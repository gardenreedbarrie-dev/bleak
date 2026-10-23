//! Install folder checks for the install dialog (`folder_info`) and before installing.

use std::fs;
use std::path::{Path, PathBuf};

use serde::Serialize;

use crate::error::{Error, Result};
use crate::manifest::Manifest;
use crate::paths;
use crate::state::InstallState;
use crate::sys;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct FolderInfo {
    pub path: String,
    /// Free bytes on the folder's drive.
    pub free_bytes: u64,
    /// Bytes to download into this folder (files already there with the right size count as present).
    pub needed_bytes: u64,
    /// Holds a WoW client already (`Data/common.MPQ` or `Wow.exe`).
    pub has_game: bool,
    pub writable: bool,
}

/// Facts about `path` (which need not exist yet).
pub fn folder_info(path: &Path, manifest: Option<&Manifest>) -> FolderInfo {
    FolderInfo {
        path: path.display().to_string(),
        free_bytes: sys::free_space(path).unwrap_or(0),
        needed_bytes: manifest.map(|m| needed_bytes(m, path)).unwrap_or(0),
        has_game: has_game(path),
        writable: is_writable(path),
    }
}

/// Sum of manifest sizes not already present with the right size.
pub fn needed_bytes(m: &Manifest, dir: &Path) -> u64 {
    m.files
        .iter()
        .filter(|f| {
            let present = paths::safe_join(dir, &f.p)
                .ok()
                .and_then(|p| fs::metadata(p).ok())
                .is_some_and(|meta| meta.is_file() && (f.once || meta.len() == f.s));
            !present
        })
        .map(|f| f.s)
        .sum()
}

pub fn has_game(dir: &Path) -> bool {
    dir.join("Data").join("common.MPQ").is_file() || dir.join("Wow.exe").is_file()
}

/// Whether files can be created in `dir` (or, when it does not exist yet, folders in its nearest
/// existing parent). Leaves nothing behind.
pub fn is_writable(dir: &Path) -> bool {
    let pid = std::process::id();
    if dir.is_dir() {
        let probe = dir.join(format!(".bleakhold-probe-{pid}"));
        let ok = fs::write(&probe, b"").is_ok();
        let _ = fs::remove_file(&probe);
        ok
    } else if dir.exists() {
        false
    } else {
        match sys::nearest_existing(dir) {
            Some(parent) if parent.is_dir() => {
                let probe = parent.join(format!(".bleakhold-probe-{pid}"));
                let ok = fs::create_dir(&probe).is_ok();
                let _ = fs::remove_dir(&probe);
                ok
            }
            _ => false,
        }
    }
}

/// The folder `install` uses for a path the player chose (see [`resolve_install_dir`]): the path must be a
/// full one, and the result must not be a file.
pub fn install_dir_for(path: &str) -> Result<PathBuf> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err(Error::io_msg("Choose a folder for the game."));
    }
    let p = PathBuf::from(trimmed);
    if !p.is_absolute() {
        return Err(Error::io_msg("Choose a full folder path, like C:\\Games\\Bleakhold."));
    }
    let dir = resolve_install_dir(&p);
    if dir.exists() && !dir.is_dir() {
        return Err(Error::io_msg(format!("{} is a file, not a folder.", dir.display())));
    }
    Ok(dir)
}

/// The folder `install` really uses for a chosen `path`: the path itself, except that a whole drive, or a
/// folder which already holds other things (not empty, no WoW client, no Bleakhold install, not itself
/// named `Bleakhold`), gets a `Bleakhold` subfolder, so the game never spreads over someone's own files.
/// Applying it twice gives the same path.
pub fn resolve_install_dir(path: &Path) -> PathBuf {
    if path.parent().is_none() {
        return path.join("Bleakhold");
    }
    let named_bleakhold = path.file_name().is_some_and(|n| n.to_string_lossy().eq_ignore_ascii_case("Bleakhold"));
    let non_empty = fs::read_dir(path).map(|mut rd| rd.next().is_some()).unwrap_or(false);
    if path.is_dir() && non_empty && !named_bleakhold && !has_game(path) && !InstallState::exists(path) {
        path.join("Bleakhold")
    } else {
        path.to_path_buf()
    }
}

