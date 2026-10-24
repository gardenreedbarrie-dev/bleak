//! HTTP client for the update server: plain `ureq` with rustls (no OpenSSL, no DLLs), no proxy, short
//! connect timeout. Everything is fetched relative to the base URL from `launcher.json`.

use std::io::Read;
use std::time::Duration;

use crate::error::{Error, Result};

#[derive(Clone)]
pub struct Http {
    agent: ureq::Agent,
    base: String,
}

/// Timeouts of the client.
#[derive(Clone, Copy, Debug)]
pub struct Timeouts {
    pub connect: Duration,
    pub read: Duration,
}

impl Default for Timeouts {
    fn default() -> Self {
        Timeouts { connect: Duration::from_secs(10), read: Duration::from_secs(30) }
    }
}

/// The start of a body, after the status was checked.
pub enum Body {
    /// 200: the whole object from byte 0.
    Full(Box<dyn Read + Send + Sync>),
    /// 206: from the requested offset.
    Partial(Box<dyn Read + Send + Sync>),
    /// 416: the requested offset is at or past the end.
    RangeNotSatisfiable,
}

impl Http {
    pub fn new(base_url: &str, user_agent: &str, t: Timeouts) -> Http {
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(t.connect)
            .timeout_read(t.read)
            .timeout_write(t.read)
            .user_agent(user_agent)
            .redirects(5)
            .build();
        let mut base = base_url.to_string();
        if !base.ends_with('/') {
            base.push('/');
        }
        Http { agent, base }
    }

    pub fn base(&self) -> &str {
        &self.base
    }

    /// `base + rel`.
    pub fn url(&self, rel: &str) -> String {
        format!("{}{}", self.base, rel.trim_start_matches('/'))
    }

    /// A small file (the manifest, its signature), whole, at most `limit` bytes, bypassing caches.
    pub fn get_small(&self, rel: &str, limit: usize) -> Result<Vec<u8>> {
        let url = self.url(rel);
        let resp = self
            .agent
            .get(&url)
            .set("Cache-Control", "no-cache")
            .set("Pragma", "no-cache")
            .call()
            .map_err(|e| net_error(&url, e))?;
        let mut out = Vec::new();
        resp.into_reader()
            .take(limit as u64 + 1)
            .read_to_end(&mut out)
            .map_err(|e| Error::network(format!("{url}: {e}")))?;
        if out.len() > limit {
            return Err(Error::network(format!("{url}: larger than {limit} bytes")));
        }
        Ok(out)
    }

    /// GET `url` from byte `offset` (a `Range` request when `offset > 0`).
    pub fn get_from(&self, url: &str, offset: u64) -> Result<Body> {
        let mut req = self.agent.get(url);
        if offset > 0 {
            req = req.set("Range", &format!("bytes={offset}-"));
        }
        match req.call() {
            Ok(resp) if resp.status() == 206 => {
                let start = resp.header("Content-Range").and_then(content_range_start);
                if start != Some(offset) {
                    return Err(Error::network(format!("{url}: the server answered a different range")));
                }
                Ok(Body::Partial(resp.into_reader()))
            }
            Ok(resp) if resp.status() == 200 => Ok(Body::Full(resp.into_reader())),
            Ok(resp) => Err(Error::network(format!("{url}: unexpected HTTP {}", resp.status()))),
            Err(ureq::Error::Status(416, _)) => Ok(Body::RangeNotSatisfiable),
            Err(e) => Err(net_error(url, e)),
        }
    }
}

fn net_error(url: &str, e: ureq::Error) -> Error {
    match e {
        ureq::Error::Status(code, _) => Error::network(format!("{url}: HTTP {code}")),
        // A transport error already names the URL.
        ureq::Error::Transport(t) => Error::network(t.to_string()),
    }
}

/// `bytes 100-199/200` → 100.
fn content_range_start(v: &str) -> Option<u64> {
    let v = v.trim();
    let rest = v.strip_prefix("bytes")?.trim_start();
    let (range, _) = rest.split_once('/')?;
    let (start, _) = range.split_once('-')?;
    start.trim().parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn content_range() {
        assert_eq!(content_range_start("bytes 100-199/200"), Some(100));
        assert_eq!(content_range_start("bytes 0-0/*"), Some(0));
        assert_eq!(content_range_start("items 1-2/3"), None);
        assert_eq!(content_range_start("bytes */200"), None);
    }

    #[test]
    fn urls() {
        let h = Http::new("http://h:1", "t", Timeouts::default());
        assert_eq!(h.url("manifest.json"), "http://h:1/manifest.json");
        assert_eq!(h.url("/objects/ab/x"), "http://h:1/objects/ab/x");
    }
}
