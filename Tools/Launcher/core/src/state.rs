//! `<install>\.bleakhold\state.json` (DESIGN.md "Local state"): every file the launcher installed, with
//! its manifest size and hash and the size and modification time it had when it was verified, plus the
//! cache epoch and the last manifest build.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::error::{Error, Result};
use crate::paths::{self, STATE_DIR};
use crate::util::write_atomic;

pub const STATE_FILE: &str = "state.json";
const STATE_VERSION: u32 = 1;

/// One installed file.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileState {
    pub p: String,
    /// Size in the manifest.
    pub s: u64,
    /// SHA-256 in the manifest.
    pub h: String,
    /// Size on disk when verified.
    pub size: u64,
    /// Modification time on disk when verified, nanoseconds since 1970.
    pub mtime: u64,
    /// Installed as a `once` file: never overwritten or deleted.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub once: bool,
}

/// A download that was started and not finished (the launcher was closed, crashed or paused): the next
/// start shows it as paused, with progress counted from where the job began.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct JobMark {
    /// Manifest build the job downloads.
    pub build: String,
    /// Bytes and files the job had to download when it began.
    pub total_bytes: u64,
    pub files_total: usize,
}

#[derive(Default, Serialize, Deserialize)]
struct StateFile {
    #[serde(default)]
    version: u32,
    #[serde(default)]
    build: String,
    #[serde(default)]
    cache_epoch: u64,
    #[serde(default)]
    realmlist: String,
    #[serde(default)]
    exe: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    job: Option<JobMark>,
    #[serde(default)]
    files: Vec<FileState>,
}

/// The install state, keyed by path.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct InstallState {
    pub build: String,
    pub cache_epoch: u64,
    /// The realmlist of the last manifest (for Play while offline).
    pub realmlist: String,
    /// The game executable of the last manifest (for Play while offline).
    pub exe: String,
    /// The unfinished download, if any.
    pub job: Option<JobMark>,
    pub files: BTreeMap<String, FileState>,
}

impl InstallState {
    pub fn path(install: &Path) -> PathBuf {
        install.join(STATE_DIR).join(STATE_FILE)
    }

    pub fn exists(install: &Path) -> bool {
        Self::path(install).is_file()
    }

    /// Reads the state. Missing gives an empty state; unreadable is set aside as `state.json.bad` and
    /// gives an empty state (the planner then re-verifies files by hash and adopts the good ones).
    /// Entries whose path breaks the path rules are dropped, so a tampered state cannot make the
    /// launcher delete anything outside the install folder.
    pub fn load(install: &Path) -> InstallState {
        let path = Self::path(install);
        let bytes = match fs::read(&path) {
            Ok(b) => b,
            Err(_) => return InstallState::default(),
        };
        let file: StateFile = match serde_json::from_slice(&bytes) {
            Ok(f) => f,
            Err(e) => {
                log::warn!("{} is unreadable ({e}); starting from an empty state", path.display());
                let mut bad = path.clone().into_os_string();
                bad.push(".bad");
                let _ = fs::rename(&path, PathBuf::from(bad));
                return InstallState::default();
            }
        };
        let mut files = BTreeMap::new();
        for f in file.files {
            if paths::validate_rel_path(&f.p).is_ok() && !paths::is_launcher_owned(&f.p) {
                files.insert(f.p.clone(), f);
            } else {
                log::warn!("state.json: ignoring entry {:?}", f.p);
            }
        }
        InstallState {
            build: file.build,
            cache_epoch: file.cache_epoch,
            realmlist: file.realmlist,
            exe: file.exe,
            job: file.job,
            files,
        }
    }

    /// Writes the state atomically.
    pub fn save(&self, install: &Path) -> Result<()> {
        let file = StateFile {
            version: STATE_VERSION,
            build: self.build.clone(),
            cache_epoch: self.cache_epoch,
            realmlist: self.realmlist.clone(),
            exe: self.exe.clone(),
            job: self.job.clone(),
            files: self.files.values().cloned().collect(),
        };
        let bytes = serde_json::to_vec(&file).expect("state serializes");
        let path = Self::path(install);
        write_atomic(&path, &bytes).map_err(|e| Error::io(format!("saving {}", path.display()), &e))
    }

    pub fn record(&mut self, f: FileState) {
        self.files.insert(f.p.clone(), f);
    }

    pub fn forget(&mut self, p: &str) {
        self.files.remove(p);
    }

    /// Bytes of every tracked file (for the window while offline).
    pub fn total_bytes(&self) -> u64 {
        self.files.values().map(|f| f.s).sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(p: &str) -> FileState {
        FileState { p: p.into(), s: 3, h: "a".repeat(64), size: 3, mtime: 42, once: false }
    }

    #[test]
    fn round_trip_and_bad_entries() {
        let dir = std::env::temp_dir().join(format!("bh-state-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        assert_eq!(InstallState::load(&dir), InstallState::default());
        let mut s = InstallState { build: "b".into(), cache_epoch: 3, ..Default::default() };
        s.job = Some(JobMark { build: "b".into(), total_bytes: 9, files_total: 2 });
        s.record(entry("Data/a.MPQ"));
        s.record(FileState { once: true, ..entry("WTF/Config.wtf") });
        s.save(&dir).unwrap();
        assert!(InstallState::exists(&dir));
        let l = InstallState::load(&dir);
        assert_eq!(l, s);
        let text = fs::read_to_string(InstallState::path(&dir)).unwrap();
        assert!(text.contains("\"once\":true") && text.contains("\"mtime\":42"), "{text}");

        let tampered = text.replace("Data/a.MPQ", "../../evil");
        fs::write(InstallState::path(&dir), tampered).unwrap();
        let l = InstallState::load(&dir);
        assert!(!l.files.contains_key("../../evil"));
        assert_eq!(l.files.len(), 1);

        fs::write(InstallState::path(&dir), b"{broken").unwrap();
        assert_eq!(InstallState::load(&dir), InstallState::default());
        assert!(dir.join(".bleakhold/state.json.bad").exists());
        fs::remove_dir_all(&dir).unwrap();
    }
}
