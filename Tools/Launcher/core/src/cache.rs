//! The game's `Cache/` folder: emptied when the manifest's `cache_epoch` differs from the one stored in
//! the state (before the next start), or when the player asks.

use std::fs;
use std::path::Path;

use crate::error::{Error, Result};
use crate::state::InstallState;

/// Empties `<install>/Cache` (keeps the folder). A link in its place is removed, never followed.
pub fn clear_cache(install: &Path) -> Result<()> {
    let cache = install.join("Cache");
    let meta = match fs::symlink_metadata(&cache) {
        Ok(m) => m,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(Error::io(format!("reading {}", cache.display()), &e)),
    };
    if meta.file_type().is_symlink() || !meta.is_dir() {
        return remove_any(&cache);
    }
    let rd = fs::read_dir(&cache).map_err(|e| Error::io(format!("reading {}", cache.display()), &e))?;
    for entry in rd {
        let entry = entry.map_err(|e| Error::io(format!("reading {}", cache.display()), &e))?;
        remove_any(&entry.path())?;
    }
    Ok(())
}

fn remove_any(p: &Path) -> Result<()> {
    let meta = fs::symlink_metadata(p).map_err(|e| Error::io(format!("reading {}", p.display()), &e))?;
    let res = if meta.is_dir() && !meta.file_type().is_symlink() {
        fs::remove_dir_all(p)
    } else {
        fs::remove_file(p).or_else(|_| fs::remove_dir(p))
    };
    res.map_err(|e| Error::io(format!("removing {}", p.display()), &e))
}

/// Empties the cache when `epoch` differs from the state's and records the new epoch. Returns whether
/// it emptied the cache. The caller saves the state.
pub fn apply_epoch(install: &Path, state: &mut InstallState, epoch: u64) -> Result<bool> {
    if state.cache_epoch == epoch {
        return Ok(false);
    }
    clear_cache(install)?;
    log::info!("cache epoch {} -> {epoch}: emptied Cache/", state.cache_epoch);
    state.cache_epoch = epoch;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn epoch_empties_cache_once() {
        let dir = std::env::temp_dir().join(format!("bh-cache-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(dir.join("Cache/WDB/enUS")).unwrap();
        fs::write(dir.join("Cache/WDB/enUS/itemcache.wdb"), b"x").unwrap();
        fs::write(dir.join("Cache/top.bin"), b"x").unwrap();
        fs::write(dir.join("keep.txt"), b"x").unwrap();
        let mut st = InstallState { cache_epoch: 1, ..Default::default() };
        assert!(!apply_epoch(&dir, &mut st, 1).unwrap());
        assert!(dir.join("Cache/top.bin").exists());
        assert!(apply_epoch(&dir, &mut st, 2).unwrap());
        assert_eq!(st.cache_epoch, 2);
        assert!(dir.join("Cache").is_dir());
        assert_eq!(fs::read_dir(dir.join("Cache")).unwrap().count(), 0);
        assert!(dir.join("keep.txt").exists());
        assert!(!apply_epoch(&dir, &mut st, 2).unwrap());
        fs::remove_dir_all(dir.join("Cache")).unwrap();
        clear_cache(&dir).unwrap();

        #[cfg(unix)]
        {
            let outside = std::env::temp_dir().join(format!("bh-cache-out-{}", std::process::id()));
            fs::create_dir_all(&outside).unwrap();
            fs::write(outside.join("precious"), b"x").unwrap();
            std::os::unix::fs::symlink(&outside, dir.join("Cache")).unwrap();
            clear_cache(&dir).unwrap();
            assert!(outside.join("precious").exists());
            assert!(fs::symlink_metadata(dir.join("Cache")).is_err());
            fs::remove_dir_all(&outside).unwrap();
        }
        fs::remove_dir_all(&dir).unwrap();
    }
}
