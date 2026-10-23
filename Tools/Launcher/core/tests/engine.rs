//! The engine end to end against a local update server: placeholder key, offline, install, update with
//! deletions and `once` files, restart without re-hashing, bad signature, invalid manifest, pause and
//! resume, a launcher closed mid-download, cancel, game running, repair, adoption of an existing client,
//! Play (realmlist, cache epoch, working folder), the cached manifest while offline, and self-update.

mod common;

use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use bleakhold_launcher_core::config::LauncherConfig;
use bleakhold_launcher_core::engine::{Engine, EngineConfig, Phase, ServerView, Sink};
use bleakhold_launcher_core::http::Timeouts;
use bleakhold_launcher_core::state::InstallState;
use bleakhold_launcher_core::{Code, Progress};
use common::*;
use serde_json::json;

#[derive(Clone, Debug)]
enum Ev {
    Phase(Phase, String),
    Progress(Progress),
    Error(Code, String),
    Server(ServerView),
}

#[derive(Default)]
struct Rec {
    events: Mutex<Vec<Ev>>,
    cv: Condvar,
    quit: AtomicBool,
}

impl Sink for Rec {
    fn phase(&self, phase: Phase, message: &str) {
        self.push(Ev::Phase(phase, message.to_string()));
    }
    fn progress(&self, p: &Progress) {
        self.push(Ev::Progress(p.clone()));
    }
    fn error(&self, code: Code, message: &str) {
        self.push(Ev::Error(code, message.to_string()));
    }
    fn server(&self, s: &ServerView) {
        self.push(Ev::Server(s.clone()));
    }
    fn quit(&self) {
        self.quit.store(true, Ordering::SeqCst);
        self.cv.notify_all();
    }
}

impl Rec {
    fn push(&self, e: Ev) {
        self.events.lock().unwrap().push(e);
        self.cv.notify_all();
    }

    fn len(&self) -> usize {
        self.events.lock().unwrap().len()
    }

    fn events(&self) -> Vec<Ev> {
        self.events.lock().unwrap().clone()
    }

    /// Waits for `phase` among the events from index `from` on; returns the index after it.
    fn wait_phase(&self, phase: Phase, from: usize) -> usize {
        let end = Instant::now() + Duration::from_secs(20);
        let mut ev = self.events.lock().unwrap();
        loop {
            if let Some(i) = ev[from..].iter().position(|e| matches!(e, Ev::Phase(p, _) if *p == phase)) {
                return from + i + 1;
            }
            let now = Instant::now();
            if now >= end {
                panic!("phase {phase:?} not reached; events: {:#?}", &ev[from..]);
            }
            ev = self.cv.wait_timeout(ev, end - now).unwrap().0;
        }
    }

    fn phases(&self, from: usize) -> Vec<Phase> {
        self.events()[from..]
            .iter()
            .filter_map(|e| match e {
                Ev::Phase(p, _) => Some(*p),
                _ => None,
            })
            .collect()
    }

    fn errors(&self, from: usize) -> Vec<(Code, String)> {
        self.events()[from..]
            .iter()
            .filter_map(|e| match e {
                Ev::Error(c, m) => Some((*c, m.clone())),
                _ => None,
            })
            .collect()
    }

    /// Waits for a progress event among the events from index `from` on (a phase's first progress event comes
    /// right after the phase event, from the engine's thread); returns it.
    fn wait_progress(&self, from: usize) -> Progress {
        let end = Instant::now() + Duration::from_secs(20);
        let mut ev = self.events.lock().unwrap();
        loop {
            if let Some(Ev::Progress(p)) = ev[from..].iter().find(|e| matches!(e, Ev::Progress(_))) {
                return p.clone();
            }
            let now = Instant::now();
            if now >= end {
                panic!("no progress event; events: {:#?}", &ev[from..]);
            }
            ev = self.cv.wait_timeout(ev, end - now).unwrap().0;
        }
    }

