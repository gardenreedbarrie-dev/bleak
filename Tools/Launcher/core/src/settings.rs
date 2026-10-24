//! `settings.json` in the launcher's config folder (DESIGN.md "Local state").

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::manifest::is_pack_id;
use crate::util::write_atomic;

pub const SETTINGS_FILE: &str = "settings.json";
pub const MAX_PARALLEL: u32 = 8;
pub const MAX_LIMIT_MBPS: u32 = 10_000;
/// `limit_mbps` counts megabytes (10^6 bytes) per second, as the window shows it ("MB/s").
pub const BYTES_PER_MB: u64 = 1_000_000;
/// The most pack choices kept.
pub const MAX_PACK_CHOICES: usize = 32;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub install_dir: Option<String>,
    /// Downloads at the same time, 1-8.
    pub parallel: u32,
    /// Speed limit in MB/s, 0 = none.
    pub limit_mbps: u32,
    pub close_on_play: bool,
    /// The player asked for shortcuts when installing.
    pub shortcuts: bool,
    /// The player's choices of optional packs (id → on); a pack not listed follows the manifest's default.
    pub packs: BTreeMap<String, bool>,
    /// SHA-256 of the launcher the last self-update installed (loop guard; not changed by the window).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub self_update_sha: Option<String>,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            install_dir: None,
            parallel: 4,
            limit_mbps: 0,
            close_on_play: true,
            shortcuts: false,
            packs: BTreeMap::new(),
            self_update_sha: None,
        }
    }
}

impl Settings {
    pub fn path(config_dir: &Path) -> PathBuf {
        config_dir.join(SETTINGS_FILE)
    }

    /// Reads the settings; a missing or unreadable file gives the defaults.
    pub fn load(config_dir: &Path) -> Settings {
        let path = Self::path(config_dir);
        match fs::read(&path) {
            Ok(bytes) => match serde_json::from_slice::<Settings>(&bytes) {
                Ok(s) => s.normalized(),
                Err(e) => {
                    log::warn!("{} is unreadable ({e}); using defaults", path.display());
                    Settings::default()
                }
            },
            Err(_) => Settings::default(),
        }
    }

    pub fn save(&self, config_dir: &Path) -> std::io::Result<()> {
        let bytes = serde_json::to_vec_pretty(&self.clone().normalized()).expect("settings serialize");
        write_atomic(&Self::path(config_dir), &bytes)
    }

    /// Values clamped to what the launcher supports.
    pub fn normalized(mut self) -> Settings {
        self.parallel = self.parallel.clamp(1, MAX_PARALLEL);
        self.limit_mbps = self.limit_mbps.min(MAX_LIMIT_MBPS);
        if self.install_dir.as_deref().is_some_and(|d| d.trim().is_empty()) {
            self.install_dir = None;
        }
        self
    }

    /// Takes the keys the window may change (`parallel`, `limit_mbps`, `close_on_play`, `shortcuts`, `packs`)
    /// from a `save_settings` payload; others, and values of the wrong type, are ignored. `limit_mbps` may be
    /// `null` (no limit) or a fraction (rounded up); `packs` sets the choices it names and keeps the others.
    pub fn merge_json(&mut self, v: &Value) {
        if let Some(n) = v.get("parallel").and_then(Value::as_f64) {
            self.parallel = n.round().clamp(1.0, MAX_PARALLEL as f64) as u32;
        }
        match v.get("limit_mbps") {
            Some(Value::Null) => self.limit_mbps = 0,
            Some(x) => {
                if let Some(n) = x.as_f64().or_else(|| x.as_str().and_then(|s| s.trim().parse().ok())) {
                    self.limit_mbps = if n <= 0.0 { 0 } else { n.ceil().min(MAX_LIMIT_MBPS as f64) as u32 };
                } else if x.as_str().is_some_and(|s| s.trim().is_empty()) {
                    self.limit_mbps = 0;
                }
            }
            None => {}
        }
        if let Some(b) = v.get("close_on_play").and_then(Value::as_bool) {
            self.close_on_play = b;
        }
        if let Some(b) = v.get("shortcuts").and_then(Value::as_bool) {
            self.shortcuts = b;
        }
        if let Some(packs) = v.get("packs").and_then(Value::as_object) {
            for (id, on) in packs {
                let room = self.packs.len() < MAX_PACK_CHOICES || self.packs.contains_key(id);
                if let (Some(on), true, true) = (on.as_bool(), is_pack_id(id), room) {
                    self.packs.insert(id.clone(), on);
                }
            }
        }
    }

    /// The speed limit in bytes per second, 0 = none.
    pub fn limit_bps(&self) -> u64 {
        self.limit_mbps as u64 * BYTES_PER_MB
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn defaults_save_load_and_clamp() {
        let dir = std::env::temp_dir().join(format!("bh-settings-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        assert_eq!(Settings::load(&dir), Settings::default());
        let s = Settings { install_dir: Some("C:\\Games\\Bleakhold".into()), parallel: 99, ..Default::default() };
        s.save(&dir).unwrap();
        let l = Settings::load(&dir);
        assert_eq!(l.parallel, 8);
        assert_eq!(l.install_dir.as_deref(), Some("C:\\Games\\Bleakhold"));
        assert!(l.close_on_play);
        fs::write(Settings::path(&dir), b"{\"parallel\": 0, \"unknown\": 1}").unwrap();
        assert_eq!(Settings::load(&dir).parallel, 1);
        fs::write(Settings::path(&dir), b"garbage").unwrap();
        assert_eq!(Settings::load(&dir), Settings::default());
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn merge_from_the_window() {
        let mut s = Settings::default();
        s.merge_json(&json!({ "parallel": 6, "limit_mbps": 2.5, "close_on_play": false, "install_dir": "x" }));
        assert_eq!((s.parallel, s.limit_mbps, s.close_on_play), (6, 3, false));
        assert_eq!(s.install_dir, None);
        assert_eq!(s.limit_bps(), 3_000_000);
        s.merge_json(&json!({ "limit_mbps": null, "parallel": "fast" }));
        assert_eq!((s.parallel, s.limit_mbps), (6, 0));
        s.merge_json(&json!({ "limit_mbps": "12", "parallel": 0 }));
        assert_eq!((s.parallel, s.limit_mbps), (1, 12));
        s.merge_json(&json!({ "limit_mbps": "" }));
        assert_eq!(s.limit_mbps, 0);
    }

    #[test]
    fn pack_choices() {
        let mut s = Settings::default();
        s.merge_json(&json!({ "packs": { "hd": false, "Bad Id": true, "music": "yes" } }));
        assert_eq!(s.packs, BTreeMap::from([("hd".to_string(), false)]));
        s.merge_json(&json!({ "packs": { "music": true } }));
        assert_eq!(s.packs.len(), 2, "other choices are kept");
        s.merge_json(&json!({ "packs": { "hd": true } }));
        assert!(s.packs["hd"]);
        let many: serde_json::Map<String, Value> = (0..40).map(|i| (format!("p{i}"), json!(true))).collect();
        s.merge_json(&json!({ "packs": many }));
        assert_eq!(s.packs.len(), MAX_PACK_CHOICES);
        let dir = std::env::temp_dir().join(format!("bh-settings-packs-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        s.save(&dir).unwrap();
        assert_eq!(Settings::load(&dir).packs, s.packs);
        fs::remove_dir_all(&dir).unwrap();
    }
}
