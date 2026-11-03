//! Starting the game: only the verified game executable, with the install folder as working directory.

use std::fs;
use std::path::Path;
use std::process::{Child, Command};

use crate::download::hash_file;
use crate::error::{Error, Result};
use crate::paths;
use crate::state::InstallState;
use crate::util::mtime_ns;

/// Checks that `<install>/<exe>` is the file the launcher verified: its size and modification time match
/// the state entry, or else its SHA-256 equals `expected_hash` (the manifest's, or the state's offline).
pub fn verify_exe(install: &Path, exe: &str, state: &InstallState, expected_hash: &str) -> Result<()> {
    let path = paths::safe_join(install, exe)?;
    let meta = fs::metadata(&path)
        .map_err(|_| Error::launch(format!("{exe} is missing. Use \"Check & repair files\" to restore it.")))?;
    if let Some(e) = state.files.get(exe) {
        if e.h == expected_hash && e.size == meta.len() && e.mtime == mtime_ns(&meta) {
            return Ok(());
        }
    }
    let h = hash_file(&path, &|| false, &mut |_| {})?;
    if h == expected_hash {
        Ok(())
    } else {
        Err(Error::launch(format!("{exe} is not the realm's game file. Use \"Check & repair files\" to restore it.")))
    }
}

/// Starts `<install>/<exe>` in `install`.
pub fn start_game(install: &Path, exe: &str) -> Result<Child> {
    let path = paths::safe_join(install, exe)?;
    let mut cmd = Command::new(&path);
    cmd.current_dir(install);
    cmd.spawn().map_err(|e| Error::launch(format!("The game could not be started: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::download::sha256_hex;
    use crate::state::FileState;

    #[test]
    fn verifies_by_state_or_hash() {
        let dir = std::env::temp_dir().join(format!("bh-launch-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("Game.exe"), b"game").unwrap();
        let h = sha256_hex(b"game");
        let mut st = InstallState::default();
        verify_exe(&dir, "Game.exe", &st, &h).unwrap();
        assert!(verify_exe(&dir, "Game.exe", &st, &sha256_hex(b"other")).is_err());
        let meta = fs::metadata(dir.join("Game.exe")).unwrap();
        st.record(FileState { p: "Game.exe".into(), s: 4, h: h.clone(), size: 4, mtime: mtime_ns(&meta), once: false });
        verify_exe(&dir, "Game.exe", &st, &h).unwrap();
        // Replaced with a same-size file: the modification time differs, so it is hashed and refused.
        fs::write(dir.join("Game.exe"), b"evil").unwrap();
        let f = fs::File::options().write(true).open(dir.join("Game.exe")).unwrap();
        f.set_modified(std::time::UNIX_EPOCH + std::time::Duration::from_secs(1_000_000)).unwrap();
        drop(f);
        assert_eq!(verify_exe(&dir, "Game.exe", &st, &h).unwrap_err().code, crate::Code::Launch);
        assert!(verify_exe(&dir, "Missing.exe", &st, &h).is_err());
        assert!(verify_exe(&dir, "../x.exe", &st, &h).is_err());
        fs::remove_dir_all(&dir).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn starts_in_the_install_folder() {
        use std::os::unix::fs::PermissionsExt;
        let dir = std::env::temp_dir().join(format!("bh-start-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("game.sh"), "#!/bin/sh\npwd > started.txt\n").unwrap();
        fs::set_permissions(dir.join("game.sh"), fs::Permissions::from_mode(0o755)).unwrap();
        let status = start_game(&dir, "game.sh").unwrap().wait().unwrap();
        assert!(status.success());
        let pwd = fs::read_to_string(dir.join("started.txt")).unwrap();
        assert_eq!(fs::canonicalize(pwd.trim()).unwrap(), fs::canonicalize(&dir).unwrap());
        assert_eq!(start_game(&dir, "missing.exe").unwrap_err().code, crate::Code::Launch);
        fs::remove_dir_all(&dir).unwrap();
    }
}
