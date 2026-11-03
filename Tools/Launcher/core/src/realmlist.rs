//! Realmlist (DESIGN.md "Update rules" 7): `set realmlist <host>` into `Data/<xxYY>/realmlist.wtf` for
//! every locale folder, and `SET realmList "<host>"` in `WTF/Config.wtf`, where only that line is
//! created or replaced and everything else is kept byte for byte.

use std::fs;
use std::path::Path;

use crate::error::{Error, Result};
use crate::manifest::validate_host;
use crate::paths;
use crate::util::write_atomic;

/// `Data/<xxYY>` folders (`enUS`, `deDE`, …).
pub fn locale_dirs(install: &Path) -> Vec<String> {
    let mut out = Vec::new();
    if let Ok(rd) = fs::read_dir(install.join("Data")) {
        for e in rd.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if is_locale(&name) && e.file_type().is_ok_and(|t| t.is_dir()) {
                out.push(name);
            }
        }
    }
    out.sort();
    out
}

fn is_locale(name: &str) -> bool {
    let b = name.as_bytes();
    b.len() == 4
        && b[0].is_ascii_lowercase()
        && b[1].is_ascii_lowercase()
        && b[2].is_ascii_uppercase()
        && b[3].is_ascii_uppercase()
}

/// Writes both files. Returns the files written (relative paths).
pub fn apply(install: &Path, realmlist: &str) -> Result<Vec<String>> {
    validate_host(realmlist).map_err(|e| Error::launch(format!("realmlist {realmlist:?}: {e}")))?;
    let mut written = Vec::new();
    for loc in locale_dirs(install) {
        let rel = format!("Data/{loc}/realmlist.wtf");
        let path = paths::prepare_write(install, &rel)?;
        let text = format!("set realmlist {realmlist}\r\n");
        if fs::read(&path).ok().as_deref() != Some(text.as_bytes()) {
            write_file(&path, text.as_bytes())?;
        }
        written.push(rel);
    }
    let rel = "WTF/Config.wtf";
    let path = paths::prepare_write(install, rel)?;
    let old = match fs::read(&path) {
        Ok(b) => Some(b),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(Error::io(format!("reading {}", path.display()), &e)),
    };
    let new = set_config_realmlist(old.as_deref().unwrap_or(b""), realmlist);
    if old.as_deref() != Some(new.as_slice()) {
        write_file(&path, &new)?;
    }
    written.push(rel.to_string());
    Ok(written)
}

fn write_file(path: &Path, bytes: &[u8]) -> Result<()> {
    write_atomic(path, bytes).map_err(|e| Error::io(format!("writing {}", path.display()), &e))
}

/// `Config.wtf` text with every `SET realmList …` line (any case, any spacing) set to `realmlist`, or one
/// appended when there is none. Line endings of the file are kept (CRLF for a new file).
pub fn set_config_realmlist(text: &[u8], realmlist: &str) -> Vec<u8> {
    let crlf = text.is_empty() || text.windows(2).any(|w| w == b"\r\n");
    let nl: &[u8] = if crlf { b"\r\n" } else { b"\n" };
    let line = format!("SET realmList \"{realmlist}\"");
    let mut out = Vec::with_capacity(text.len() + line.len() + 2);
    let mut found = false;
    let mut rest = text;
    while !rest.is_empty() {
        let (content, ending, next) = match rest.iter().position(|&b| b == b'\n') {
            Some(i) => {
                let (c, e) = if i > 0 && rest[i - 1] == b'\r' {
                    (&rest[..i - 1], &rest[i - 1..=i])
                } else {
                    (&rest[..i], &rest[i..=i])
                };
                (c, e, &rest[i + 1..])
            }
            None => (rest, &b""[..], &b""[..]),
        };
        if is_realmlist_line(content) {
            out.extend_from_slice(line.as_bytes());
            found = true;
        } else {
            out.extend_from_slice(content);
        }
        out.extend_from_slice(ending);
        rest = next;
    }
    if !found {
        if !out.is_empty() && !out.ends_with(b"\n") {
            out.extend_from_slice(nl);
        }
        out.extend_from_slice(line.as_bytes());
        out.extend_from_slice(nl);
    }
    out
}

fn is_realmlist_line(line: &[u8]) -> bool {
    let s = String::from_utf8_lossy(line);
    let mut words = s.split_whitespace();
    matches!(
        (words.next(), words.next()),
        (Some(set), Some(name)) if set.eq_ignore_ascii_case("set") && name.eq_ignore_ascii_case("realmlist")
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn set(text: &str) -> String {
        String::from_utf8(set_config_realmlist(text.as_bytes(), "185.217.124.41")).unwrap()
    }

    #[test]
    fn config_wtf_line_only() {
        assert_eq!(set(""), "SET realmList \"185.217.124.41\"\r\n");
        assert_eq!(
            set("SET locale \"enUS\"\nSET realmList \"logon.old.org\"\nSET gxApi \"d3d9\"\n"),
            "SET locale \"enUS\"\nSET realmList \"185.217.124.41\"\nSET gxApi \"d3d9\"\n"
        );
        assert_eq!(
            set("SET locale \"enUS\"\r\nset   REALMLIST old\r\nSET realmName \"Bleakhold\"\r\n"),
            "SET locale \"enUS\"\r\nSET realmList \"185.217.124.41\"\r\nSET realmName \"Bleakhold\"\r\n"
        );
        assert_eq!(set("SET a \"1\""), "SET a \"1\"\nSET realmList \"185.217.124.41\"\n");
        assert_eq!(set("SET a \"1\"\r\n"), "SET a \"1\"\r\nSET realmList \"185.217.124.41\"\r\n");
        assert_eq!(set("SET realmListX \"x\"\n"), "SET realmListX \"x\"\nSET realmList \"185.217.124.41\"\n");
        assert_eq!(set("SET realmList \"185.217.124.41\""), "SET realmList \"185.217.124.41\"");
    }

    #[test]
    fn writes_locales_and_config() {
        let dir = std::env::temp_dir().join(format!("bh-realm-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        for d in ["Data/enUS", "Data/deDE", "Data/Interface", "Data/ENUS", "WTF"] {
            fs::create_dir_all(dir.join(d)).unwrap();
        }
        fs::write(dir.join("Data/enUS/realmlist.wtf"), "set realmlist logon.wow.com\n").unwrap();
        fs::write(dir.join("WTF/Config.wtf"), "SET gxWindow \"1\"\nSET realmList \"old\"\n").unwrap();
        let w = apply(&dir, "185.217.124.41").unwrap();
        assert_eq!(w, ["Data/deDE/realmlist.wtf", "Data/enUS/realmlist.wtf", "WTF/Config.wtf"]);
        for loc in ["enUS", "deDE"] {
            assert_eq!(
                fs::read_to_string(dir.join(format!("Data/{loc}/realmlist.wtf"))).unwrap(),
                "set realmlist 185.217.124.41\r\n"
            );
        }
        // Only `xxYY` names count (on a case-insensitive file system ENUS is the enUS folder itself).
        #[cfg(not(windows))]
        assert!(!dir.join("Data/ENUS/realmlist.wtf").exists());
        assert_eq!(
            fs::read_to_string(dir.join("WTF/Config.wtf")).unwrap(),
            "SET gxWindow \"1\"\nSET realmList \"185.217.124.41\"\n"
        );
        assert!(apply(&dir, "bad host\"").is_err());
        fs::remove_dir_all(&dir).unwrap();
    }
}
