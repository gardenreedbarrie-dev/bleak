//! Shared test helpers: a tiny HTTP/1.1 file server on 127.0.0.1 (std only) that understands `Range` and
//! can corrupt or cut responses on purpose, manifest signing with a fixed test key, and temp folders.

#![allow(dead_code)]

use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use ed25519_dalek::{Signer, SigningKey};
use serde_json::{json, Value};

use bleakhold_launcher_core::download::sha256_hex;

/// A request the server saw.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Hit {
    pub path: String,
    pub range: Option<u64>,
}

#[derive(Default)]
pub struct ServerState {
    pub files: Mutex<HashMap<String, Vec<u8>>>,
    pub hits: Mutex<Vec<Hit>>,
    /// Path → how many more responses get one byte flipped.
    pub corrupt: Mutex<HashMap<String, usize>>,
    /// Path → (how many more responses are cut, bytes of body sent before closing).
    pub cut: Mutex<HashMap<String, (usize, usize)>>,
    /// Answer every request with the whole file (as if `Range` were not supported).
    pub ignore_range: AtomicBool,
    /// Sleep this many ms per 16 KiB of body (to keep downloads running for pause tests).
    pub slow_ms: AtomicU64,
}

pub struct TestServer {
    pub base: String,
    pub state: Arc<ServerState>,
}

impl TestServer {
    pub fn start() -> TestServer {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}/", listener.local_addr().unwrap());
        let state = Arc::new(ServerState::default());
        let st = state.clone();
        thread::spawn(move || {
            for conn in listener.incoming() {
                let Ok(conn) = conn else { continue };
                let st = st.clone();
                thread::spawn(move || {
                    let _ = handle(conn, &st);
                });
            }
        });
        TestServer { base, state }
    }

    pub fn put(&self, path: &str, bytes: &[u8]) {
        self.state.files.lock().unwrap().insert(path.to_string(), bytes.to_vec());
    }

    pub fn remove(&self, path: &str) {
        self.state.files.lock().unwrap().remove(path);
    }

    /// Stores `bytes` as a content-addressed object and returns its hash.
    pub fn put_object(&self, bytes: &[u8]) -> String {
        let h = sha256_hex(bytes);
        self.put(&format!("objects/{}/{h}", &h[..2]), bytes);
        h
    }

    pub fn hits(&self) -> Vec<Hit> {
        self.state.hits.lock().unwrap().clone()
    }

    pub fn hits_for(&self, path: &str) -> Vec<Hit> {
        self.hits().into_iter().filter(|h| h.path == path).collect()
    }

    pub fn clear_hits(&self) {
        self.state.hits.lock().unwrap().clear();
    }

    pub fn corrupt_next(&self, path: &str, times: usize) {
        self.state.corrupt.lock().unwrap().insert(path.to_string(), times);
    }

    pub fn cut_next(&self, path: &str, times: usize, after: usize) {
        self.state.cut.lock().unwrap().insert(path.to_string(), (times, after));
    }

    /// Publishes a signed manifest: every file as an object, then `manifest.json` and its signature.
    pub fn publish(&self, spec: &Spec) -> Value {
        let mut files = Vec::new();
        for f in &spec.files {
            let h = self.put_object(&f.content);
            let mut e = json!({ "p": f.p, "s": f.content.len(), "h": h });
            if f.once {
                e["once"] = json!(true);
            }
            files.push(e);
        }
        let mut m = json!({
            "format": 1,
            "product": "Bleakhold",
            "build": spec.build,
            "realmlist": "127.0.0.1",
            "exe": spec.exe,
            "objects": "objects/",
            "cache_epoch": spec.cache_epoch,
            "files": files,
            "news": [ { "title": "Hello", "date": "2026-10-23", "body": "News", "url": "https://example.org/n" } ],
            "links": { "website": "https://example.org/" },
        });
        if let Some(l) = &spec.launcher {
            let h = self.put_object(&l.1);
            m["launcher"] = json!({ "version": l.0, "size": l.1.len(), "sha256": h });
        }
        if let Some(port) = spec.server_port {
            m["server"] = json!({ "name": "Test Realm", "host": "127.0.0.1", "auth_port": port, "world_port": port });
        }
        let bytes = serde_json::to_vec(&m).unwrap();
        self.put("manifest.json.sig", sign(&bytes).as_bytes());
        self.put("manifest.json", &bytes);
        m
    }
}

/// A file of a manifest spec.
#[derive(Clone)]
pub struct SpecFile {
    pub p: String,
    pub content: Vec<u8>,
    pub once: bool,
}

pub struct Spec {
    pub build: String,
    pub exe: String,
    pub cache_epoch: u64,
    pub files: Vec<SpecFile>,
    /// (version, bytes)
    pub launcher: Option<(String, Vec<u8>)>,
    pub server_port: Option<u16>,
}

