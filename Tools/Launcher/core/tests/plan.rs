//! Planner: fast check by size and modification time, full hash for repair, `once` files, adoption of
//! an existing install, and deletion of tracked files only.

mod common;

use std::fs;
use std::path::Path;
use std::time::{Duration, UNIX_EPOCH};

use bleakhold_launcher_core::download::sha256_hex;
use bleakhold_launcher_core::manifest::Manifest;
use bleakhold_launcher_core::planner::{self, Mode, Plan, VerifyProgress};
use bleakhold_launcher_core::state::{FileState, InstallState};
use bleakhold_launcher_core::util::mtime_ns;
use common::*;
use serde_json::json;

fn manifest(files: &[(&str, &[u8], bool)]) -> Manifest {
    let files: Vec<_> =
        files.iter().map(|(p, c, once)| json!({ "p": p, "s": c.len(), "h": sha256_hex(c), "once": once })).collect();
    let m = json!({ "format": 1, "realmlist": "127.0.0.1", "exe": "Bleakhold.exe", "files": files });
    Manifest::parse(&serde_json::to_vec(&m).unwrap()).unwrap()
}

fn write(dir: &Path, rel: &str, content: &[u8]) {
    let p = dir.join(rel);
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(p, content).unwrap();
}

fn tracked(dir: &Path, rel: &str, content: &[u8]) -> FileState {
    let meta = fs::metadata(dir.join(rel)).unwrap();
    FileState {
        p: rel.into(),
        s: content.len() as u64,
        h: sha256_hex(content),
        size: meta.len(),
        mtime: mtime_ns(&meta),
        once: false,
    }
}

struct Run {
    plan: Plan,
    hashed: Vec<String>,
    verified: Vec<(String, bool)>,
    last: VerifyProgress,
}

fn plan(m: &Manifest, dir: &Path, state: &InstallState, mode: Mode) -> Run {
    let mut hashed = Vec::new();
    let mut verified = Vec::new();
    let mut last = VerifyProgress::default();
    let plan = planner::plan(
        m,
        dir,
        state,
        mode,
        &|| false,
        &mut |vp| {
            if hashed.last() != Some(&vp.file) && !vp.file.is_empty() {
                hashed.push(vp.file.clone());
            }
            last = vp.clone();
        },
        &mut |p, e| verified.push((p.to_string(), e.is_some())),
    )
    .unwrap();
    hashed.dedup();
    Run { plan, hashed, verified, last }
}

fn names(plan: &Plan) -> Vec<&str> {
    let mut v: Vec<&str> = plan.downloads.iter().map(|j| j.p.as_str()).collect();
    v.sort();
    v
}

