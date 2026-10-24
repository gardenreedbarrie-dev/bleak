//! The launcher's own update, simulated with plain files: download and verify the new launcher, swap it
//! in (running exe → `.old.exe`), clean up on the next start, restart with the same arguments, and the
//! install folder's copy.

mod common;

use std::fs;
use std::time::Duration;

use bleakhold_launcher_core::download::{sha256_hex, Control};
use bleakhold_launcher_core::http::{Http, Timeouts};
use bleakhold_launcher_core::manifest::LauncherInfo;
use bleakhold_launcher_core::selfupdate;
use bleakhold_launcher_core::Code;
use common::*;

fn http(srv: &TestServer) -> Http {
    Http::new(&srv.base, "test", Timeouts { connect: Duration::from_secs(5), read: Duration::from_secs(5) })
}

#[test]
fn download_swap_and_cleanup() {
    let srv = TestServer::start();
    let dir = temp_dir("su-swap");
    let exe = dir.join("Bleakhold Launcher.exe");
    fs::write(&exe, b"launcher 1.0.0").unwrap();
    let new = bytes(1, 70_000);
    let info = LauncherInfo { version: "1.1.0".into(), size: new.len() as u64, sha256: srv.put_object(&new) };

    let mut last = None;
    let path = selfupdate::download(
        &http(&srv),
        "objects/",
        &info,
        &exe,
        &Control::new(),
        Duration::from_millis(10),
        &mut |p| last = Some(p.clone()),
    )
    .unwrap();
    assert_eq!(path, dir.join("Bleakhold Launcher.new.exe"));
    assert_eq!(read(&path), new);
    assert_eq!(last.unwrap().done_bytes, 70_000);

    selfupdate::swap(&exe, &path).unwrap();
    assert_eq!(read(&exe), new);
    assert_eq!(read(&dir.join("Bleakhold Launcher.old.exe")), b"launcher 1.0.0");
    assert!(!path.exists());

    // The next start removes the leftover.
    selfupdate::cleanup(&exe);
    assert!(!dir.join("Bleakhold Launcher.old.exe").exists());
    assert_eq!(read(&exe), new);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_bad_download_never_replaces_the_launcher() {
    let srv = TestServer::start();
    let dir = temp_dir("su-bad");
    let exe = dir.join("BleakholdLauncher.exe");
    fs::write(&exe, b"old").unwrap();
    let new = bytes(2, 10_000);
    let h = srv.put_object(&new);
    srv.corrupt_next(&format!("objects/{}/{h}", &h[..2]), 100);
    let info = LauncherInfo { version: "2.0.0".into(), size: new.len() as u64, sha256: h };
    let e = selfupdate::download(
        &http(&srv),
        "objects/",
        &info,
        &exe,
        &Control::new(),
        Duration::from_millis(10),
        &mut |_| {},
    )
    .unwrap_err();
    assert_eq!(e.code, Code::Hash);
    assert_eq!(read(&exe), b"old");
    assert!(!dir.join("BleakholdLauncher.new.exe").exists());

    // Wrong size in the manifest: also refused.
    let info = LauncherInfo { version: "2.0.0".into(), size: 5, sha256: sha256_hex(&new) };
    assert!(selfupdate::download(
        &http(&srv),
        "objects/",
        &info,
        &exe,
        &Control::new(),
        Duration::from_millis(10),
        &mut |_| {}
    )
    .is_err());
    assert_eq!(read(&exe), b"old");
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn swap_puts_the_old_launcher_back_when_it_fails() {
    let dir = temp_dir("su-rollback");
    let exe = dir.join("BleakholdLauncher.exe");
    fs::write(&exe, b"old").unwrap();
    fs::write(dir.join("BleakholdLauncher.old.exe"), b"older leftover").unwrap();
    let e = selfupdate::swap(&exe, &dir.join("missing.new.exe")).unwrap_err();
    assert_eq!(e.code, Code::Io);
    assert_eq!(read(&exe), b"old");
    fs::remove_dir_all(&dir).unwrap();
}

#[cfg(unix)]
#[test]
fn restart_passes_the_same_arguments() {
    use bleakhold_launcher_core::selfupdate::AFTER_UPDATE_ARG;
    use std::os::unix::fs::PermissionsExt;
    let dir = temp_dir("su-restart");
    let exe = dir.join("launcher.sh");
    let out = dir.join("args.txt");
    fs::write(&exe, format!("#!/bin/sh\necho \"$@\" > '{}'\n", out.display())).unwrap();
    fs::set_permissions(&exe, fs::Permissions::from_mode(0o755)).unwrap();
    selfupdate::restart(&exe, &["--minimized".into()]).unwrap();
    let mut text = String::new();
    for _ in 0..100 {
        text = fs::read_to_string(&out).unwrap_or_default();
        if !text.is_empty() {
            break;
        }
        std::thread::sleep(Duration::from_millis(20));
    }
    assert_eq!(text.trim(), format!("--minimized {AFTER_UPDATE_ARG} {}", std::process::id()));
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn install_folder_copy() {
    let dir = temp_dir("su-copy");
    let downloads = dir.join("Downloads");
    let install = dir.join("Games/Bleakhold");
    fs::create_dir_all(&downloads).unwrap();
    let exe = downloads.join("BleakholdLauncher.exe");
    fs::write(&exe, b"launcher v1").unwrap();

    let copy = selfupdate::ensure_install_copy(&exe, &install).unwrap();
    assert_eq!(copy, install.join("Bleakhold Launcher.exe"));
    assert_eq!(read(&copy), b"launcher v1");
    let mtime = fs::metadata(&copy).unwrap().modified().unwrap();

    // Identical: left alone.
    std::thread::sleep(Duration::from_millis(20));
    selfupdate::ensure_install_copy(&exe, &install).unwrap();
    assert_eq!(fs::metadata(&copy).unwrap().modified().unwrap(), mtime);

    // A newer running launcher replaces the copy.
    fs::write(&exe, b"launcher v2").unwrap();
    selfupdate::ensure_install_copy(&exe, &install).unwrap();
    assert_eq!(read(&copy), b"launcher v2");

    // Running the copy itself: nothing to do.
    selfupdate::ensure_install_copy(&copy, &install).unwrap();
    assert_eq!(read(&copy), b"launcher v2");
    assert_eq!(fs::read_dir(&install).unwrap().count(), 1, "no temp file left");
    fs::remove_dir_all(&dir).unwrap();
}