impl Spec {
    pub fn new(build: &str) -> Spec {
        Spec {
            build: build.into(),
            exe: "Bleakhold.exe".into(),
            cache_epoch: 1,
            files: Vec::new(),
            launcher: None,
            server_port: None,
        }
    }

    pub fn file(mut self, p: &str, content: &[u8]) -> Spec {
        self.files.push(SpecFile { p: p.into(), content: content.to_vec(), once: false });
        self
    }

    pub fn once(mut self, p: &str, content: &[u8]) -> Spec {
        self.files.push(SpecFile { p: p.into(), content: content.to_vec(), once: true });
        self
    }
}

fn handle(conn: TcpStream, st: &ServerState) -> std::io::Result<()> {
    conn.set_read_timeout(Some(Duration::from_secs(10)))?;
    let mut reader = BufReader::new(conn.try_clone()?);
    let mut line = String::new();
    reader.read_line(&mut line)?;
    let path = line.split_whitespace().nth(1).unwrap_or("/").trim_start_matches('/').to_string();
    let mut range = None;
    loop {
        let mut h = String::new();
        if reader.read_line(&mut h)? == 0 || h == "\r\n" || h == "\n" {
            break;
        }
        let lower = h.to_ascii_lowercase();
        if let Some(v) = lower.strip_prefix("range:") {
            let v = v.trim();
            if let Some(n) = v.strip_prefix("bytes=").and_then(|r| r.split('-').next()) {
                range = n.trim().parse::<u64>().ok();
            }
        }
    }
    st.hits.lock().unwrap().push(Hit { path: path.clone(), range });
    let mut out = conn;
    let file = st.files.lock().unwrap().get(&path).cloned();
    let Some(mut body) = file else {
        out.write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")?;
        return Ok(());
    };
    let total = body.len() as u64;
    let mut status = "200 OK".to_string();
    let mut extra = String::new();
    if let Some(start) = range.filter(|_| !st.ignore_range.load(Ordering::SeqCst)) {
        if start >= total {
            let head = format!(
                "HTTP/1.1 416 Range Not Satisfiable\r\nContent-Range: bytes */{total}\r\nContent-Length: 0\r\n\
                 Connection: close\r\n\r\n"
            );
            out.write_all(head.as_bytes())?;
            return Ok(());
        }
        status = "206 Partial Content".into();
        extra = format!("Content-Range: bytes {start}-{}/{total}\r\n", total - 1);
        body = body[start as usize..].to_vec();
    }
    {
        let mut c = st.corrupt.lock().unwrap();
        if let Some(n) = c.get_mut(&path) {
            if *n > 0 && !body.is_empty() {
                *n -= 1;
                let mid = body.len() / 2;
                body[mid] ^= 0xff;
            }
        }
    }
    let mut send = body.len();
    {
        let mut c = st.cut.lock().unwrap();
        if let Some((n, after)) = c.get_mut(&path) {
            if *n > 0 {
                *n -= 1;
                send = (*after).min(body.len());
            }
        }
    }
    let head = format!(
        "HTTP/1.1 {status}\r\nContent-Length: {}\r\n{extra}Content-Type: application/octet-stream\r\n\
         Connection: close\r\n\r\n",
        body.len()
    );
    out.write_all(head.as_bytes())?;
    let slow = st.slow_ms.load(Ordering::SeqCst);
    for chunk in body[..send].chunks(16 * 1024) {
        out.write_all(chunk)?;
        if slow > 0 {
            thread::sleep(Duration::from_millis(slow));
        }
    }
    out.flush()?;
    let _ = out.shutdown(std::net::Shutdown::Both);
    // Drain anything left so the client sees a clean close.
    let mut sink = Vec::new();
    let _ = reader.read_to_end(&mut sink);
    Ok(())
}

/// The fixed test signing key (never used outside tests).
pub fn signing_key() -> SigningKey {
    SigningKey::from_bytes(&[7u8; 32])
}

pub fn public_key_b64() -> String {
    STANDARD.encode(signing_key().verifying_key().to_bytes())
}

pub fn sign(bytes: &[u8]) -> String {
    STANDARD.encode(signing_key().sign(bytes).to_bytes())
}

/// A fresh, empty temp folder for one test.
pub fn temp_dir(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("bh-it-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// Deterministic bytes.
pub fn bytes(seed: u8, len: usize) -> Vec<u8> {
    let mut x: u32 = 0x9e37_79b9 ^ seed as u32;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 17;
            x ^= x << 5;
            (x & 0xff) as u8
        })
        .collect()
}

pub fn read(p: &Path) -> Vec<u8> {
    fs::read(p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}
