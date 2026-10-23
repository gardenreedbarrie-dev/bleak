//! Downloader against a local HTTP server: parallel downloads, resume of an interrupted `.part` with
//! `Range`, a cut connection, hash mismatch → retry → error, stale `.part`, cancel, speed limit.

mod common;

use std::fs;
use std::path::Path;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use bleakhold_launcher_core::download::{self, sha256_hex, Control, Dest, Options, Progress, Task};
use bleakhold_launcher_core::http::{Http, Timeouts};
use bleakhold_launcher_core::Code;
use common::*;

fn http(srv: &TestServer) -> Http {
    Http::new(&srv.base, "test", Timeouts { connect: Duration::from_secs(5), read: Duration::from_secs(5) })
}

fn opts() -> Options {
    Options { backoff: Duration::from_millis(10), progress_interval: Duration::from_millis(20), ..Options::default() }
}

fn task(srv: &TestServer, root: &Path, rel: &str, content: &[u8]) -> Task {
    let h = srv.put_object(content);
    Task {
        url: format!("{}objects/{}/{h}", srv.base, &h[..2]),
        dest: Dest::Install { root: root.to_path_buf(), rel: rel.into() },
        size: content.len() as u64,
        sha256: h,
        label: rel.into(),
    }
}

fn object_path(content: &[u8]) -> String {
    let h = sha256_hex(content);
    format!("objects/{}/{h}", &h[..2])
}

fn run(
    srv: &TestServer,
    tasks: &[Task],
    o: &Options,
    ctl: &Control,
) -> (bleakhold_launcher_core::Result<()>, Vec<Progress>, Vec<usize>) {
    let mut progress = Vec::new();
    let mut done = Vec::new();
    let r = download::run(&http(srv), tasks, o, ctl, &mut |p| progress.push(p.clone()), &mut |i, _| {
        done.push(i);
        Ok(())
    });
    (r, progress, done)
}

