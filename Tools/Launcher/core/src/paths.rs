//! Path rules (DESIGN.md "Manifest"): what a manifest may name, and the only way the launcher turns such
//! a name into a place on disk. Every write and delete goes through [`prepare_write`] or [`safe_join`],
//! so nothing is ever written outside the install folder, whatever the manifest or the state file says.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use crate::error::{Error, Result};

/// The launcher's own folder inside the install folder (`state.json`).
pub const STATE_DIR: &str = ".bleakhold";
/// The copy of the launcher the install keeps (shortcuts point to it).
pub const LAUNCHER_COPY: &str = "Bleakhold Launcher.exe";
/// Suffix of a partly downloaded file.
pub const PART_SUFFIX: &str = ".part";

const MAX_PATH_LEN: usize = 400;

/// Checks one manifest path (`p`): relative, `/`-separated, no empty, `.` or `..` component, no `\`, no
/// drive letter, no control character, no character Windows forbids in a name (`<>:"|?*`, which also
/// rules out alternate data streams), no component ending in a dot or a space (Windows drops those, so
/// two names could mean one file), and no Windows reserved device name, with or without extension.
pub fn validate_rel_path(p: &str) -> std::result::Result<(), String> {
    if p.is_empty() {
        return Err("empty path".into());
    }
    if p.len() > MAX_PATH_LEN {
        return Err(format!("path longer than {MAX_PATH_LEN} bytes"));
    }
    if p.chars().any(char::is_control) {
        return Err("control character in path".into());
    }
    if p.contains('\\') {
        return Err("backslash in path".into());
    }
    if p.starts_with('/') {
        return Err("absolute path".into());
    }
    let b = p.as_bytes();
    if b.len() >= 2 && b[0].is_ascii_alphabetic() && b[1] == b':' {
        return Err("drive letter in path".into());
    }
    for comp in p.split('/') {
        validate_component(comp)?;
    }
    Ok(())
}

fn validate_component(comp: &str) -> std::result::Result<(), String> {
    if comp.is_empty() {
        return Err("empty path component".into());
    }
    if comp == "." || comp == ".." {
        return Err(format!("'{comp}' component"));
    }
    if let Some(c) = comp.chars().find(|c| matches!(c, '<' | '>' | ':' | '"' | '|' | '?' | '*')) {
        return Err(format!("character '{c}' is not allowed in a file name"));
    }
    if comp.ends_with('.') || comp.ends_with(' ') {
        return Err(format!("'{comp}' ends with a dot or a space"));
    }
    if is_reserved_name(comp) {
        return Err(format!("'{comp}' is a reserved Windows name"));
    }
    Ok(())
}

/// `CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9` (and the superscript digits Windows also
/// reserves), with or without an extension, in any case.
pub fn is_reserved_name(comp: &str) -> bool {
    let stem = comp.split('.').next().unwrap_or("").trim_end_matches(' ');
    let upper = stem.to_uppercase();
    match upper.as_str() {
        "CON" | "PRN" | "AUX" | "NUL" => true,
        _ => {
            let mut chars = upper.chars();
            let head: String = chars.by_ref().take(3).collect();
            let rest: Vec<char> = chars.collect();
            (head == "COM" || head == "LPT")
                && rest.len() == 1
                && matches!(rest[0], '1'..='9' | '\u{b9}' | '\u{b2}' | '\u{b3}')
        }
    }
}

/// Names the launcher keeps for itself: its state folder, its own copy and partial downloads.
pub fn is_launcher_owned(p: &str) -> bool {
    let lower = p.to_lowercase();
    let first = lower.split('/').next().unwrap_or("");
    first == STATE_DIR
        || lower == LAUNCHER_COPY.to_lowercase()
        || lower == "bleakhold launcher.old.exe"
        || lower.ends_with(PART_SUFFIX)
}

/// Checks a whole list of manifest paths: every path valid, none owned by the launcher, no two equal
/// when case is ignored, and no file also used as a folder by another entry (`Data` and `Data/x`).
pub fn validate_path_set<'a>(paths: impl IntoIterator<Item = &'a str>) -> std::result::Result<(), String> {
    let mut files: HashSet<String> = HashSet::new();
    let mut dirs: HashSet<String> = HashSet::new();
    for p in paths {
        validate_rel_path(p).map_err(|e| format!("{p:?}: {e}"))?;
        if is_launcher_owned(p) {
            return Err(format!("{p:?}: the launcher keeps this name for itself"));
        }
        let lower = p.to_lowercase();
        if !files.insert(lower.clone()) {
            return Err(format!("{p:?}: listed twice (names differ only by case)"));
        }
        let mut acc = String::new();
        let comps: Vec<&str> = lower.split('/').collect();
        for comp in &comps[..comps.len() - 1] {
            if !acc.is_empty() {
                acc.push('/');
            }
            acc.push_str(comp);
            dirs.insert(acc.clone());
        }
    }
    if let Some(clash) = files.iter().find(|f| dirs.contains(*f)) {
        return Err(format!("{clash:?} is both a file and a folder"));
    }
    Ok(())
}

/// Joins a validated relative path onto `root`, component by component.
pub fn safe_join(root: &Path, rel: &str) -> Result<PathBuf> {
    validate_rel_path(rel).map_err(|e| Error::io_msg(format!("refusing path {rel:?}: {e}")))?;
    let mut out = root.to_path_buf();
    for comp in rel.split('/') {
        out.push(comp);
    }
    Ok(out)
}

/// The path to write `rel` to: validated, its folders created, and its parent folder checked to really
/// lie inside `root` once links and junctions are resolved.
pub fn prepare_write(root: &Path, rel: &str) -> Result<PathBuf> {
    let target = safe_join(root, rel)?;
    let parent = target.parent().unwrap_or(root);
    fs::create_dir_all(parent).map_err(|e| Error::io(format!("creating {}", parent.display()), &e))?;
    ensure_inside(root, parent)?;
    Ok(target)
}

