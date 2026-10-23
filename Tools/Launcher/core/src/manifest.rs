//! The manifest (DESIGN.md "Manifest (format 1)"): parsing and strict validation. A manifest that fails
//! any rule is rejected whole; nothing in it is used.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::error::{Error, Result};
use crate::paths;

/// The largest manifest the launcher reads.
pub const MAX_MANIFEST_BYTES: usize = 32 << 20;

/// One file of the game.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
pub struct FileEntry {
    /// Path relative to the install folder, `/`-separated.
    pub p: String,
    /// Size in bytes.
    pub s: u64,
    /// SHA-256, 64 lower-case hex characters.
    pub h: String,
    /// Install when missing, never overwrite or delete.
    #[serde(default)]
    pub once: bool,
}

/// The newest launcher.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
pub struct LauncherInfo {
    pub version: String,
    pub size: u64,
    pub sha256: String,
}

/// The realm, for the status light.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
pub struct ServerInfo {
    #[serde(default)]
    pub name: String,
    pub host: String,
    #[serde(default = "default_auth_port")]
    pub auth_port: u16,
    #[serde(default = "default_world_port")]
    pub world_port: u16,
}

fn default_auth_port() -> u16 {
    3724
}

fn default_world_port() -> u16 {
    8085
}

fn default_objects() -> String {
    "objects/".into()
}

/// A parsed and validated manifest.
#[derive(Clone, Debug, PartialEq, Deserialize, Serialize)]
pub struct Manifest {
    pub format: u32,
    #[serde(default)]
    pub product: String,
    #[serde(default)]
    pub build: String,
    #[serde(default)]
    pub realmlist: String,
    pub exe: String,
    #[serde(default = "default_objects")]
    pub objects: String,
    #[serde(default)]
    pub cache_epoch: u64,
    #[serde(default)]
    pub launcher: Option<LauncherInfo>,
    pub files: Vec<FileEntry>,
    #[serde(default)]
    pub news: Vec<Value>,
    #[serde(default)]
    pub links: Map<String, Value>,
    #[serde(default)]
    pub server: Option<ServerInfo>,
}

impl Manifest {
    /// Parses and validates manifest bytes (already verified against the signature).
    pub fn parse(bytes: &[u8]) -> Result<Manifest> {
        if bytes.len() > MAX_MANIFEST_BYTES {
            return Err(Error::manifest("The update list is too large."));
        }
        let mut m: Manifest = serde_json::from_slice(bytes)
            .map_err(|e| Error::manifest(format!("The update list could not be read: {e}")))?;
        m.validate().map_err(|e| Error::manifest(format!("The update list is invalid: {e}")))?;
        if !m.objects.ends_with('/') {
            m.objects.push('/');
        }
        Ok(m)
    }

    /// Every rule of DESIGN.md, plus what the launcher needs to run the result safely.
    pub fn validate(&self) -> std::result::Result<(), String> {
        if self.format != 1 {
            return Err(format!("format {} is not supported by this launcher", self.format));
        }
        if self.files.is_empty() {
            return Err("no files".into());
        }
        paths::validate_path_set(self.files.iter().map(|f| f.p.as_str()))?;
        for f in &self.files {
            if !is_sha256_hex(&f.h) {
                return Err(format!("{:?}: bad hash {:?}", f.p, f.h));
            }
        }
        // The executable is started only when it is among the files (its hash is what Play checks); a
        // manifest without it is still valid for downloading.
        paths::validate_rel_path(&self.exe).map_err(|e| format!("exe {:?}: {e}", self.exe))?;
        if self.files.iter().any(|f| f.p == self.exe && f.once) {
            return Err("the game executable cannot be a 'once' file".into());
        }
        if !self.exe.to_lowercase().ends_with(".exe") {
            return Err(format!("the game executable {:?} is not an .exe", self.exe));
        }
        validate_host(&self.realmlist).map_err(|e| format!("realmlist: {e}"))?;
        validate_objects(&self.objects)?;
        if let Some(l) = &self.launcher {
            semver::Version::parse(&l.version).map_err(|e| format!("launcher version {:?}: {e}", l.version))?;
            if !is_sha256_hex(&l.sha256) {
                return Err(format!("launcher: bad hash {:?}", l.sha256));
            }
            if l.size == 0 {
                return Err("launcher: size 0".into());
            }
        }
        if let Some(s) = &self.server {
            validate_host(&s.host).map_err(|e| format!("server host: {e}"))?;
            if s.auth_port == 0 || s.world_port == 0 {
                return Err("server: port 0".into());
            }
        }
        if self.build.chars().any(char::is_control) || self.build.len() > 200 {
            return Err("build: control characters or too long".into());
        }
        Ok(())
    }

    /// Sum of every file's size.
    pub fn total_bytes(&self) -> u64 {
        self.files.iter().map(|f| f.s).sum()
    }

    pub fn file(&self, p: &str) -> Option<&FileEntry> {
        self.files.iter().find(|f| f.p == p)
    }

    /// `objects/<h0h1>/<h>`, relative to the base URL.
    pub fn object_path(&self, h: &str) -> String {
        object_path(&self.objects, h)
    }
}

/// `<objects><h0h1>/<h>`.
pub fn object_path(objects: &str, h: &str) -> String {
    format!("{objects}{}/{h}", &h[..2])
}

