//! `launcher.json`, compiled into the launcher: where the realm's update server is, the key its
//! manifests are signed with, and the realmlist to fall back on.

use ed25519_dalek::VerifyingKey;
use serde::Deserialize;

use crate::manifest::validate_host;
use crate::signature;
use crate::util::is_http_url;

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
pub struct LauncherConfig {
    pub base_url: String,
    pub public_key: String,
    pub realmlist: String,
}

impl LauncherConfig {
    /// Parses and checks `launcher.json`. The base URL gets a trailing `/`. The key is not checked here
    /// (see [`LauncherConfig::key`]): a placeholder key must still give a launcher that starts and says so.
    pub fn parse(json: &str) -> Result<LauncherConfig, String> {
        let mut c: LauncherConfig = serde_json::from_str(json).map_err(|e| format!("launcher.json: {e}"))?;
        if !is_http_url(&c.base_url) {
            return Err(format!("launcher.json: base_url {:?} is not an http(s) URL", c.base_url));
        }
        if !c.base_url.ends_with('/') {
            c.base_url.push('/');
        }
        validate_host(&c.realmlist).map_err(|e| format!("launcher.json: realmlist: {e}"))?;
        Ok(c)
    }

    /// The manifest key, or a message for the player when it is missing (the placeholder) or broken.
    pub fn key(&self) -> Result<VerifyingKey, String> {
        signature::decode_public_key(&self.public_key)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_normalizes() {
        let c = LauncherConfig::parse(
            r#"{"base_url": "http://185.217.124.41:8090", "public_key": "REPLACE_WITH_VPS_PUBLIC_KEY",
                "realmlist": "185.217.124.41"}"#,
        )
        .unwrap();
        assert_eq!(c.base_url, "http://185.217.124.41:8090/");
        assert!(c.key().unwrap_err().contains("signing key"));
        assert!(LauncherConfig::parse(r#"{"base_url": "ftp://x/", "public_key": "", "realmlist": "x"}"#).is_err());
        assert!(LauncherConfig::parse(r#"{"base_url": "http://x/", "public_key": "", "realmlist": "a b"}"#).is_err());
    }
}