/// Suggested install folder: `<system drive>\Games\Bleakhold` when it can be created, else
/// `%USERPROFILE%\Games\Bleakhold` (on other systems `~/Games/Bleakhold`).
pub fn default_install_dir() -> PathBuf {
    #[cfg(windows)]
    {
        let drive = std::env::var("SystemDrive").unwrap_or_else(|_| "C:".into());
        let system = PathBuf::from(format!("{drive}\\")).join("Games").join("Bleakhold");
        if is_writable(&system) {
            return system;
        }
        let home = std::env::var_os("USERPROFILE").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
        home.join("Games").join("Bleakhold")
    }
    #[cfg(not(windows))]
    {
        let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
        home.join("Games").join("Bleakhold")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::download::sha256_hex;

    #[test]
    fn info_of_new_and_existing_folders() {
        let dir = std::env::temp_dir().join(format!("bh-folder-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        let h = sha256_hex(b"abc");
        let m = Manifest::parse(
            format!(
                r#"{{"format":1,"realmlist":"x","exe":"Wow.exe","files":[
                {{"p":"Wow.exe","s":3,"h":"{h}"}},{{"p":"Data/common.MPQ","s":10,"h":"{h}"}},
                {{"p":"WTF/Config.wtf","s":99,"h":"{h}","once":true}}]}}"#
            )
            .as_bytes(),
        )
        .unwrap();

        let i = folder_info(&dir.join("new"), Some(&m));
        assert!(!i.has_game && i.writable && i.free_bytes > 0);
        assert_eq!(i.needed_bytes, 112);
        assert!(!dir.exists(), "probing must not create the folder");

        fs::create_dir_all(dir.join("Data")).unwrap();
        fs::create_dir_all(dir.join("WTF")).unwrap();
        fs::write(dir.join("Wow.exe"), b"xyz").unwrap();
        fs::write(dir.join("Data/common.MPQ"), b"short").unwrap();
        fs::write(dir.join("WTF/Config.wtf"), b"mine").unwrap();
        let i = folder_info(&dir, Some(&m));
        assert!(i.has_game && i.writable);
        assert_eq!(i.needed_bytes, 10);
        assert_eq!(folder_info(&dir, None).needed_bytes, 0);
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 3, "no probe left behind");
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn install_dir_rules() {
        assert!(install_dir_for("").is_err());
        assert!(install_dir_for("relative/dir").is_err());
        #[cfg(unix)]
        {
            assert_eq!(install_dir_for("/").unwrap(), PathBuf::from("/Bleakhold"));
            assert_eq!(install_dir_for("/tmp/x/Bleakhold ").unwrap(), PathBuf::from("/tmp/x/Bleakhold"));
            let f = std::env::temp_dir().join(format!("bh-file-{}", std::process::id()));
            fs::write(&f, b"").unwrap();
            assert!(install_dir_for(f.to_str().unwrap()).unwrap_err().message.contains("is a file"));
            fs::remove_file(&f).unwrap();
        }
        assert!(default_install_dir().ends_with("Bleakhold"));
    }

    #[test]
    fn resolves_the_folder_install_uses() {
        let dir = std::env::temp_dir().join(format!("bh-resolve-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        // Missing or empty: as chosen.
        assert_eq!(resolve_install_dir(&dir.join("New")), dir.join("New"));
        fs::create_dir_all(dir.join("Empty")).unwrap();
        assert_eq!(resolve_install_dir(&dir.join("Empty")), dir.join("Empty"));
        // Someone's own files: a Bleakhold subfolder, and resolving that again keeps it.
        fs::create_dir_all(dir.join("Games/Other")).unwrap();
        let r = resolve_install_dir(&dir.join("Games"));
        assert_eq!(r, dir.join("Games/Bleakhold"));
        fs::create_dir_all(dir.join("Games/Bleakhold/junk")).unwrap();
        assert_eq!(resolve_install_dir(&r), r);
        // A WoW client or an earlier Bleakhold install: as chosen.
        fs::create_dir_all(dir.join("WoW")).unwrap();
        fs::write(dir.join("WoW/Wow.exe"), b"x").unwrap();
        assert_eq!(resolve_install_dir(&dir.join("WoW")), dir.join("WoW"));
        fs::create_dir_all(dir.join("Mine/.bleakhold")).unwrap();
        fs::write(dir.join("Mine/.bleakhold/state.json"), b"{}").unwrap();
        assert_eq!(resolve_install_dir(&dir.join("Mine")), dir.join("Mine"));
        fs::remove_dir_all(&dir).unwrap();
    }
}
