//! What depends on the operating system: free disk space, whether the game is running, waiting for a
//! process, the per-user config folder and how I/O errors read. Windows code is behind `cfg(windows)`;
//! elsewhere there are harmless stand-ins so the engine still runs and tests on Linux.

use std::io;
use std::path::{Path, PathBuf};
use std::time::Duration;

/// Bytes free for the current user on the volume holding `path` (or its nearest existing parent).
pub fn free_space(path: &Path) -> Option<u64> {
    let existing = nearest_existing(path)?;
    imp::free_space(&existing)
}

/// The path itself or the closest parent folder that exists.
pub fn nearest_existing(path: &Path) -> Option<PathBuf> {
    let mut p = Some(path);
    while let Some(cur) = p {
        if cur.exists() {
            return Some(cur.to_path_buf());
        }
        p = cur.parent();
    }
    None
}

/// Whether a process whose executable file is named `exe_name` (case ignored) is running.
pub fn is_process_running(exe_name: &str) -> bool {
    imp::is_process_running(exe_name)
}

/// Waits (at most `timeout`) for process `pid` to end. Used by a freshly updated launcher, so the old
/// one has let go of the single-instance lock before the new one starts its window.
pub fn wait_for_pid(pid: u32, timeout: Duration) {
    imp::wait_for_pid(pid, timeout)
}

/// The disk (or the user's quota) is full.
pub fn is_disk_full(e: &io::Error) -> bool {
    matches!(e.raw_os_error(), Some(code) if imp::DISK_FULL.contains(&code))
}

/// Another program holds the file (on Windows: sharing or lock violation, or a mapped section).
pub fn is_in_use(e: &io::Error) -> bool {
    matches!(e.raw_os_error(), Some(code) if imp::IN_USE.contains(&code))
}

/// `%APPDATA%\Bleakhold Launcher` on Windows; `$XDG_CONFIG_HOME/bleakhold-launcher` (or
/// `~/.config/bleakhold-launcher`) elsewhere.
pub fn config_dir() -> PathBuf {
    #[cfg(windows)]
    {
        let base = std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("USERPROFILE").map(|h| PathBuf::from(h).join("AppData").join("Roaming")))
            .unwrap_or_else(std::env::temp_dir);
        base.join("Bleakhold Launcher")
    }
    #[cfg(not(windows))]
    {
        let base = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".config")))
            .unwrap_or_else(std::env::temp_dir);
        base.join("bleakhold-launcher")
    }
}

/// Whether two paths name the same file (resolved, case ignored on Windows).
pub fn same_file(a: &Path, b: &Path) -> bool {
    match (std::fs::canonicalize(a), std::fs::canonicalize(b)) {
        (Ok(x), Ok(y)) => {
            if cfg!(windows) {
                x.to_string_lossy().to_lowercase() == y.to_string_lossy().to_lowercase()
            } else {
                x == y
            }
        }
        _ => false,
    }
}

#[cfg(windows)]
mod imp {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use std::path::Path;
    use std::time::Duration;

    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW;
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS,
    };
    use windows_sys::Win32::System::Threading::{OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE};

    /// ERROR_HANDLE_DISK_FULL, ERROR_DISK_FULL, ERROR_DISK_QUOTA_EXCEEDED.
    pub const DISK_FULL: &[i32] = &[39, 112, 1295];
    /// ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION, ERROR_USER_MAPPED_FILE.
    pub const IN_USE: &[i32] = &[32, 33, 1224];

    fn wide(s: &OsStr) -> Vec<u16> {
        s.encode_wide().chain(std::iter::once(0)).collect()
    }

    pub fn free_space(path: &Path) -> Option<u64> {
        let w = wide(path.as_os_str());
        let mut free: u64 = 0;
        // SAFETY: `w` is NUL-terminated and outlives the call; the out pointers are valid or null.
        let ok = unsafe { GetDiskFreeSpaceExW(w.as_ptr(), &mut free, std::ptr::null_mut(), std::ptr::null_mut()) };
        if ok != 0 {
            Some(free)
        } else {
            None
        }
    }

    pub fn is_process_running(exe_name: &str) -> bool {
        let want = exe_name.to_lowercase();
        // SAFETY: plain Win32 calls; the snapshot handle is closed on every path, the entry is sized.
        unsafe {
            let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
            if snap == INVALID_HANDLE_VALUE || snap.is_null() {
                return false;
            }
            let mut entry: PROCESSENTRY32W = std::mem::zeroed();
            entry.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
            let mut found = false;
            let mut ok = Process32FirstW(snap, &mut entry);
            while ok != 0 {
                let len = entry.szExeFile.iter().position(|&c| c == 0).unwrap_or(entry.szExeFile.len());
                let name = String::from_utf16_lossy(&entry.szExeFile[..len]);
                if name.to_lowercase() == want {
                    found = true;
                    break;
                }
                ok = Process32NextW(snap, &mut entry);
            }
            CloseHandle(snap);
            found
        }
    }

    pub fn wait_for_pid(pid: u32, timeout: Duration) {
        // SAFETY: the handle is checked and closed; waiting on a process handle has no other effect.
        unsafe {
            let h = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid);
            if h.is_null() {
                return;
            }
            WaitForSingleObject(h, timeout.as_millis().min(u32::MAX as u128) as u32);
            CloseHandle(h);
        }
    }
}