    fn progress_after(&self, from: usize) -> Vec<Progress> {
        self.events()[from..]
            .iter()
            .filter_map(|e| match e {
                Ev::Progress(p) => Some(p.clone()),
                _ => None,
            })
            .collect()
    }

    #[cfg_attr(not(unix), allow(dead_code))]
    fn wait_quit(&self) {
        let end = Instant::now() + Duration::from_secs(20);
        let mut ev = self.events.lock().unwrap();
        while !self.quit.load(Ordering::SeqCst) {
            assert!(Instant::now() < end, "no quit");
            ev = self.cv.wait_timeout(ev, Duration::from_millis(100)).unwrap().0;
        }
    }
}

struct Setup {
    root: PathBuf,
    config: PathBuf,
    install: PathBuf,
}

fn setup(name: &str) -> Setup {
    let root = temp_dir(name);
    Setup { config: root.join("config"), install: root.join("Games/Bleakhold"), root }
}

fn config(base: &str, key: &str, cfg_dir: &Path) -> EngineConfig {
    let lc =
        LauncherConfig::parse(&json!({ "base_url": base, "public_key": key, "realmlist": "127.0.0.1" }).to_string())
            .unwrap();
    let mut c = EngineConfig::new("1.0.0", lc, cfg_dir.to_path_buf());
    c.server_interval = Duration::from_secs(600);
    c.probe_timeout = Duration::from_millis(300);
    c.http_timeouts = Timeouts { connect: Duration::from_secs(5), read: Duration::from_secs(5) };
    c.retry_backoff = Duration::from_millis(10);
    c.signature_retry_delay = Duration::from_millis(10);
    c
}

fn start(c: EngineConfig) -> (Engine, Arc<Rec>) {
    let rec = Arc::new(Rec::default());
    let e = Engine::new(c, rec.clone());
    (e, rec)
}

fn v1() -> Spec {
    Spec::new("v1")
        .file("Bleakhold.exe", b"#!/bin/sh\npwd > started.txt\n")
        .file("Data/common.MPQ", &bytes(1, 300_000))
        .file("Data/enUS/patch-enUS.MPQ", &bytes(2, 120_000))
        .file("Interface/AddOns/Bleakhold/Bleakhold.lua", b"print('hi')")
        .file("Data/old.txt", b"old")
        .once("WTF/Config.wtf", b"SET gxWindow \"1\"\n")
}

fn install_v1(srv: &TestServer, s: &Setup) -> (Engine, Arc<Rec>) {
    srv.publish(&v1());
    let (e, rec) = start(config(&srv.base, &public_key_b64(), &s.config));
    let i = rec.wait_phase(Phase::NeedsInstall, 0);
    e.install(s.install.to_str().unwrap(), false, false).unwrap();
    rec.wait_phase(Phase::Ready, i);
    (e, rec)
}

