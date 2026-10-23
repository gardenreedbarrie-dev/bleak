//! The launcher's own update (DESIGN.md "Update rules" 2): download the newer launcher next to the running
//! exe, check its SHA-256, rename the running exe to `<name>.old.exe` (Windows allows renaming a running
//! exe, not deleting it), move the new one into place and start it; every start deletes a leftover
//! `.old.exe`. Also keeps the install folder's copy of the launcher (`Bleakhold Launcher.exe`) current.

use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use crate::download::{self, Control, Dest, Options, Progress, Task};
use crate::error::{Error, Result};
use crate::http::Http;
use crate::manifest::{object_path, LauncherInfo};
use crate::paths::LAUNCHER_COPY;
use crate::sys;

/// The argument a freshly updated launcher gets, followed by the old launcher's process id.
pub const AFTER_UPDATE_ARG: &str = "--after-update";

fn sibling(exe: &Path, suffix: &str) -> PathBuf {
    let stem = exe.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_else(|| "launcher".into());
    exe.with_file_name(format!("{stem}{suffix}"))
}

/// `<dir>/<name>.old.exe`.
pub fn old_exe_path(exe: &Path) -> PathBuf {
    sibling(exe, ".old.exe")
}

/// `<dir>/<name>.new.exe` (the verified download before the swap).
pub fn new_exe_path(exe: &Path) -> PathBuf {
    sibling(exe, ".new.exe")
}

/// Deletes a leftover `.old.exe` (and a stale `.new.exe`) next to `exe`. Called at every start.
pub fn cleanup(exe: &Path) {
    for p in [old_exe_path(exe), new_exe_path(exe)] {
        if p.exists() {
            match fs::remove_file(&p) {
                Ok(()) => log::info!("removed {}", p.display()),
                Err(e) => log::warn!("could not remove {}: {e}", p.display()),
            }
        }
    }
}

/// Whether `remote` is a newer semver than `current` (unparsable versions are never newer).
pub fn is_newer(remote: &str, current: &str) -> bool {
    match (semver::Version::parse(remote), semver::Version::parse(current)) {
        (Ok(r), Ok(c)) => r > c,
        _ => false,
    }
}

/// Downloads the launcher object to `<name>.new.exe` (resumable `.part`, SHA-256 checked, `backoff` before
/// a retry) and returns that path.
pub fn download(
    http: &Http,
    objects: &str,
    info: &LauncherInfo,
    exe: &Path,
    ctl: &Control,
    backoff: Duration,
    on_progress: &mut dyn FnMut(&Progress),
) -> Result<PathBuf> {
    let target = new_exe_path(exe);
    let task = Task {
        url: http.url(&object_path(objects, &info.sha256)),
        dest: Dest::Path(target.clone()),
        size: info.size,
        sha256: info.sha256.clone(),
        label: format!("Bleakhold Launcher {}", info.version),
    };
    let opts = Options { parallel: 1, backoff, ..Options::default() };
    download::run(http, std::slice::from_ref(&task), &opts, ctl, on_progress, &mut |_, _| Ok(()))?;
    Ok(target)
}

/// Puts `new` in place of the running `exe`: `exe` → `<name>.old.exe`, `new` → `exe`. Puts the old one
/// back when the second step fails.
pub fn swap(exe: &Path, new: &Path) -> Result<()> {
    let old = old_exe_path(exe);
    if old.exists() {
        fs::remove_file(&old).map_err(|e| Error::io(format!("removing {}", old.display()), &e))?;
    }
    fs::rename(exe, &old).map_err(|e| Error::io(format!("moving {} aside", exe.display()), &e))?;
    if let Err(e) = fs::rename(new, exe) {
        let _ = fs::rename(&old, exe);
        return Err(Error::io(format!("putting the new launcher in place of {}", exe.display()), &e));
    }
    Ok(())
}

/// Starts `exe` (the verified new launcher) with `args` plus `--after-update <our pid>`.
pub fn restart(exe: &Path, args: &[OsString]) -> Result<()> {
    let mut cmd = Command::new(exe);
    cmd.args(args).arg(AFTER_UPDATE_ARG).arg(std::process::id().to_string());
    if let Some(dir) = exe.parent() {
        cmd.current_dir(dir);
    }
    cmd.spawn().map(|_| ()).map_err(|e| Error::launch(format!("starting the new launcher: {e}")))
}

/// Splits `--after-update <pid>` off the command line: `(pid, other args)`.
pub fn parse_args(args: impl IntoIterator<Item = OsString>) -> (Option<u32>, Vec<OsString>) {
    let mut pid = None;
    let mut rest = Vec::new();
    let mut it = args.into_iter();
    while let Some(a) = it.next() {
        if a == AFTER_UPDATE_ARG {
            pid = it.next().and_then(|p| p.to_str().and_then(|s| s.parse().ok()));
        } else {
            rest.push(a);
        }
    }
    (pid, rest)
}

/// `<install>/Bleakhold Launcher.exe`.
pub fn install_copy_path(install: &Path) -> PathBuf {
    install.join(LAUNCHER_COPY)
}

/// Copies the running launcher to `<install>/Bleakhold Launcher.exe` unless it already is that file or
/// the copy is identical. Returns the copy's path.
pub fn ensure_install_copy(current_exe: &Path, install: &Path) -> Result<PathBuf> {
    let copy = install_copy_path(install);
    if sys::same_file(current_exe, &copy) {
        return Ok(copy);
    }
    let src = fs::read(current_exe).map_err(|e| Error::io(format!("reading {}", current_exe.display()), &e))?;
    if fs::read(&copy).ok().is_some_and(|dst| dst == src) {
        return Ok(copy);
    }
    let tmp = sibling(&copy, ".exe.tmp");
    fs::create_dir_all(install).map_err(|e| Error::io(format!("creating {}", install.display()), &e))?;
    fs::write(&tmp, &src).map_err(|e| Error::io(format!("writing {}", tmp.display()), &e))?;
    if let Err(e) = download::rename_over(&tmp, &copy) {
        let _ = fs::remove_file(&tmp);
        return Err(Error::io(format!("writing {}", copy.display()), &e));
    }
    log::info!("copied the launcher to {}", copy.display());
    Ok(copy)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_and_versions() {
        let exe = Path::new("/x/Bleakhold Launcher.exe");
        assert_eq!(old_exe_path(exe), Path::new("/x/Bleakhold Launcher.old.exe"));
        assert_eq!(new_exe_path(exe), Path::new("/x/Bleakhold Launcher.new.exe"));
        assert_eq!(old_exe_path(Path::new("/x/BleakholdLauncher.exe")), Path::new("/x/BleakholdLauncher.old.exe"));
        assert!(is_newer("1.0.1", "1.0.0"));
        assert!(is_newer("1.10.0", "1.9.9"));
        assert!(!is_newer("1.0.0", "1.0.0"));
        assert!(!is_newer("1.0.0-beta", "1.0.0"));
        assert!(!is_newer("0.9.0", "1.0.0"));
        assert!(!is_newer("junk", "1.0.0"));
    }

    #[test]
    fn args() {
        let (pid, rest) = parse_args(["--x".into(), AFTER_UPDATE_ARG.into(), "42".into(), "y".into()]);
        assert_eq!(pid, Some(42));
        assert_eq!(rest, vec![OsString::from("--x"), OsString::from("y")]);
        assert_eq!(parse_args(Vec::<OsString>::new()), (None, vec![]));
    }
}