#[test]
fn downloads_many_files_in_parallel() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-many");
    let contents: Vec<Vec<u8>> = (0..12).map(|i| bytes(i, 10_000 + i as usize * 3_000)).collect();
    let tasks: Vec<Task> =
        contents.iter().enumerate().map(|(i, c)| task(&srv, &dir, &format!("Data/sub{}/f{i}.bin", i % 3), c)).collect();
    let (r, progress, mut done) = run(&srv, &tasks, &Options { parallel: 4, ..opts() }, &Control::new());
    r.unwrap();
    done.sort();
    assert_eq!(done, (0..12).collect::<Vec<_>>());
    for (i, c) in contents.iter().enumerate() {
        assert_eq!(&read(&dir.join(format!("Data/sub{}/f{i}.bin", i % 3))), c);
        assert!(!dir.join(format!("Data/sub{}/f{i}.bin.part", i % 3)).exists());
    }
    let last = progress.last().unwrap();
    let total: u64 = contents.iter().map(|c| c.len() as u64).sum();
    assert_eq!((last.done_bytes, last.total_bytes, last.files_done, last.files_total), (total, total, 12, 12));
    assert!(progress.windows(2).all(|w| w[0].done_bytes <= w[1].done_bytes), "progress only grows");
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn resumes_an_interrupted_part_with_range() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-resume");
    let content = bytes(1, 300_000);
    let t = task(&srv, &dir, "Data/common.MPQ", &content);
    fs::create_dir_all(dir.join("Data")).unwrap();
    fs::write(dir.join("Data/common.MPQ.part"), &content[..120_000]).unwrap();
    let (r, progress, _) = run(&srv, &[t], &opts(), &Control::new());
    r.unwrap();
    assert_eq!(read(&dir.join("Data/common.MPQ")), content);
    let hits = srv.hits_for(&object_path(&content));
    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].range, Some(120_000));
    // Resumed bytes count as done.
    assert_eq!(progress.last().unwrap().done_bytes, 300_000);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_cut_connection_is_resumed_on_the_next_try() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-cut");
    let content = bytes(2, 200_000);
    let t = task(&srv, &dir, "Data/patch.MPQ", &content);
    srv.cut_next(&object_path(&content), 1, 50_000);
    let (r, _, _) = run(&srv, &[t], &opts(), &Control::new());
    r.unwrap();
    assert_eq!(read(&dir.join("Data/patch.MPQ")), content);
    let hits = srv.hits_for(&object_path(&content));
    assert_eq!(hits.len(), 2);
    assert_eq!(hits[0].range, None);
    assert!(hits[1].range.unwrap() > 0, "second try resumes: {hits:?}");
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn hash_mismatch_retries_then_fails() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-hash");
    let content = bytes(3, 50_000);
    let path = object_path(&content);

    // Two bad answers, then a good one: succeeds on the third try.
    let t = task(&srv, &dir, "a.bin", &content);
    srv.corrupt_next(&path, 2);
    let (r, _, _) = run(&srv, std::slice::from_ref(&t), &opts(), &Control::new());
    r.unwrap();
    assert_eq!(read(&dir.join("a.bin")), content);
    assert_eq!(srv.hits_for(&path).len(), 3);

    // Always bad: three tries, then a hash error, no .part and no file left.
    srv.clear_hits();
    let t2 = Task { dest: Dest::Install { root: dir.clone(), rel: "b.bin".into() }, ..t };
    srv.corrupt_next(&path, 100);
    let (r, _, done) = run(&srv, &[t2], &opts(), &Control::new());
    let e = r.unwrap_err();
    assert_eq!(e.code, Code::Hash, "{e}");
    assert!(done.is_empty());
    assert_eq!(srv.hits_for(&path).len(), 3);
    assert!(!dir.join("b.bin").exists() && !dir.join("b.bin.part").exists());
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn missing_object_is_a_network_error_after_three_tries() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-404");
    let content = bytes(4, 1000);
    let t = task(&srv, &dir, "x.bin", &content);
    srv.remove(&object_path(&content));
    let (r, _, _) = run(&srv, &[t], &opts(), &Control::new());
    assert_eq!(r.unwrap_err().code, Code::Network);
    assert_eq!(srv.hits_for(&object_path(&content)).len(), 3);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn stale_part_from_an_older_file_starts_over_for_free() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-stale");
    let content = bytes(5, 80_000);
    let t = task(&srv, &dir, "Data/x.MPQ", &content);
    fs::create_dir_all(dir.join("Data")).unwrap();
    fs::write(dir.join("Data/x.MPQ.part"), bytes(99, 30_000)).unwrap();
    let (r, _, _) = run(&srv, &[t], &Options { tries: 1, ..opts() }, &Control::new());
    r.unwrap();
    assert_eq!(read(&dir.join("Data/x.MPQ")), content);
    let hits = srv.hits_for(&object_path(&content));
    assert_eq!(hits.iter().map(|h| h.range).collect::<Vec<_>>(), vec![Some(30_000), None]);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn server_without_range_support_restarts_cleanly() {
    let srv = TestServer::start();
    srv.state.ignore_range.store(true, Ordering::SeqCst);
    let dir = temp_dir("dl-norange");
    let content = bytes(6, 60_000);
    let t = task(&srv, &dir, "f.bin", &content);
    fs::write(dir.join("f.bin.part"), &content[..20_000]).unwrap();
    let (r, progress, _) = run(&srv, &[t], &opts(), &Control::new());
    r.unwrap();
    assert_eq!(read(&dir.join("f.bin")), content);
    assert_eq!(progress.last().unwrap().done_bytes, 60_000);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn complete_part_needs_no_request_and_replaces_the_target() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-complete");
    let content = bytes(7, 5_000);
    let t = task(&srv, &dir, "f.bin", &content);
    fs::write(dir.join("f.bin"), b"old version").unwrap();
    fs::write(dir.join("f.bin.part"), &content).unwrap();
    let (r, _, _) = run(&srv, &[t], &opts(), &Control::new());
    r.unwrap();
    assert_eq!(read(&dir.join("f.bin")), content);
    assert!(srv.hits().is_empty());
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn empty_files_and_bad_paths() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-empty");
    let t = task(&srv, &dir, "Logs/empty.txt", b"");
    let (r, _, _) = run(&srv, &[t], &opts(), &Control::new());
    r.unwrap();
    assert_eq!(fs::metadata(dir.join("Logs/empty.txt")).unwrap().len(), 0);

    let mut bad = task(&srv, &dir, "x", b"abc");
    bad.dest = Dest::Install { root: dir.clone(), rel: "../escape.txt".into() };
    let (r, _, _) = run(&srv, &[bad], &opts(), &Control::new());
    assert_eq!(r.unwrap_err().code, Code::Io);
    assert!(!dir.parent().unwrap().join("escape.txt").exists());
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn cancel_keeps_the_part_for_later() {
    let srv = TestServer::start();
    srv.state.slow_ms.store(20, Ordering::SeqCst);
    let dir = temp_dir("dl-cancel");
    let content = bytes(8, 2_000_000);
    let t = task(&srv, &dir, "big.bin", &content);
    let ctl = Arc::new(Control::new());
    let c2 = ctl.clone();
    let stopper = thread::spawn(move || {
        thread::sleep(Duration::from_millis(300));
        c2.request_stop();
    });
    let started = Instant::now();
    let (r, _, done) = run(&srv, std::slice::from_ref(&t), &opts(), &ctl);
    stopper.join().unwrap();
    assert!(r.unwrap_err().is_cancelled());
    assert!(done.is_empty());
    assert!(started.elapsed() < Duration::from_secs(2));
    let part = fs::metadata(dir.join("big.bin.part")).unwrap().len();
    assert!(part > 0 && part < 2_000_000, "{part}");
    assert!(!dir.join("big.bin").exists());

    // Resume from where it stopped.
    srv.state.slow_ms.store(0, Ordering::SeqCst);
    ctl.clear();
    srv.clear_hits();
    let (r, _, _) = run(&srv, &[t], &opts(), &ctl);
    r.unwrap();
    assert_eq!(read(&dir.join("big.bin")), content);
    assert_eq!(srv.hits()[0].range, Some(part));
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn speed_limit_slows_the_download() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-limit");
    let content = bytes(9, 600_000);
    let t = task(&srv, &dir, "f.bin", &content);
    let ctl = Control::new();
    ctl.set_limit_bps(1_000_000);
    let started = Instant::now();
    let (r, _, _) = run(&srv, &[t], &opts(), &ctl);
    r.unwrap();
    // 0.6 MB at 1 MB/s, less a quarter second of credit.
    let el = started.elapsed();
    assert!(el >= Duration::from_millis(300), "{el:?}");
    assert_eq!(read(&dir.join("f.bin")), content);
    fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn on_done_error_stops_the_run() {
    let srv = TestServer::start();
    let dir = temp_dir("dl-ondone");
    let tasks: Vec<Task> = (0..5).map(|i| task(&srv, &dir, &format!("f{i}"), &bytes(i, 1000))).collect();
    let r = download::run(
        &http(&srv),
        &tasks,
        &Options { parallel: 1, ..opts() },
        &Control::new(),
        &mut |_| {},
        &mut |_, _| Err(bleakhold_launcher_core::Error::io_msg("disk said no")),
    );
    assert_eq!(r.unwrap_err().message, "disk said no");
    fs::remove_dir_all(&dir).unwrap();
}