#[test]
fn placeholder_key_refuses_to_trust_anything() {
    let srv = TestServer::start();
    srv.publish(&v1());
    let s = setup("en-placeholder");
    let (e, rec) = start(config(&srv.base, "REPLACE_WITH_VPS_PUBLIC_KEY", &s.config));
    let i = rec.wait_phase(Phase::Error, 0);
    let errs = rec.errors(0);
    assert_eq!(errs[0].0, Code::Signature);
    assert!(errs[0].1.contains("signing key"), "{errs:?}");
    // The error event comes right before the error phase.
    let ev = rec.events();
    let err_at = ev.iter().position(|e| matches!(e, Ev::Error(..))).unwrap();
    assert!(err_at < i - 1, "error event before the phase");
    assert!(srv.hits_for("manifest.json").is_empty());
    assert_eq!(e.state().phase, Phase::Error);
    // Retry gives the same answer.
    let n = rec.len();
    e.check();
    rec.wait_phase(Phase::Error, n);
    assert_eq!(e.install(s.install.to_str().unwrap(), false, false).unwrap_err().code, Code::Signature);
    assert!(!s.install.exists());
    drop(e);
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn offline_without_an_install() {
    let dead = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}/", dead.local_addr().unwrap());
    drop(dead);
    let s = setup("en-offline");
    let (e, rec) = start(config(&base, &public_key_b64(), &s.config));
    rec.wait_phase(Phase::Offline, 0);
    let st = e.state();
    assert!(!st.installed);
    assert!(st.install_dir.ends_with("Bleakhold"), "suggested folder: {}", st.install_dir);
    assert!(e.play().is_err());
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn install_update_and_restart() {
    let srv = TestServer::start();
    let s = setup("en-flow");
    srv.publish(&v1());
    let (e, rec) = start(config(&srv.base, &public_key_b64(), &s.config));
    let i = rec.wait_phase(Phase::NeedsInstall, 0);
    let st = e.state();
    assert!(!st.installed && st.build == "v1" && st.news.len() == 1 && st.links.contains_key("website"));
    let total = st.total_bytes;
    assert_eq!(st.pending_bytes, total);

    let info = e.folder_info(s.install.to_str().unwrap()).unwrap();
    assert_eq!(info.path, s.install.display().to_string());
    assert!(info.writable && !info.has_game && info.free_bytes > 0);
    assert_eq!(info.needed_bytes, total);
    assert!(e.folder_info("relative").is_err());

    e.install(s.install.to_str().unwrap(), true, true).unwrap();
    let j = rec.wait_phase(Phase::Ready, i);
    assert_eq!(rec.phases(i), [Phase::Downloading, Phase::Ready]);
    let progress = rec.progress_after(i);
    assert_eq!(progress.first().unwrap().done_bytes, 0, "a progress event as soon as downloading starts");
    let last = progress.last().unwrap();
    assert_eq!((last.done_bytes, last.total_bytes, last.files_done, last.files_total), (total, total, 6, 6));
    for f in &v1().files {
        assert_eq!(read(&s.install.join(&f.p)), f.content, "{}", f.p);
    }
    let st = e.state();
    assert!(st.installed && st.pending_bytes == 0);
    assert_eq!(st.install_dir, s.install.display().to_string());
    let settings: serde_json::Value = serde_json::from_slice(&read(&s.config.join("settings.json"))).unwrap();
    assert_eq!(settings["install_dir"], json!(s.install.display().to_string()));
    assert_eq!(settings["shortcuts"], json!(true));
    let state = InstallState::load(&s.install);
    assert_eq!(state.files.len(), 6);
    assert!(state.files["WTF/Config.wtf"].once && state.job.is_none());
    assert_eq!(state.build, "v1");

    // The player adds an addon and changes their settings.
    fs::create_dir_all(s.install.join("Interface/AddOns/Mine")).unwrap();
    fs::write(s.install.join("Interface/AddOns/Mine/Mine.toc"), b"## Title: Mine").unwrap();
    fs::write(s.install.join("WTF/Config.wtf"), b"SET gxWindow \"0\"\nSET realmList \"x\"\n").unwrap();

    // v2: one file changed, one removed, one added, the once default changed.
    let v2 = Spec::new("v2")
        .file("Bleakhold.exe", b"#!/bin/sh\npwd > started.txt\n")
        .file("Data/common.MPQ", &bytes(1, 300_000))
        .file("Data/enUS/patch-enUS.MPQ", &bytes(3, 130_000))
        .file("Interface/AddOns/Bleakhold/Bleakhold.lua", b"print('hi')")
        .file("Data/new.txt", b"new file")
        .once("WTF/Config.wtf", b"SET gxWindow \"1\"\nSET new \"1\"\n");
    srv.publish(&v2);
    srv.clear_hits();
    e.check();
    let k = rec.wait_phase(Phase::NeedsUpdate, j);
    assert_eq!(e.state().pending_bytes, 130_000 + 8);
    assert_eq!(e.state().build, "v2");
    e.update();
    rec.wait_phase(Phase::Ready, k);
    assert_eq!(read(&s.install.join("Data/enUS/patch-enUS.MPQ")), bytes(3, 130_000));
    assert_eq!(read(&s.install.join("Data/new.txt")), b"new file");
    assert!(!s.install.join("Data/old.txt").exists(), "dropped file deleted");
    assert!(s.install.join("Interface/AddOns/Mine/Mine.toc").exists(), "player's addon kept");
    assert_eq!(read(&s.install.join("WTF/Config.wtf")), b"SET gxWindow \"0\"\nSET realmList \"x\"\n");
    let objects: Vec<_> = srv.hits().into_iter().filter(|h| h.path.starts_with("objects/")).collect();
    assert_eq!(objects.len(), 2, "only what changed: {objects:?}");
    drop(e);

    // A new start: ready straight away, nothing hashed or downloaded.
    srv.clear_hits();
    let (e2, rec2) = start(config(&srv.base, &public_key_b64(), &s.config));
    rec2.wait_phase(Phase::Ready, 0);
    assert_eq!(rec2.phases(0), [Phase::Loading, Phase::Ready]);
    assert!(srv.hits().iter().all(|h| !h.path.starts_with("objects/")));
    assert!(e2.state().installed);
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn bad_signature_and_invalid_manifest_change_nothing() {
    let srv = TestServer::start();
    let s = setup("en-badsig");
    let (e, rec) = install_v1(&srv, &s);
    let before = InstallState::load(&s.install);

    // Signature of other bytes: retried once, then the error phase.
    let mut spec = v1();
    spec.build = "evil".into();
    spec.files[1].content = b"evil".to_vec();
    srv.publish(&spec);
    srv.put("manifest.json.sig", sign(b"something else").as_bytes());
    srv.clear_hits();
    let n = rec.len();
    e.check();
    rec.wait_phase(Phase::Error, n);
    assert_eq!(rec.errors(n)[0].0, Code::Signature);
    assert_eq!(srv.hits_for("manifest.json").len(), 2);
    assert_eq!(InstallState::load(&s.install), before);
    assert_eq!(read(&s.install.join("Data/common.MPQ")), bytes(1, 300_000));

    // Properly signed but breaking a path rule.
    let m = json!({ "format": 1, "realmlist": "127.0.0.1", "exe": "Bleakhold.exe",
                    "files": [ { "p": "../escape.txt", "s": 1, "h": "a".repeat(64) } ] });
    let bytes = serde_json::to_vec(&m).unwrap();
    srv.put("manifest.json", &bytes);
    srv.put("manifest.json.sig", sign(&bytes).as_bytes());
    let n = rec.len();
    e.check();
    rec.wait_phase(Phase::Error, n);
    assert_eq!(rec.errors(n)[0].0, Code::Manifest);
    assert_eq!(InstallState::load(&s.install), before);
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn pause_resume_and_cancel() {
    let srv = TestServer::start();
    let s = setup("en-pause");
    let spec = Spec::new("v1").file("Bleakhold.exe", b"exe").file("Data/big.MPQ", &bytes(5, 3_000_000));
    srv.publish(&spec);
    srv.state.slow_ms.store(15, Ordering::SeqCst);
    let (e, rec) = start(config(&srv.base, &public_key_b64(), &s.config));
    let i = rec.wait_phase(Phase::NeedsInstall, 0);
    e.install(s.install.to_str().unwrap(), false, false).unwrap();
    let i = rec.wait_phase(Phase::Downloading, i);
    std::thread::sleep(Duration::from_millis(400));
    e.pause();
    let p = rec.wait_phase(Phase::Paused, i);
    rec.wait_progress(p);
    std::thread::sleep(Duration::from_millis(50));
    let after = rec.progress_after(p);
    assert_eq!(after.len(), 1, "one progress event right after paused");
    assert!(after[0].done_bytes > 0 && after[0].done_bytes < after[0].total_bytes);
    assert_eq!(after[0].speed_bps, 0);
    assert!(fs::metadata(s.install.join("Data/big.MPQ.part")).unwrap().len() > 0);

    srv.state.slow_ms.store(0, Ordering::SeqCst);
    srv.clear_hits();
    e.resume();
    rec.wait_phase(Phase::Ready, p);
    assert_eq!(read(&s.install.join("Data/big.MPQ")), bytes(5, 3_000_000));
    let resumed: Vec<_> = srv.hits().into_iter().filter(|h| h.path.starts_with("objects/")).collect();
    assert!(resumed.iter().any(|h| h.range.unwrap_or(0) > 0), "resumed with Range: {resumed:?}");

    // Cancel during an update: back to needs_update, the job dropped.
    let spec2 = Spec::new("v2").file("Bleakhold.exe", b"exe").file("Data/big.MPQ", &bytes(6, 3_000_000));
    srv.publish(&spec2);
    srv.state.slow_ms.store(15, Ordering::SeqCst);
    let n = rec.len();
    e.check();
    let n = rec.wait_phase(Phase::NeedsUpdate, n);
    e.update();
    let n = rec.wait_phase(Phase::Downloading, n);
    std::thread::sleep(Duration::from_millis(300));
    e.cancel();
    rec.wait_phase(Phase::NeedsUpdate, n);
    assert!(InstallState::load(&s.install).job.is_none());
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn closed_mid_download_starts_paused_and_resumes() {
    let srv = TestServer::start();
    let s = setup("en-closed");
    let spec = Spec::new("v1")
        .file("Bleakhold.exe", b"exe")
        .file("Data/a.MPQ", &bytes(7, 200_000))
        .file("Data/big.MPQ", &bytes(8, 3_000_000));
    srv.publish(&spec);
    srv.state.slow_ms.store(15, Ordering::SeqCst);
    let (e, rec) = start(config(&srv.base, &public_key_b64(), &s.config));
    let i = rec.wait_phase(Phase::NeedsInstall, 0);
    e.install(s.install.to_str().unwrap(), false, false).unwrap();
    rec.wait_phase(Phase::Downloading, i);
    std::thread::sleep(Duration::from_millis(600));
    e.shutdown(Duration::from_secs(5));
    drop(e);
    let job = InstallState::load(&s.install).job.expect("job mark kept");
    assert_eq!(job.files_total, 3);

    srv.state.slow_ms.store(0, Ordering::SeqCst);
    let (e2, rec2) = start(config(&srv.base, &public_key_b64(), &s.config));
    let p = rec2.wait_phase(Phase::Paused, 0);
    rec2.wait_progress(p);
    std::thread::sleep(Duration::from_millis(50));
    let shown = rec2.progress_after(p);
    assert_eq!(shown.len(), 1);
    assert_eq!((shown[0].total_bytes, shown[0].files_total), (job.total_bytes, 3));
    e2.resume();
    let r = rec2.wait_phase(Phase::Ready, p);
    let last = rec2.progress_after(p).into_iter().last().unwrap();
    assert_eq!(
        (last.done_bytes, last.total_bytes, last.files_done, last.files_total),
        (job.total_bytes, job.total_bytes, 3, 3)
    );
    assert_eq!(read(&s.install.join("Data/big.MPQ")), bytes(8, 3_000_000));
    assert!(InstallState::load(&s.install).job.is_none());
    assert!(r > p);
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn game_running_blocks_updates() {
    let srv = TestServer::start();
    let s = setup("en-running");
    let (e, rec) = install_v1(&srv, &s);
    drop(e);
    let mut spec = v1();
    spec.build = "v2".into();
    spec.files[1].content = bytes(9, 1000);
    srv.publish(&spec);
    let mut c = config(&srv.base, &public_key_b64(), &s.config);
    let seen = Arc::new(Mutex::new(String::new()));
    let seen2 = seen.clone();
    c.game_running = Some(Arc::new(move |name: &str| {
        *seen2.lock().unwrap() = name.to_string();
        true
    }));
    let (e, rec2) = start(c);
    let n = rec2.wait_phase(Phase::NeedsUpdate, 0);
    e.update();
    rec2.wait_phase(Phase::Error, n);
    assert_eq!(rec2.errors(n)[0].0, Code::GameRunning);
    assert_eq!(*seen.lock().unwrap(), "Bleakhold.exe");
    assert_eq!(read(&s.install.join("Data/common.MPQ")), bytes(1, 300_000));
    drop(rec);
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn repair_restores_a_damaged_file() {
    let srv = TestServer::start();
    let s = setup("en-repair");
    let (e, rec) = install_v1(&srv, &s);
    let p = s.install.join("Data/common.MPQ");
    let mtime = fs::metadata(&p).unwrap().modified().unwrap();
    let mut damaged = bytes(1, 300_000);
    damaged[1000] ^= 1;
    fs::write(&p, &damaged).unwrap();
    fs::File::options().write(true).open(&p).unwrap().set_modified(mtime).unwrap();
    let n = rec.len();
    e.check();
    rec.wait_phase(Phase::Ready, n);
    assert_eq!(read(&p), damaged, "a fast check trusts size and time");
    let n = rec.len();
    e.repair();
    let v = rec.wait_phase(Phase::Verifying, n);
    let first = rec.wait_progress(v);
    assert!(first.files_total >= 5, "verifying progress fills the file counts: {first:?}");
    rec.wait_phase(Phase::Ready, v);
    assert_eq!(rec.phases(n), [Phase::Verifying, Phase::Downloading, Phase::Ready]);
    assert_eq!(read(&p), bytes(1, 300_000));
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn existing_client_is_adopted() {
    let srv = TestServer::start();
    let s = setup("en-adopt");
    srv.publish(&v1());
    // A WoW folder that already has the big files.
    fs::create_dir_all(s.install.join("Data/enUS")).unwrap();
    fs::write(s.install.join("Data/common.MPQ"), bytes(1, 300_000)).unwrap();
    fs::write(s.install.join("Data/enUS/patch-enUS.MPQ"), bytes(2, 120_000)).unwrap();
    fs::write(s.install.join("Wow.exe"), b"blizzard").unwrap();
    let (e, rec) = start(config(&srv.base, &public_key_b64(), &s.config));
    let i = rec.wait_phase(Phase::NeedsInstall, 0);
    let info = e.folder_info(s.install.to_str().unwrap()).unwrap();
    assert!(info.has_game);
    assert_eq!(info.path, s.install.display().to_string(), "a WoW folder is used as it is");
    assert_eq!(info.needed_bytes, e.state().total_bytes - 420_000);
    e.install(s.install.to_str().unwrap(), false, false).unwrap();
    rec.wait_phase(Phase::Ready, i);
    assert_eq!(rec.phases(i), [Phase::Verifying, Phase::Downloading, Phase::Ready]);
    let objects: Vec<_> = srv.hits().into_iter().filter(|h| h.path.starts_with("objects/")).collect();
    assert_eq!(objects.len(), 4, "{objects:?}");
    assert!(s.install.join("Wow.exe").exists());
    assert_eq!(InstallState::load(&s.install).files.len(), 6);
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn a_folder_with_other_things_gets_a_bleakhold_subfolder() {
    let srv = TestServer::start();
    let s = setup("en-subfolder");
    srv.publish(&v1());
    let games = s.root.join("Games");
    fs::create_dir_all(games.join("Other Game")).unwrap();
    let (e, rec) = start(config(&srv.base, &public_key_b64(), &s.config));
    let i = rec.wait_phase(Phase::NeedsInstall, 0);
    let info = e.folder_info(games.to_str().unwrap()).unwrap();
    assert_eq!(info.path, games.join("Bleakhold").display().to_string());
    e.install(games.to_str().unwrap(), false, false).unwrap();
    rec.wait_phase(Phase::Ready, i);
    assert!(games.join("Bleakhold/Bleakhold.exe").exists());
    assert_eq!(e.state().install_dir, games.join("Bleakhold").display().to_string());
    fs::remove_dir_all(&s.root).unwrap();
}

#[cfg(unix)]
#[test]
fn play_sets_the_realmlist_empties_the_cache_and_starts_the_game() {
    use std::os::unix::fs::PermissionsExt;
    let srv = TestServer::start();
    let s = setup("en-play");
    let (e, rec) = install_v1(&srv, &s);
    let exe = s.install.join("Bleakhold.exe");
    fs::set_permissions(&exe, fs::Permissions::from_mode(0o755)).unwrap();
    fs::create_dir_all(s.install.join("Cache/WDB")).unwrap();
    fs::write(s.install.join("Cache/WDB/creaturecache.wdb"), b"stale").unwrap();
    e.save_settings(&json!({ "close_on_play": false })).unwrap();

    let n = rec.len();
    e.play().unwrap();
    let n2 = rec.wait_phase(Phase::Playing, n);
    rec.wait_phase(Phase::Ready, n2);
    assert_eq!(rec.phases(n), [Phase::Launching, Phase::Playing, Phase::Ready]);
    let pwd = fs::read_to_string(s.install.join("started.txt")).unwrap();
    assert_eq!(fs::canonicalize(pwd.trim()).unwrap(), fs::canonicalize(&s.install).unwrap());
    assert_eq!(read(&s.install.join("Data/enUS/realmlist.wtf")), b"set realmlist 127.0.0.1\r\n");
    assert_eq!(read(&s.install.join("WTF/Config.wtf")), b"SET gxWindow \"1\"\nSET realmList \"127.0.0.1\"\n");
    assert_eq!(fs::read_dir(s.install.join("Cache")).unwrap().count(), 0);
    assert_eq!(InstallState::load(&s.install).cache_epoch, 1);

    // close_on_play: the launcher quits once the game runs.
    e.save_settings(&json!({ "close_on_play": true })).unwrap();
    e.play().unwrap();
    rec.wait_quit();
    drop(e);

    // A replaced game executable is never started.
    let (e2, rec2) = start(config(&srv.base, &public_key_b64(), &s.config));
    rec2.wait_phase(Phase::Ready, 0);
    fs::write(&exe, b"#!/bin/sh\necho evil > evil.txt\n").unwrap();
    fs::set_permissions(&exe, fs::Permissions::from_mode(0o755)).unwrap();
    e2.play().unwrap();
    rec2.wait_phase(Phase::Error, 0);
    assert_eq!(rec2.errors(0)[0].0, Code::Launch);
    std::thread::sleep(Duration::from_millis(100));
    assert!(!s.install.join("evil.txt").exists());
    drop(e2);
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn offline_uses_the_last_verified_manifest() {
    let srv = TestServer::start();
    let s = setup("en-cached");
    let (e, _rec) = install_v1(&srv, &s);
    drop(e);
    let dead = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}/", dead.local_addr().unwrap());
    drop(dead);
    let (e, rec) = start(config(&base, &public_key_b64(), &s.config));
    rec.wait_phase(Phase::Offline, 0);
    let st = e.state();
    assert!(st.installed);
    assert_eq!(st.news.len(), 1, "news from the cached manifest");
    assert_eq!(st.build, "v1");
    assert!(st.message.contains("still play"));
    // Tampering with the cache: not used.
    drop(e);
    let cache = s.config.join("manifest-cache/manifest.json");
    let mut b = read(&cache);
    let i = b.iter().position(|&c| c == b'v').unwrap();
    b[i] = b'w';
    fs::write(&cache, b).unwrap();
    let (e, rec) = start(config(&base, &public_key_b64(), &s.config));
    rec.wait_phase(Phase::Offline, 0);
    assert!(e.state().news.is_empty());
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn realm_status_is_probed() {
    let srv = TestServer::start();
    let realm = TcpListener::bind("127.0.0.1:0").unwrap();
    let mut spec = v1();
    spec.server_port = Some(realm.local_addr().unwrap().port());
    srv.publish(&spec);
    let s = setup("en-realm");
    let (e, rec) = start(config(&srv.base, &public_key_b64(), &s.config));
    rec.wait_phase(Phase::NeedsInstall, 0);
    let end = Instant::now() + Duration::from_secs(10);
    loop {
        let online = rec.events().iter().any(|ev| matches!(ev, Ev::Server(v) if v.online && v.name == "Test Realm"));
        if online {
            break;
        }
        assert!(Instant::now() < end, "no online server event: {:?}", rec.events());
        std::thread::sleep(Duration::from_millis(50));
    }
    let sv = e.state().server.unwrap();
    assert!(sv.auth && sv.world && sv.ping_ms.is_some());
    fs::remove_dir_all(&s.root).unwrap();
}

#[test]
fn self_update_swaps_the_running_launcher() {
    let srv = TestServer::start();
    let s = setup("en-selfupdate");
    let mut spec = v1();
    let new_launcher = bytes(42, 50_000);
    spec.launcher = Some(("1.1.0".into(), new_launcher.clone()));
    srv.publish(&spec);
    let exe_dir = s.root.join("Downloads");
    fs::create_dir_all(&exe_dir).unwrap();
    let exe = exe_dir.join("BleakholdLauncher.exe");
    fs::write(&exe, b"launcher 1.0.0").unwrap();
    let mut c = config(&srv.base, &public_key_b64(), &s.config);
    c.current_exe = Some(exe.clone());
    let (_e, rec) = start(c);
    let i = rec.wait_phase(Phase::SelfUpdating, 0);
    let msg = rec.events().iter().find_map(|ev| match ev {
        Ev::Phase(Phase::SelfUpdating, m) => Some(m.clone()),
        _ => None,
    });
    assert!(msg.unwrap().contains("1.1.0"));
    // The swap happens; starting the new file fails here (it is not a real program), which is reported,
    // and the launcher carries on.
    rec.wait_phase(Phase::NeedsInstall, i);
    assert_eq!(read(&exe), new_launcher);
    assert_eq!(read(&exe_dir.join("BleakholdLauncher.old.exe")), b"launcher 1.0.0");
    assert!(rec.progress_after(i).last().unwrap().done_bytes == 50_000);
    assert!(rec.errors(i).iter().any(|(c, m)| *c == Code::Launch && m.contains("could not update itself")));
    drop(_e);

    // The "new" launcher still says 1.0.0 (a mislabelled publish): it must not update to the same file
    // again, or it would loop.
    let settings: serde_json::Value = serde_json::from_slice(&read(&s.config.join("settings.json"))).unwrap();
    assert_eq!(settings["self_update_sha"], json!(bleakhold_launcher_core::download::sha256_hex(&new_launcher)));
    let mut c = config(&srv.base, &public_key_b64(), &s.config);
    c.current_exe = Some(exe.clone());
    let (_e2, rec2) = start(c.clone());
    rec2.wait_phase(Phase::NeedsInstall, 0);
    assert!(!rec2.phases(0).contains(&Phase::SelfUpdating), "{:?}", rec2.phases(0));
    drop(_e2);

    // Once the running launcher is current, the guard is cleared.
    c.launcher_version = "1.1.0".into();
    let (_e3, rec3) = start(c);
    rec3.wait_phase(Phase::NeedsInstall, 0);
    std::thread::sleep(Duration::from_millis(50));
    let settings: serde_json::Value = serde_json::from_slice(&read(&s.config.join("settings.json"))).unwrap();
    assert!(settings.get("self_update_sha").is_none(), "{settings}");
    fs::remove_dir_all(&s.root).unwrap();
}