/// 64 lower-case hex characters.
pub fn is_sha256_hex(h: &str) -> bool {
    h.len() == 64 && h.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// A host name, IPv4 address or `host:port`: letters, digits, `.`, `-` and `:` only, so it can go into
/// `realmlist.wtf` and `Config.wtf` as it is.
pub fn validate_host(h: &str) -> std::result::Result<(), String> {
    if h.is_empty() {
        return Err("empty".into());
    }
    if h.len() > 253 {
        return Err("too long".into());
    }
    if !h.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-' || b == b':') {
        return Err(format!("{h:?} has characters a host name cannot have"));
    }
    Ok(())
}

fn validate_objects(o: &str) -> std::result::Result<(), String> {
    let trimmed = o.strip_suffix('/').unwrap_or(o);
    if trimmed.is_empty() {
        return Err("objects: empty".into());
    }
    if !trimmed.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b'_' | b'/')) {
        return Err(format!("objects {o:?}: unexpected characters"));
    }
    paths::validate_rel_path(trimmed).map_err(|e| format!("objects {o:?}: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const H: &str = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    fn base() -> Value {
        json!({
            "format": 1, "product": "Bleakhold", "build": "b1", "realmlist": "185.217.124.41",
            "exe": "Bleakhold.exe", "objects": "objects/", "cache_epoch": 2,
            "launcher": { "version": "1.2.0", "size": 3, "sha256": H },
            "files": [
                { "p": "Bleakhold.exe", "s": 3, "h": H },
                { "p": "WTF/Config.wtf", "s": 3, "h": H, "once": true }
            ],
            "news": [ { "title": "t", "date": "2026-10-23", "body": "b", "url": "https://x" } ],
            "links": { "website": "https://x" },
            "server": { "name": "Bleakhold", "host": "185.217.124.41", "auth_port": 3724, "world_port": 8085 },
            "future_field": { "ignored": true }
        })
    }

    fn parse(v: &Value) -> Result<Manifest> {
        Manifest::parse(serde_json::to_vec(v).unwrap().as_slice())
    }

    #[test]
    fn parses_the_documented_shape() {
        let m = parse(&base()).unwrap();
        assert_eq!(m.cache_epoch, 2);
        assert_eq!(m.files.len(), 2);
        assert!(m.files[1].once);
        assert_eq!(m.total_bytes(), 6);
        assert_eq!(m.object_path(H), format!("objects/ba/{H}"));
        assert_eq!(m.server.as_ref().unwrap().world_port, 8085);
        assert_eq!(m.launcher.as_ref().unwrap().version, "1.2.0");
    }

    #[test]
    fn defaults_for_optional_fields() {
        let v = json!({ "format": 1, "realmlist": "x.example", "exe": "Wow.exe",
                        "files": [ { "p": "Wow.exe", "s": 1, "h": H } ] });
        let m = parse(&v).unwrap();
        assert_eq!(m.objects, "objects/");
        assert_eq!(m.cache_epoch, 0);
        assert!(m.launcher.is_none() && m.server.is_none() && m.news.is_empty() && m.links.is_empty());
        let mut v2 = v.clone();
        v2["objects"] = json!("store/v1");
        assert_eq!(parse(&v2).unwrap().objects, "store/v1/");
    }

    fn rejects(change: impl FnOnce(&mut Value), why: &str) {
        let mut v = base();
        change(&mut v);
        let e = parse(&v).expect_err(why);
        assert_eq!(e.code, crate::Code::Manifest);
        assert!(e.message.contains(why), "{} (expected {why})", e.message);
    }

    #[test]
    fn rejects_bad_manifests() {
        rejects(|v| v["format"] = json!(2), "format 2");
        rejects(|v| v["files"] = json!([]), "no files");
        rejects(|v| v["files"][0]["h"] = json!("ABC"), "bad hash");
        rejects(|v| v["files"][0]["h"] = json!(H.to_uppercase()), "bad hash");
        rejects(|v| v["exe"] = json!("../Missing.exe"), "exe");
        rejects(|v| v["exe"] = json!("WTF/Config.wtf"), "'once'");
        rejects(|v| v["exe"] = json!("Data/x.MPQ"), "not an .exe");
        rejects(|v| v["realmlist"] = json!("evil\" host"), "realmlist");
        rejects(|v| v["realmlist"] = json!(""), "realmlist");
        rejects(|v| v["objects"] = json!("../objects/"), "objects");
        rejects(|v| v["objects"] = json!("http://evil/"), "objects");
        rejects(|v| v["launcher"]["version"] = json!("one"), "launcher version");
        rejects(|v| v["launcher"]["sha256"] = json!("00"), "launcher: bad hash");
        rejects(|v| v["server"]["host"] = json!("a b"), "server host");
        rejects(|v| v["news"] = json!("not a list"), "could not be read");
        rejects(|v| v["files"][0]["s"] = json!(-1), "could not be read");
        rejects(|v| v["files"].as_array_mut().unwrap().push(json!({ "p": "bleakhold.EXE", "s": 1, "h": H })), "twice");
        for bad in ["/abs", "C:/x", "a\\b", "a/../b", "a/./b", "a//b", "a\u{1}b", "CON", "aux.txt", "a/b:c"] {
            rejects(|v| v["files"].as_array_mut().unwrap().push(json!({ "p": bad, "s": 1, "h": H })), "invalid");
        }
        let e = Manifest::parse(b"{not json").unwrap_err();
        assert_eq!(e.code, crate::Code::Manifest);
    }

    #[test]
    fn hosts() {
        assert!(validate_host("185.217.124.41").is_ok());
        assert!(validate_host("logon.example.org:3724").is_ok());
        assert!(validate_host("a b").is_err());
        assert!(validate_host("a\"b").is_err());
        assert!(validate_host("a\nb").is_err());
    }
}
