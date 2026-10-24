//! The manifest (DESIGN.md "Manifest (format 1)"): parsing and strict validation. A manifest that fails
//! any rule is rejected whole; nothing in it is used.

use std::collections::{BTreeMap, HashSet};

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
    /// A mirror: another address serving the same bytes, tried before the realm's `objects/` copy.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub u: Option<String>,
    /// The optional pack the file belongs to; installed only while that pack is on.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pack: Option<String>,
}

/// An optional part of the game the player may leave out, like the HD graphics.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
pub struct Pack {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub about: String,
    /// On for a player who has not chosen.
    #[serde(default)]
    pub default: bool,
}

/// The most packs a manifest may declare.
pub const MAX_PACKS: usize = 16;

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
    #[serde(default)]
    pub packs: Vec<Pack>,
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
            if let Some(u) = &f.u {
                validate_mirror(u).map_err(|e| format!("{:?}: mirror {e}", f.p))?;
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
        self.validate_packs()
    }

    fn validate_packs(&self) -> std::result::Result<(), String> {
        if self.packs.len() > MAX_PACKS {
            return Err(format!("more than {MAX_PACKS} packs"));
        }
        let mut ids = HashSet::new();
        for p in &self.packs {
            if !is_pack_id(&p.id) {
                return Err(format!("pack id {:?}: 1-32 characters of a-z, 0-9 and -", p.id));
            }
            if !ids.insert(p.id.as_str()) {
                return Err(format!("pack {:?} is listed twice", p.id));
            }
            if p.name.trim().is_empty() || p.name.chars().count() > 60 || p.name.chars().any(char::is_control) {
                return Err(format!("pack {:?}: the name is empty, longer than 60 or has control characters", p.id));
            }
            if p.about.chars().count() > 300 || p.about.chars().any(char::is_control) {
                return Err(format!("pack {:?}: the text is longer than 300 or has control characters", p.id));
            }
        }
        for f in &self.files {
            let Some(pack) = &f.pack else { continue };
            if !ids.contains(pack.as_str()) {
                return Err(format!("{:?}: unknown pack {pack:?}", f.p));
            }
            if f.once {
                return Err(format!("{:?}: a 'once' file cannot belong to a pack", f.p));
            }
            if f.p == self.exe {
                return Err("the game executable cannot belong to a pack".into());
            }
        }
        Ok(())
    }

    /// Whether `pack` is on for these choices; a pack the player has not chosen follows its `default`.
    pub fn pack_on(pack: &Pack, choices: &BTreeMap<String, bool>) -> bool {
        choices.get(&pack.id).copied().unwrap_or(pack.default)
    }

    /// What a player with these pack choices installs: every file outside a pack, and the files of the packs
    /// that are on. Files of a pack that is off are then no longer listed, so the launcher removes the ones it
    /// installed, as it does with any file a manifest drops.
    pub fn for_packs(&self, choices: &BTreeMap<String, bool>) -> Manifest {
        let on: HashSet<&str> =
            self.packs.iter().filter(|p| Self::pack_on(p, choices)).map(|p| p.id.as_str()).collect();
        let mut m = self.clone();
        m.files.retain(|f| f.pack.as_deref().is_none_or(|p| on.contains(p)));
        m
    }

    /// The size of a pack's files.
    pub fn pack_bytes(&self, id: &str) -> u64 {
        self.files.iter().filter(|f| f.pack.as_deref() == Some(id)).map(|f| f.s).sum()
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

/// A pack id: 1-32 characters of `a-z`, `0-9` and `-`.
pub fn is_pack_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 32 && id.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
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

/// An absolute `http://` or `https://` URL of printable ASCII (no spaces), at most 2048 characters.
pub fn validate_mirror(u: &str) -> std::result::Result<(), String> {
    let rest = u.strip_prefix("https://").or_else(|| u.strip_prefix("http://"));
    let Some(rest) = rest else {
        return Err(format!("{u:?} is not an http(s) URL"));
    };
    if u.len() > 2048 {
        return Err("is too long".into());
    }
    if rest.is_empty() || rest.starts_with('/') {
        return Err(format!("{u:?} has no host"));
    }
    if !u.bytes().all(|b| b.is_ascii_graphic()) {
        return Err(format!("{u:?} has spaces, control or non-ASCII characters"));
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
        assert!(m.files.iter().all(|f| f.u.is_none()));
    }

    #[test]
    fn packs() {
        let mut v = base();
        v["packs"] = json!([{ "id": "hd", "name": "HD graphics", "about": "Reforged", "default": true },
                            { "id": "extra-music", "name": "Music" }]);
        v["files"].as_array_mut().unwrap().push(json!({ "p": "Data/patch-A.MPQ", "s": 5, "h": H, "pack": "hd" }));
        v["files"].as_array_mut().unwrap().push(json!({ "p": "Sound/x.mp3", "s": 7, "h": H, "pack": "extra-music" }));
        let m = parse(&v).unwrap();
        assert_eq!(m.packs.len(), 2);
        assert!(m.packs[0].default && !m.packs[1].default, "default is false when absent");
        assert_eq!(m.pack_bytes("hd"), 5);
        let mut choices = BTreeMap::new();
        let names = |m: &Manifest| m.files.iter().map(|f| f.p.clone()).collect::<Vec<_>>();
        assert_eq!(names(&m.for_packs(&choices)), ["Bleakhold.exe", "WTF/Config.wtf", "Data/patch-A.MPQ"]);
        choices.insert("hd".to_string(), false);
        choices.insert("extra-music".to_string(), true);
        assert_eq!(names(&m.for_packs(&choices)), ["Bleakhold.exe", "WTF/Config.wtf", "Sound/x.mp3"]);
        choices.insert("gone".to_string(), true);
        assert_eq!(m.for_packs(&choices).files.len(), 3, "a choice for a pack the manifest lacks changes nothing");

        let with_pack = |change: &dyn Fn(&mut Value)| {
            let mut v = base();
            v["packs"] = json!([{ "id": "hd", "name": "HD graphics", "default": true }]);
            change(&mut v);
            v
        };
        for (change, why) in [
            (&(|v: &mut Value| v["files"][0]["pack"] = json!("nope")) as &dyn Fn(&mut Value), "unknown pack"),
            (&|v: &mut Value| v["files"][1]["pack"] = json!("hd"), "'once' file"),
            (&|v: &mut Value| v["files"][0]["pack"] = json!("hd"), "game executable"),
            (&|v: &mut Value| v["packs"][0]["id"] = json!("HD"), "pack id"),
            (&|v: &mut Value| v["packs"][0]["id"] = json!(""), "pack id"),
            (&|v: &mut Value| v["packs"].as_array_mut().unwrap().push(json!({ "id": "hd", "name": "x" })), "twice"),
            (&|v: &mut Value| v["packs"][0]["name"] = json!(" "), "name"),
            (&|v: &mut Value| v["packs"][0]["name"] = json!("x".repeat(61)), "name"),
            (&|v: &mut Value| v["packs"][0]["about"] = json!("a\nb"), "text"),
            (
                &|v: &mut Value| {
                    v["packs"] =
                        json!((0..17).map(|i| json!({ "id": format!("p{i}"), "name": "x" })).collect::<Vec<_>>())
                },
                "more than",
            ),
        ] {
            let e = parse(&with_pack(change)).expect_err(why);
            assert!(e.message.contains(why), "{} (expected {why})", e.message);
        }
    }

    #[test]
    fn mirrors() {
        let mut v = base();
        v["files"][0]["u"] = json!("https://pub-0123.r2.dev/patch-A.mpq");
        let m = parse(&v).unwrap();
        assert_eq!(m.files[0].u.as_deref(), Some("https://pub-0123.r2.dev/patch-A.mpq"));
        for bad in ["ftp://x/y", "objects/ab/x", "https://", "https:///x", "https://a b/c", "https://x/\u{e9}"] {
            rejects(|v| v["files"][0]["u"] = json!(bad), "mirror");
        }
        rejects(|v| v["files"][0]["u"] = json!(format!("https://x/{}", "a".repeat(2048))), "too long");
        rejects(|v| v["files"][0]["u"] = json!(5), "could not be read");
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