#[cfg(not(windows))]
mod imp {
    use std::path::Path;
    use std::time::{Duration, Instant};

    #[cfg(unix)]
    pub const DISK_FULL: &[i32] = &[libc::ENOSPC, libc::EDQUOT];
    #[cfg(unix)]
    pub const IN_USE: &[i32] = &[libc::ETXTBSY];
    #[cfg(not(unix))]
    pub const DISK_FULL: &[i32] = &[];
    #[cfg(not(unix))]
    pub const IN_USE: &[i32] = &[];

    #[cfg(unix)]
    pub fn free_space(path: &Path) -> Option<u64> {
        use std::ffi::CString;
        use std::os::unix::ffi::OsStrExt;
        let c = CString::new(path.as_os_str().as_bytes()).ok()?;
        // SAFETY: `c` is a valid C string; `st` is plain data the call fills in.
        unsafe {
            let mut st: libc::statvfs = std::mem::zeroed();
            if libc::statvfs(c.as_ptr(), &mut st) == 0 {
                Some((st.f_bavail as u64).saturating_mul(st.f_frsize as u64))
            } else {
                None
            }
        }
    }

    #[cfg(not(unix))]
    pub fn free_space(_path: &Path) -> Option<u64> {
        None
    }

    /// The game only runs on Windows.
    pub fn is_process_running(_exe_name: &str) -> bool {
        false
    }

    pub fn wait_for_pid(pid: u32, timeout: Duration) {
        let end = Instant::now() + timeout;
        let proc_dir = std::path::PathBuf::from(format!("/proc/{pid}"));
        while proc_dir.exists() && Instant::now() < end {
            std::thread::sleep(Duration::from_millis(50));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn free_space_of_temp() {
        let deep = std::env::temp_dir().join("does/not/exist/yet");
        assert_eq!(nearest_existing(&deep).unwrap(), std::env::temp_dir());
        assert!(free_space(&deep).unwrap() > 0);
    }

    #[cfg(windows)]
    #[test]
    fn finds_its_own_process_by_name() {
        let exe = std::env::current_exe().unwrap();
        let name = exe.file_name().unwrap().to_string_lossy().to_uppercase();
        assert!(is_process_running(&name), "{name}");
    }

    #[test]
    fn errors_that_mean_in_use_or_full() {
        #[cfg(windows)]
        {
            assert!(is_in_use(&io::Error::from_raw_os_error(32)));
            assert!(is_disk_full(&io::Error::from_raw_os_error(112)));
        }
        assert!(!is_in_use(&io::Error::other("x")));
        assert!(!is_disk_full(&io::Error::other("x")));
    }

    #[test]
    fn same_file_and_config_dir() {
        let t = std::env::temp_dir();
        assert!(same_file(&t, &t.join(".")));
        assert!(!same_file(&t, &t.join("nope-not-here")));
        assert!(config_dir().ends_with("bleakhold-launcher") || config_dir().ends_with("Bleakhold Launcher"));
    }

    #[test]
    fn wait_for_a_finished_process_returns() {
        let mut child = std::process::Command::new(std::env::current_exe().unwrap())
            .arg("--list")
            .stdout(std::process::Stdio::null())
            .spawn()
            .unwrap();
        let pid = child.id();
        child.wait().unwrap();
        let t = std::time::Instant::now();
        wait_for_pid(pid, Duration::from_secs(5));
        assert!(t.elapsed() < Duration::from_secs(5));
        assert!(!is_process_running("Bleakhold-no-such-process.exe"));
    }
}