/// Fails unless `path` (which must exist) resolves to `root` or a place below it.
pub fn ensure_inside(root: &Path, path: &Path) -> Result<()> {
    let croot = fs::canonicalize(root).map_err(|e| Error::io(format!("opening {}", root.display()), &e))?;
    let cpath = fs::canonicalize(path).map_err(|e| Error::io(format!("opening {}", path.display()), &e))?;
    if cpath.starts_with(&croot) {
        Ok(())
    } else {
        Err(Error::io_msg(format!("refusing to write {}: it leads outside the install folder", path.display())))
    }
}

/// `<path>.part`.
pub fn part_path(target: &Path) -> PathBuf {
    let mut s = target.as_os_str().to_owned();
    s.push(PART_SUFFIX);
    PathBuf::from(s)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_ordinary_paths() {
        for p in [
            "Data/common.MPQ",
            "Wow.exe",
            "Data/enUS/patch-enUS-3.MPQ",
            "Interface/AddOns/Bleakhold/Bleakhold.toc",
            "Data/Interface/Bleakhold/Dances/Music/a b.mp3",
            "WTF/Config.wtf",
            ".hidden/file",
            "Tools/BleakholdRaceForge.exe",
            "CONSOLE.txt",
            "COM10.txt",
            "Données/ü.txt",
        ] {
            assert_eq!(validate_rel_path(p), Ok(()), "{p}");
        }
    }

    #[test]
    fn rejects_every_rule() {
        let bad = [
            ("", "empty"),
            ("/etc/passwd", "absolute"),
            ("C:/Windows/x", "drive"),
            ("c:x", "drive"),
            ("Data\\common.MPQ", "backslash"),
            ("Data/../x", "'..'"),
            ("../x", "'..'"),
            ("Data/./x", "'.'"),
            (".", "'.'"),
            ("Data//x", "empty path component"),
            ("Data/", "empty path component"),
            ("Data/x\u{0}", "control"),
            ("Data/x\ny", "control"),
            ("Data/x\u{7f}", "control"),
            ("CON", "reserved"),
            ("con.txt", "reserved"),
            ("Data/Nul.MPQ", "reserved"),
            ("aux", "reserved"),
            ("PRN.tar.gz", "reserved"),
            ("COM1", "reserved"),
            ("lpt9.log", "reserved"),
            ("COM\u{b9}", "reserved"),
            ("NUL .txt", "reserved"),
            ("Data/x:stream", "not allowed"),
            ("Data/a*b", "not allowed"),
            ("Data/a?b", "not allowed"),
            ("Data/a\"b", "not allowed"),
            ("Data/a<b", "not allowed"),
            ("Data/a|b", "not allowed"),
            ("Data/name.", "dot or a space"),
            ("Data/name ", "dot or a space"),
            ("Data /x", "dot or a space"),
        ];
        for (p, why) in bad {
            let err = validate_rel_path(p).expect_err(p);
            assert!(err.contains(why), "{p:?}: {err} (expected {why})");
        }
        assert!(validate_rel_path(&"a/".repeat(300)).is_err());
    }

    #[test]
    fn reserved_names() {
        assert!(is_reserved_name("CON"));
        assert!(is_reserved_name("com5.dat"));
        assert!(is_reserved_name("Lpt3"));
        assert!(!is_reserved_name("COM0"));
        assert!(!is_reserved_name("COM"));
        assert!(!is_reserved_name("CONX"));
        assert!(!is_reserved_name("x.CON"));
    }

    #[test]
    fn path_sets() {
        assert_eq!(validate_path_set(["a/b", "a/c", "d"]), Ok(()));
        let e = validate_path_set(["Data/common.MPQ", "data/COMMON.mpq"]).unwrap_err();
        assert!(e.contains("twice"), "{e}");
        let e = validate_path_set(["Data", "Data/x"]).unwrap_err();
        assert!(e.contains("both a file and a folder"), "{e}");
        let e = validate_path_set(["data/x/y", "DATA/X"]).unwrap_err();
        assert!(e.contains("both a file and a folder"), "{e}");
        for owned in [".bleakhold/state.json", ".BleakHold/x", "Bleakhold Launcher.exe", "Data/x.MPQ.part"] {
            let e = validate_path_set([owned]).unwrap_err();
            assert!(e.contains("keeps this name"), "{owned}: {e}");
        }
        assert!(validate_path_set(["ok", "../bad"]).is_err());
    }

    #[test]
    fn join_and_prepare_stay_inside() {
        let dir = std::env::temp_dir().join(format!("bh-paths-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        let t = prepare_write(&dir, "Data/enUS/x.txt").unwrap();
        assert_eq!(t, dir.join("Data").join("enUS").join("x.txt"));
        assert!(dir.join("Data/enUS").is_dir());
        assert!(safe_join(&dir, "../x").is_err());
        assert!(prepare_write(&dir, "/abs").is_err());
        assert_eq!(part_path(&t), dir.join("Data/enUS/x.txt.part"));

        #[cfg(unix)]
        {
            let outside = std::env::temp_dir().join(format!("bh-paths-out-{}", std::process::id()));
            fs::create_dir_all(&outside).unwrap();
            std::os::unix::fs::symlink(&outside, dir.join("Link")).unwrap();
            let err = prepare_write(&dir, "Link/evil.txt").unwrap_err();
            assert!(err.message.contains("outside"), "{err}");
            fs::remove_dir_all(&outside).unwrap();
        }
        fs::remove_dir_all(&dir).unwrap();
    }
}