#[test]
fn fresh_folder_downloads_everything() {
    let dir = temp_dir("plan-fresh");
    let m =
        manifest(&[("Bleakhold.exe", b"exe", false), ("Data/a.MPQ", b"aaaa", false), ("WTF/Config.wtf", b"cfg", true)]);
    let r = plan(&m, &dir, &InstallState::default(), Mode::Fast);
    assert_eq!(names(&r.plan), ["Bleakhold.exe", "Data/a.MPQ", "WTF/Config.wtf"]);
    assert!(r.plan.downloads.iter().find(|j| j.p == "WTF/Config.wtf").unwrap().once);
    assert_eq!((r.plan.download_bytes, r.plan.total_bytes), (10, 10));
    assert!(r.hashed.is_empty());
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn fast_check_trusts_the_state_and_hashes_only_changes() {
    let dir = temp_dir("plan-fast");
    let files: [(&str, &[u8], bool); 3] =
        [("Bleakhold.exe", b"exe", false), ("Data/a.MPQ", b"aaaa", false), ("Data/b.MPQ", b"bbbb", false)];
    let m = manifest(&files);
    let mut st = InstallState::default();
    for (p, c, _) in files {
        write(&dir, p, c);
        st.record(tracked(&dir, p, c));
    }
    let r = plan(&m, &dir, &st, Mode::Fast);
    assert!(r.plan.is_empty() && r.hashed.is_empty(), "{:?}", r.plan);

    // Size changed: download without hashing.
    write(&dir, "Data/a.MPQ", b"aaaaaa");
    // Same size, other content, new mtime: hashed and found wrong.
    write(&dir, "Data/b.MPQ", b"BBBB");
    fs::File::options()
        .write(true)
        .open(dir.join("Data/b.MPQ"))
        .unwrap()
        .set_modified(UNIX_EPOCH + Duration::from_secs(1_000_000))
        .unwrap();
    let r = plan(&m, &dir, &st, Mode::Fast);
    assert_eq!(names(&r.plan), ["Data/a.MPQ", "Data/b.MPQ"]);
    assert_eq!(r.hashed, ["Data/b.MPQ"]);
    assert_eq!(r.verified, [("Data/b.MPQ".to_string(), false)]);
    assert_eq!((r.last.files_done, r.last.files_total, r.last.done_bytes, r.last.total_bytes), (1, 1, 4, 4));

    // Same content, only the mtime moved (e.g. copied): hashed and adopted.
    write(&dir, "Data/b.MPQ", b"bbbb");
    fs::File::options()
        .write(true)
        .open(dir.join("Data/b.MPQ"))
        .unwrap()
        .set_modified(UNIX_EPOCH + Duration::from_secs(2_000_000))
        .unwrap();
    let r = plan(&m, &dir, &st, Mode::Fast);
    assert_eq!(names(&r.plan), ["Data/a.MPQ"]);
    assert_eq!(r.verified, [("Data/b.MPQ".to_string(), true)]);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn repair_hashes_everything() {
    let dir = temp_dir("plan-repair");
    let files: [(&str, &[u8], bool); 2] = [("Bleakhold.exe", b"exe", false), ("Data/a.MPQ", b"aaaa", false)];
    let m = manifest(&files);
    let mut st = InstallState::default();
    for (p, c, _) in files {
        write(&dir, p, c);
        st.record(tracked(&dir, p, c));
    }
    // Damage a.MPQ without changing size or mtime (bit rot): fast trusts it, repair finds it.
    let meta = fs::metadata(dir.join("Data/a.MPQ")).unwrap();
    write(&dir, "Data/a.MPQ", b"aXaa");
    fs::File::options()
        .write(true)
        .open(dir.join("Data/a.MPQ"))
        .unwrap()
        .set_modified(meta.modified().unwrap())
        .unwrap();
    assert!(plan(&m, &dir, &st, Mode::Fast).plan.is_empty());
    let r = plan(&m, &dir, &st, Mode::Repair);
    assert_eq!(names(&r.plan), ["Data/a.MPQ"]);
    let mut h = r.hashed.clone();
    h.sort();
    assert_eq!(h, ["Bleakhold.exe", "Data/a.MPQ"]);
    assert!(r.verified.contains(&("Data/a.MPQ".to_string(), false)));
    assert!(r.verified.contains(&("Bleakhold.exe".to_string(), true)));
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn once_files_are_only_checked_for_presence() {
    let dir = temp_dir("plan-once");
    let m = manifest(&[("Bleakhold.exe", b"exe", false), ("WTF/Config.wtf", b"default", true)]);
    write(&dir, "Bleakhold.exe", b"exe");
    write(&dir, "WTF/Config.wtf", b"the player's own settings, longer");
    for mode in [Mode::Fast, Mode::Repair] {
        let r = plan(&m, &dir, &InstallState::default(), mode);
        assert!(!names(&r.plan).contains(&"WTF/Config.wtf"), "{mode:?}");
        assert!(!r.hashed.contains(&"WTF/Config.wtf".to_string()));
    }
    fs::remove_file(dir.join("WTF/Config.wtf")).unwrap();
    let r = plan(&m, &dir, &InstallState::default(), Mode::Fast);
    assert_eq!(names(&r.plan), ["WTF/Config.wtf"]);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn existing_install_is_adopted() {
    let dir = temp_dir("plan-adopt");
    let m = manifest(&[
        ("Bleakhold.exe", b"bleak", false),
        ("Wow.exe", b"wow", false),
        ("Data/common.MPQ", b"common", false),
        ("Data/patch.MPQ", b"patch", false),
    ]);
    write(&dir, "Wow.exe", b"wow");
    write(&dir, "Data/common.MPQ", b"common");
    write(&dir, "Data/patch.MPQ", b"PATCH");
    write(&dir, "Interface/AddOns/Mine/Mine.toc", b"player's addon");
    let r = plan(&m, &dir, &InstallState::default(), Mode::Fast);
    assert_eq!(names(&r.plan), ["Bleakhold.exe", "Data/patch.MPQ"]);
    let mut adopted: Vec<_> = r.verified.iter().filter(|v| v.1).map(|v| v.0.as_str()).collect();
    adopted.sort();
    assert_eq!(adopted, ["Data/common.MPQ", "Wow.exe"]);
    assert!(r.plan.deletes.is_empty());
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn deletes_only_tracked_files() {
    let dir = temp_dir("plan-delete");
    let m = manifest(&[("Bleakhold.exe", b"exe", false), ("Data/new.MPQ", b"new", false)]);
    write(&dir, "Bleakhold.exe", b"exe");
    write(&dir, "Data/old.MPQ", b"old");
    write(&dir, "Data/Sub/gone.txt", b"gone");
    write(&dir, "Data/Keep/gone2.txt", b"gone2");
    write(&dir, "Data/Keep/mine.txt", b"player's");
    write(&dir, "WTF/Config.wtf", b"settings");
    write(&dir, "Screenshots/shot.jpg", b"jpg");
    let mut st = InstallState::default();
    for (p, c) in [
        ("Bleakhold.exe", &b"exe"[..]),
        ("Data/old.MPQ", b"old"),
        ("Data/Sub/gone.txt", b"gone"),
        ("Data/Keep/gone2.txt", b"gone2"),
    ] {
        st.record(tracked(&dir, p, c));
    }
    st.record(FileState { once: true, ..tracked(&dir, "WTF/Config.wtf", b"settings") });
    // Tracked under another case than the manifest now uses: the same file on Windows, kept.
    write(&dir, "Data/NEW.mpq", b"new");
    st.record(tracked(&dir, "Data/NEW.mpq", b"new"));

    let r = plan(&m, &dir, &st, Mode::Fast);
    let mut del = r.plan.deletes.clone();
    del.sort();
    assert_eq!(del, ["Data/Keep/gone2.txt", "Data/Sub/gone.txt", "Data/old.MPQ"]);

    write(&dir, "Data/old.MPQ.part", b"ol");
    planner::delete_stale(&dir, &del, &mut st);
    assert!(!dir.join("Data/old.MPQ").exists() && !dir.join("Data/old.MPQ.part").exists());
    assert!(!dir.join("Data/Sub").exists(), "emptied folder removed");
    assert!(dir.join("Data/Keep/mine.txt").exists(), "player's file kept");
    assert!(dir.join("WTF/Config.wtf").exists() && dir.join("Screenshots/shot.jpg").exists());
    assert!(dir.join("Bleakhold.exe").exists());
    assert!(!st.files.contains_key("Data/old.MPQ") && st.files.contains_key("WTF/Config.wtf"));

    // A tampered list never reaches outside the folder.
    let outside = dir.parent().unwrap().join(format!("bh-outside-{}", std::process::id()));
    fs::write(&outside, b"x").unwrap();
    let rel = format!("../{}", outside.file_name().unwrap().to_string_lossy());
    planner::delete_stale(&dir, &[rel], &mut st);
    assert!(outside.exists());
    fs::remove_file(&outside).unwrap();
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn stop_cancels_hashing() {
    let dir = temp_dir("plan-stop");
    let m = manifest(&[("Bleakhold.exe", b"exe", false)]);
    write(&dir, "Bleakhold.exe", b"exe");
    let e = planner::plan(&m, &dir, &InstallState::default(), Mode::Repair, &|| true, &mut |_| {}, &mut |_, _| {})
        .unwrap_err();
    assert!(e.is_cancelled());
    fs::remove_dir_all(&dir).unwrap();
}
