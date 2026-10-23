//! The launcher's state machine (DESIGN.md "Update rules", "Window ↔ backend"). One worker thread owns
//! every long job (check, self-update, plan, download, play) and runs the window's commands one at a
//! time; pause and cancel reach it through the shared [`Control`]. A second thread probes the realm every
//! 30 s. The window side (Tauri) only forwards commands and turns [`Sink`] calls into events.

use std::ffi::OsString;
use std::fs;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex, MutexGuard, OnceLock};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use ed25519_dalek::VerifyingKey;
use serde::Serialize;
use serde_json::{Map, Value};

use crate::cache;
use crate::config::LauncherConfig;
use crate::download::{self, Control, Dest, Options, Progress, Task};
use crate::error::{Code, Error, Result};
use crate::folder::{self, FolderInfo};
use crate::http::{Http, Timeouts};
use crate::launch;
use crate::manifest::{Manifest, MAX_MANIFEST_BYTES};
use crate::paths;
use crate::planner::{self, Mode, Plan};
use crate::realmlist;
use crate::selfupdate;
use crate::server::{self, ServerTarget};
use crate::settings::Settings;
use crate::shortcut;
use crate::signature;
use crate::state::{FileState, InstallState, JobMark};
use crate::sys;
use crate::util::{human_bytes, mtime_ns, write_atomic};

/// The phases of DESIGN.md; the window's big button follows them.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Loading,
    Offline,
    NeedsInstall,
    NeedsUpdate,
    Downloading,
    Verifying,
    Paused,
    Ready,
    Launching,
    Playing,
    SelfUpdating,
    Error,
}

impl Phase {
    pub fn as_str(self) -> &'static str {
        match self {
            Phase::Loading => "loading",
            Phase::Offline => "offline",
            Phase::NeedsInstall => "needs_install",
            Phase::NeedsUpdate => "needs_update",
            Phase::Downloading => "downloading",
            Phase::Verifying => "verifying",
            Phase::Paused => "paused",
            Phase::Ready => "ready",
            Phase::Launching => "launching",
            Phase::Playing => "playing",
            Phase::SelfUpdating => "self_updating",
            Phase::Error => "error",
        }
    }
}

/// Where the engine reports to (the Tauri app emits these as the events of DESIGN.md).
pub trait Sink: Send + Sync + 'static {
    fn phase(&self, phase: Phase, message: &str);
    fn progress(&self, progress: &Progress);
    fn error(&self, code: Code, message: &str);
    fn server(&self, status: &ServerView);
    /// End the process: after a self-update started the new launcher, or when the game started and
    /// `close_on_play` is set.
    fn quit(&self);
}

/// Decides whether a game process with this executable name runs (tests replace it).
pub type ProcessCheck = Arc<dyn Fn(&str) -> bool + Send + Sync>;

#[derive(Clone)]
pub struct EngineConfig {
    pub launcher_version: String,
    pub launcher: LauncherConfig,
    /// Holds `settings.json`, the log and the last verified manifest.
    pub config_dir: PathBuf,
    /// The running launcher; `None` turns off self-update and the install folder copy.
    pub current_exe: Option<PathBuf>,
    /// Arguments to start the updated launcher with.
    pub args: Vec<OsString>,
    pub server_interval: Duration,
    pub probe_timeout: Duration,
    pub http_timeouts: Timeouts,
    /// First wait after a failed try (doubles).
    pub retry_backoff: Duration,
    /// Wait before fetching manifest and signature again when they do not match (a publish may have
    /// replaced one of the two files between the two downloads).
    pub signature_retry_delay: Duration,
    pub game_running: Option<ProcessCheck>,
}

impl EngineConfig {
    pub fn new(launcher_version: &str, launcher: LauncherConfig, config_dir: PathBuf) -> EngineConfig {
        EngineConfig {
            launcher_version: launcher_version.to_string(),
            launcher,
            config_dir,
            current_exe: None,
            args: Vec::new(),
            server_interval: Duration::from_secs(30),
            probe_timeout: Duration::from_secs(3),
            http_timeouts: Timeouts::default(),
            retry_backoff: Duration::from_secs(1),
            signature_retry_delay: Duration::from_secs(2),
            game_running: None,
        }
    }
}

/// `get_state` (DESIGN.md `State`).
#[derive(Clone, Debug, Serialize)]
pub struct StateView {
    pub launcher_version: String,
    pub phase: Phase,
    pub message: String,
    pub installed: bool,
    /// The install folder, or before installing the suggested one.
    pub install_dir: String,
    pub settings: SettingsView,
    pub build: String,
    pub total_bytes: u64,
    pub pending_bytes: u64,
    pub news: Vec<Value>,
    pub links: Map<String, Value>,
    /// `null` until the first probe.
    pub server: Option<ServerView>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SettingsView {
    pub parallel: u32,
    pub limit_mbps: u32,
    pub close_on_play: bool,
    pub shortcuts: bool,
}

impl From<&Settings> for SettingsView {
    fn from(s: &Settings) -> Self {
        SettingsView {
            parallel: s.parallel,
            limit_mbps: s.limit_mbps,
            close_on_play: s.close_on_play,
            shortcuts: s.shortcuts,
        }
    }
}

/// `State.server` and the `server` event.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ServerView {
    pub name: String,
    pub online: bool,
    pub auth: bool,
    pub world: bool,
    pub ping_ms: Option<u64>,
}

/// What a resumed job continues.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    Check,
    Install,
    Update,
    Repair,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum StopReason {
    None,
    Pause,
    Cancel,
    Shutdown,
}

enum Cmd {
    Startup,
    Check,
    Install {
        dir: PathBuf,
        desktop: bool,
        start_menu: bool,
    },
    Update,
    Repair,
    Resume,
    /// Cancel while paused: drop the unfinished job.
    Discard,
    Play,
    ClearCache,
    Shutdown,
}

/// Whether a command may run in a phase; checked when it is sent and again when the worker takes it.
type Gate = fn(Phase) -> bool;

struct CachedPlan {
    build: String,
    dir: PathBuf,
    plan: Plan,
}

struct Status {
    phase: Phase,
    message: String,
    settings: Settings,
    manifest: Option<Arc<Manifest>>,
    /// The manifest was fetched in this session (not the cached copy shown while offline).
    manifest_live: bool,
    installed: bool,
    local_build: String,
    local_total: u64,
    pending_bytes: u64,
    server: Option<ServerView>,
    plan: Option<CachedPlan>,
    resume: Option<Kind>,
    last_progress: Option<Progress>,
}

struct Inner {
    cfg: EngineConfig,
    key: std::result::Result<VerifyingKey, String>,
    sink: Arc<dyn Sink>,
    ctl: Control,
    http: Http,
    status: Mutex<Status>,
    /// Commands sent and not yet taken by the worker.
    queued: AtomicUsize,
    stop_reason: Mutex<StopReason>,
    shutdown: AtomicBool,
    probe_now: AtomicBool,
    default_dir: OnceLock<String>,
}

/// The engine handle the app keeps (commands are methods; all return quickly).
pub struct Engine {
    inner: Arc<Inner>,
    tx: Mutex<mpsc::Sender<(Cmd, Gate)>>,
    worker: Mutex<Option<JoinHandle<()>>>,
}

const DEFAULT_EXE: &str = "Bleakhold.exe";
const SAVE_EVERY: Duration = Duration::from_millis(500);
const BIG_FILE: u64 = 8 << 20;
const DISK_MARGIN: u64 = 64 << 20;
const MANIFEST_CACHE: &str = "manifest-cache";
/// Commands that may wait for the worker.
const MAX_QUEUED: usize = 2;

impl Engine {
    /// Loads the settings, starts the worker (which checks for updates right away) and the status thread.
    pub fn new(cfg: EngineConfig, sink: Arc<dyn Sink>) -> Engine {
        let settings = Settings::load(&cfg.config_dir);
        let ctl = Control::new();
        ctl.set_limit_bps(settings.limit_bps());
        let http = Http::new(
            &cfg.launcher.base_url,
            &format!("BleakholdLauncher/{}", cfg.launcher_version),
            cfg.http_timeouts,
        );
        let key = cfg.launcher.key();
        let inner = Arc::new(Inner {
            cfg,
            key,
            sink,
            ctl,
            http,
            status: Mutex::new(Status {
                phase: Phase::Loading,
                message: String::new(),
                settings,
                manifest: None,
                manifest_live: false,
                installed: false,
                local_build: String::new(),
                local_total: 0,
                pending_bytes: 0,
                server: None,
                plan: None,
                resume: None,
                last_progress: None,
            }),
            queued: AtomicUsize::new(0),
            stop_reason: Mutex::new(StopReason::None),
            shutdown: AtomicBool::new(false),
            probe_now: AtomicBool::new(false),
            default_dir: OnceLock::new(),
        });
        inner.refresh_local();
        let (tx, rx) = mpsc::channel();
        let w = inner.clone();
        let worker = thread::Builder::new()
            .name("bleakhold-worker".into())
            .spawn(move || w.worker_loop(rx))
            .expect("worker thread");
        let s = inner.clone();
        thread::Builder::new().name("bleakhold-status".into()).spawn(move || s.server_loop()).expect("status thread");
        let _ = tx.send((Cmd::Startup, |_| true));
        Engine { inner, tx: Mutex::new(tx), worker: Mutex::new(Some(worker)) }
    }

    pub fn state(&self) -> StateView {
        self.inner.view()
    }

    /// `folder_info` for the folder `install` would use for `path` (see [`folder::resolve_install_dir`]).
    pub fn folder_info(&self, path: &str) -> Result<FolderInfo> {
        let dir = folder::install_dir_for(path)?;
        let manifest = self.inner.st().manifest.clone();
        Ok(folder::folder_info(&dir, manifest.as_deref()))
    }

    /// `install`: checks the folder, then installs there in the background.
    pub fn install(&self, path: &str, desktop_shortcut: bool, start_menu: bool) -> Result<()> {
        if let Err(msg) = &self.inner.key {
            return Err(Error::signature(msg.clone()));
        }
        let dir = folder::install_dir_for(path)?;
        if !folder::is_writable(&dir) {
            return Err(Error::io_msg(format!(
                "The launcher cannot write to {}. Choose another folder, like {}.",
                dir.display(),
                self.inner.default_dir()
            )));
        }
        let accepted = self.submit(Cmd::Install { dir, desktop: desktop_shortcut, start_menu }, |p| {
            !matches!(p, Phase::Launching | Phase::Playing)
        });
        if accepted {
            Ok(())
        } else {
            Err(Error::io_msg("The launcher is busy. Try again in a moment."))
        }
    }

    /// `check`: fetch the manifest again (also the error phase's Retry).
    pub fn check(&self) {
        self.submit(Cmd::Check, |p| !matches!(p, Phase::Launching | Phase::Playing));
    }

    pub fn update(&self) {
        self.submit(Cmd::Update, |p| matches!(p, Phase::NeedsUpdate | Phase::Ready | Phase::Error));
    }

    pub fn repair(&self) {
        self.submit(Cmd::Repair, |p| !matches!(p, Phase::Launching | Phase::Playing | Phase::NeedsInstall));
    }

    /// `play`: rejected unless the game is ready (or installed while offline).
    pub fn play(&self) -> Result<()> {
        let ok = {
            let st = self.inner.st();
            st.phase == Phase::Ready || (st.phase == Phase::Offline && st.installed)
        };
        if ok && self.submit(Cmd::Play, |p| matches!(p, Phase::Ready | Phase::Offline)) {
            Ok(())
        } else {
            Err(Error::launch("The game can't start right now."))
        }
    }

    pub fn pause(&self) {
        self.stop_job(StopReason::Pause, &[Phase::Downloading, Phase::Verifying]);
    }

    pub fn resume(&self) {
        self.submit(Cmd::Resume, |p| p == Phase::Paused);
    }

    /// `cancel`: stops the download (or drops a paused one); back to needs_install or needs_update.
    pub fn cancel(&self) {
        if self.inner.st().phase == Phase::Paused {
            self.submit(Cmd::Discard, |p| p == Phase::Paused);
        } else {
            self.stop_job(StopReason::Cancel, &[Phase::Downloading, Phase::Verifying, Phase::SelfUpdating]);
        }
    }

    pub fn clear_cache(&self) {
        self.submit(Cmd::ClearCache, |p| !matches!(p, Phase::Launching | Phase::Playing));
    }

    /// `save_settings`: takes the keys the window may change, applies the speed limit at once (the
    /// number of parallel downloads applies to the next download) and returns the result.
    pub fn save_settings(&self, v: &Value) -> Result<Settings> {
        let s = {
            let mut st = self.inner.st();
            st.settings.merge_json(v);
            st.settings = st.settings.clone().normalized();
            st.settings.clone()
        };
        self.inner.ctl.set_limit_bps(s.limit_bps());
        s.save(&self.inner.cfg.config_dir)
            .map_err(|e| Error::io(format!("saving {}", Settings::path(&self.inner.cfg.config_dir).display()), &e))?;
        Ok(s)
    }

    /// The install folder, once the player installed.
    pub fn install_dir(&self) -> Option<PathBuf> {
        self.inner.install_dir()
    }

    /// Stops the running job and waits (at most `wait`) for the worker to save its state.
    pub fn shutdown(&self, wait: Duration) {
        self.inner.shutdown.store(true, Ordering::SeqCst);
        *self.inner.stop_reason.lock().unwrap_or_else(|e| e.into_inner()) = StopReason::Shutdown;
        self.inner.ctl.request_stop();
        if let Ok(tx) = self.tx.lock() {
            let _ = tx.send((Cmd::Shutdown, |_| true));
        }
        let handle = self.worker.lock().ok().and_then(|mut w| w.take());
        if let Some(h) = handle {
            let end = Instant::now() + wait;
            while !h.is_finished() && Instant::now() < end {
                thread::sleep(Duration::from_millis(20));
            }
            if h.is_finished() {
                let _ = h.join();
            }
        }
    }

    /// Queues a command for the worker (at most [`MAX_QUEUED`] waiting). A command sent while the worker
    /// finishes the previous one waits for it; its gate is checked again when it runs.
    fn submit(&self, cmd: Cmd, allowed: Gate) -> bool {
        let phase = self.inner.st().phase;
        if !allowed(phase) {
            log::info!("command ignored in phase {}", phase.as_str());
            return false;
        }
        if self.inner.queued.fetch_add(1, Ordering::SeqCst) >= MAX_QUEUED {
            self.inner.queued.fetch_sub(1, Ordering::SeqCst);
            log::info!("command ignored: {MAX_QUEUED} commands already waiting");
            return false;
        }
        match self.tx.lock() {
            Ok(tx) if tx.send((cmd, allowed)).is_ok() => true,
            _ => {
                self.inner.queued.fetch_sub(1, Ordering::SeqCst);
                false
            }
        }
    }

    fn stop_job(&self, reason: StopReason, phases: &[Phase]) {
        let phase = self.inner.st().phase;
        if phases.contains(&phase) {
            *self.inner.stop_reason.lock().unwrap_or_else(|e| e.into_inner()) = reason;
            self.inner.ctl.request_stop();
        }
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        self.inner.shutdown.store(true, Ordering::SeqCst);
        self.inner.ctl.request_stop();
        if let Ok(tx) = self.tx.lock() {
            let _ = tx.send((Cmd::Shutdown, |_| true));
        }
    }
}

impl Inner {
    fn st(&self) -> MutexGuard<'_, Status> {
        self.status.lock().unwrap_or_else(|e| e.into_inner())
    }

    fn default_dir(&self) -> String {
        self.default_dir.get_or_init(|| folder::default_install_dir().display().to_string()).clone()
    }

    fn view(&self) -> StateView {
        let default_dir = self.default_dir();
        let st = self.st();
        let m = st.manifest.as_deref();
        StateView {
            launcher_version: self.cfg.launcher_version.clone(),
            phase: st.phase,
            message: st.message.clone(),
            installed: st.installed,
            install_dir: st.settings.install_dir.clone().unwrap_or(default_dir),
            settings: SettingsView::from(&st.settings),
            build: m.map(|m| m.build.clone()).unwrap_or_else(|| st.local_build.clone()),
            total_bytes: m.map(Manifest::total_bytes).unwrap_or(st.local_total),
            pending_bytes: st.pending_bytes,
            news: m.map(|m| m.news.clone()).unwrap_or_default(),
            links: m.map(|m| m.links.clone()).unwrap_or_default(),
            server: st.server.clone(),
        }
    }

    fn set_phase(&self, phase: Phase, message: &str) {
        {
            let mut st = self.st();
            st.phase = phase;
            st.message = message.to_string();
        }
        log::info!("phase {}{}{}", phase.as_str(), if message.is_empty() { "" } else { ": " }, message);
        self.sink.phase(phase, message);
    }

    fn emit_progress(&self, p: &Progress) {
        self.st().last_progress = Some(p.clone());
        self.sink.progress(p);
    }

    /// Reports an error, then enters the error phase (Retry checks again).
    fn fail(&self, e: Error) {
        log::error!("{e}");
        self.sink.error(e.code, &e.message);
        self.set_phase(Phase::Error, &e.message);
    }

    fn install_dir(&self) -> Option<PathBuf> {
        self.st().settings.install_dir.as_ref().map(PathBuf::from)
    }

    /// The manifest fetched in this session; `None` while only the offline copy is known.
    fn live_manifest(&self) -> Option<Arc<Manifest>> {
        let st = self.st();
        st.manifest.clone().filter(|_| st.manifest_live)
    }

    fn manifest(&self) -> Option<Arc<Manifest>> {
        self.st().manifest.clone()
    }

    fn exe_name(&self, manifest: Option<&Manifest>, state: Option<&InstallState>) -> String {
        manifest
            .map(|m| m.exe.clone())
            .or_else(|| state.map(|s| s.exe.clone()).filter(|e| !e.is_empty()))
            .unwrap_or_else(|| DEFAULT_EXE.to_string())
    }

    /// Re-reads `installed`, the local build and size from the install folder.
    fn refresh_local(&self) {
        let dir = self.install_dir();
        let manifest = self.manifest();
        let (installed, build, total) = match dir {
            Some(d) if InstallState::exists(&d) => {
                let s = InstallState::load(&d);
                let exe = self.exe_name(manifest.as_deref(), Some(&s));
                let has_exe = paths::safe_join(&d, &exe).map(|p| p.is_file()).unwrap_or(false);
                (has_exe, s.build.clone(), s.total_bytes())
            }
            _ => (false, String::new(), 0),
        };
        let mut st = self.st();
        st.installed = installed;
        st.local_build = build;
        st.local_total = total;
    }

    fn game_running(&self, manifest: Option<&Manifest>) -> bool {
        let state = self.install_dir().map(|d| InstallState::load(&d));
        let exe = self.exe_name(manifest, state.as_ref());
        let name = exe.rsplit('/').next().unwrap_or(&exe).to_string();
        match &self.cfg.game_running {
            Some(f) => f(&name),
            None => sys::is_process_running(&name),
        }
    }

    fn take_stop_reason(&self) -> StopReason {
        let mut r = self.stop_reason.lock().unwrap_or_else(|e| e.into_inner());
        std::mem::replace(&mut *r, StopReason::None)
    }

    // ---- worker ----

    fn worker_loop(self: Arc<Self>, rx: mpsc::Receiver<(Cmd, Gate)>) {
        while let Ok((cmd, allowed)) = rx.recv() {
            if matches!(cmd, Cmd::Shutdown) || self.shutdown.load(Ordering::SeqCst) {
                break;
            }
            let phase = self.st().phase;
            if !matches!(cmd, Cmd::Startup) {
                self.queued.fetch_sub(1, Ordering::SeqCst);
            }
            if !allowed(phase) {
                log::info!("queued command dropped in phase {}", phase.as_str());
                continue;
            }
            self.ctl.clear();
            *self.stop_reason.lock().unwrap_or_else(|e| e.into_inner()) = StopReason::None;
            let me = self.clone();
            if catch_unwind(AssertUnwindSafe(move || me.run(cmd))).is_err() {
                self.fail(Error::io_msg("The launcher hit an internal error. Try again."));
            }
        }
        log::info!("worker stopped");
    }

    fn run(self: Arc<Self>, cmd: Cmd) {
        match cmd {
            Cmd::Startup => self.startup(),
            Cmd::Check => {
                // Retry after a failed download continues it; a plain check shows it as paused.
                let from_error = self.st().phase == Phase::Error;
                self.check_flow(from_error)
            }
            Cmd::Install { dir, desktop, start_menu } => self.install_flow(dir, desktop, start_menu),
            Cmd::Update => self.update_flow(Kind::Update),
            Cmd::Repair => self.repair_flow(),
            Cmd::Resume => {
                let kind = self.st().resume.unwrap_or(Kind::Update);
                match kind {
                    Kind::Check => self.check_flow(true),
                    Kind::Repair => self.repair_flow(),
                    k => self.update_flow(k),
                }
            }
            Cmd::Discard => self.discard_job(),
            Cmd::Play => self.play_flow(),
            Cmd::ClearCache => self.clear_cache_flow(),
            Cmd::Shutdown => {}
        }
    }

    fn startup(&self) {
        log::info!("Bleakhold Launcher {} starting", self.cfg.launcher_version);
        if let Some(exe) = &self.cfg.current_exe {
            selfupdate::cleanup(exe);
        }
        self.check_flow(false);
    }

    /// Verified, valid manifest (and its bytes and signature). A signature failure is retried once
    /// after a moment: a publish may have replaced one of the two files between the two downloads.
    fn fetch_manifest(&self) -> Result<(Manifest, Vec<u8>, Vec<u8>)> {
        let key = self.key.as_ref().map_err(|m| Error::signature(m.clone()))?;
        let mut tries = 0;
        loop {
            let bytes = self.http.get_small("manifest.json", MAX_MANIFEST_BYTES)?;
            let sig = self.http.get_small("manifest.json.sig", 4096)?;
            match signature::verify(&bytes, &sig, key) {
                Ok(()) => return Manifest::parse(&bytes).map(|m| (m, bytes, sig)),
                Err(e) if tries == 0 => {
                    log::warn!("manifest signature did not verify, fetching again: {}", e.message);
                    tries += 1;
                    thread::sleep(self.cfg.signature_retry_delay);
                }
                Err(e) => return Err(e),
            }
        }
    }

    /// Fetches and stores the manifest (and keeps a copy for offline starts).
    fn load_live_manifest(&self) -> Result<Arc<Manifest>> {
        let (m, bytes, sig) = self.fetch_manifest()?;
        let m = Arc::new(m);
        let dir = self.cfg.config_dir.join(MANIFEST_CACHE);
        if let Err(e) = write_atomic(&dir.join("manifest.json"), &bytes)
            .and_then(|_| write_atomic(&dir.join("manifest.json.sig"), &sig))
        {
            log::warn!("could not keep a copy of the manifest: {e}");
        }
        {
            let mut st = self.st();
            st.manifest = Some(m.clone());
            st.manifest_live = true;
            st.plan = None;
        }
        self.probe_now.store(true, Ordering::SeqCst);
        Ok(m)
    }

    /// The copy of the last verified manifest, verified again (for news, links and Play while offline).
    fn cached_manifest(&self) -> Option<Manifest> {
        let key = self.key.as_ref().ok()?;
        let dir = self.cfg.config_dir.join(MANIFEST_CACHE);
        let bytes = fs::read(dir.join("manifest.json")).ok()?;
        let sig = fs::read(dir.join("manifest.json.sig")).ok()?;
        signature::verify(&bytes, &sig, key).ok()?;
        Manifest::parse(&bytes).ok()
    }

    fn check_flow(&self, resume_job: bool) {
        self.st().resume = None;
        if let Err(msg) = &self.key {
            return self.fail(Error::signature(msg.clone()));
        }
        self.set_phase(Phase::Loading, "Checking for updates…");
        let manifest = match self.load_live_manifest() {
            Ok(m) => m,
            Err(e) if e.code == Code::Network => return self.go_offline(&e),
            Err(e) => return self.fail(e),
        };
        log::info!(
            "manifest build {:?}: {} files, {}",
            manifest.build,
            manifest.files.len(),
            human_bytes(manifest.total_bytes())
        );
        self.refresh_local();

        if let (Some(info), Some(exe)) = (&manifest.launcher, &self.cfg.current_exe) {
            let newer = selfupdate::is_newer(&info.version, &self.cfg.launcher_version);
            let tried = self.st().settings.self_update_sha.clone();
            if !newer && tried.is_some() {
                self.remember_self_update(None);
            }
            if newer && tried.as_deref() == Some(info.sha256.as_str()) {
                // We are the launcher that update installed, yet still older than the manifest says:
                // the published launcher is mislabelled. Updating again would loop.
                log::error!(
                    "the launcher {} ({}) was installed already and still reports {}; not updating again",
                    info.version,
                    info.sha256,
                    self.cfg.launcher_version
                );
            } else if newer {
                match self.self_update(&manifest, exe) {
                    Ok(()) => return self.sink.quit(),
                    Err(e) if e.is_cancelled() => {
                        if self.take_stop_reason() == StopReason::Shutdown {
                            return;
                        }
                        self.ctl.clear();
                        log::info!("launcher update cancelled");
                    }
                    Err(e) => {
                        log::error!("self-update failed: {e}");
                        self.sink.error(e.code, &format!("The launcher could not update itself: {}", e.message));
                    }
                }
            }
        }
        self.keep_install_copy(&manifest);
        self.plan_and_show(&manifest, resume_job);
    }

    fn go_offline(&self, e: &Error) {
        log::warn!("offline: {e}");
        let cached = if self.st().manifest.is_none() { self.cached_manifest().map(Arc::new) } else { None };
        {
            let mut st = self.st();
            if cached.is_some() {
                st.manifest = cached;
            }
            st.manifest_live = false;
            st.plan = None;
        }
        self.refresh_local();
        let installed = self.st().installed;
        let msg = if installed {
            "The update server can't be reached. You can still play."
        } else {
            "The update server can't be reached. Check your connection and try again."
        };
        self.set_phase(Phase::Offline, msg);
    }

    fn self_update(&self, manifest: &Manifest, exe: &Path) -> Result<()> {
        let info = manifest.launcher.as_ref().expect("checked by caller");
        self.set_phase(Phase::SelfUpdating, &format!("Bleakhold Launcher {} is out. Updating…", info.version));
        let new = selfupdate::download(
            &self.http,
            &manifest.objects,
            info,
            exe,
            &self.ctl,
            self.cfg.retry_backoff,
            &mut |p| self.emit_progress(p),
        )?;
        self.remember_self_update(Some(info.sha256.clone()));
        selfupdate::swap(exe, &new)?;
        log::info!("launcher {} in place, restarting", info.version);
        selfupdate::restart(exe, &self.cfg.args)
    }

    /// Records (or clears) the launcher hash a self-update installed, so the new launcher never updates
    /// to that same file again.
    fn remember_self_update(&self, sha: Option<String>) {
        let s = {
            let mut st = self.st();
            st.settings.self_update_sha = sha;
            st.settings.clone()
        };
        if let Err(e) = s.save(&self.cfg.config_dir) {
            log::warn!("could not save settings: {e}");
        }
    }

    /// Keeps `<install>\Bleakhold Launcher.exe` the running launcher when this one is current.
    fn keep_install_copy(&self, manifest: &Manifest) {
        let (Some(exe), Some(dir)) = (&self.cfg.current_exe, self.install_dir()) else {
            return;
        };
        if !InstallState::exists(&dir) {
            return;
        }
        if manifest.launcher.as_ref().is_some_and(|l| selfupdate::is_newer(&l.version, &self.cfg.launcher_version)) {
            return;
        }
        if let Err(e) = selfupdate::ensure_install_copy(exe, &dir) {
            log::warn!("could not refresh the launcher copy: {e}");
        }
    }

    /// Plans (fast) and shows the result: needs_install, needs_update, ready, or paused when an
    /// unfinished download is found (`resume_job` continues it instead).
    fn plan_and_show(&self, manifest: &Arc<Manifest>, resume_job: bool) {
        let dir = match self.install_dir() {
            Some(d) if d.is_dir() && (InstallState::exists(&d) || folder::has_game(&d)) => d,
            _ => {
                self.st().pending_bytes = manifest.total_bytes();
                return self.set_phase(Phase::NeedsInstall, "");
            }
        };
        self.st().resume = Some(Kind::Check);
        let plan = match self.make_plan(manifest, &dir, Mode::Fast) {
            Ok(p) => p,
            Err(e) if e.is_cancelled() => return self.after_stop(),
            Err(e) => return self.fail(e),
        };
        self.st().resume = None;
        if plan.downloads.is_empty() {
            // Nothing to download: drop what the manifest no longer lists and be ready.
            if let Err(e) = self.finish_install(manifest, &dir, &plan) {
                return self.fail(e);
            }
            return self.set_phase(Phase::Ready, "");
        }
        let job = InstallState::load(&dir).job.filter(|j| job_fits(j, &manifest.build, &plan));
        let installed = self.st().installed;
        {
            let mut st = self.st();
            st.pending_bytes = plan.download_bytes;
            st.plan = Some(CachedPlan { build: manifest.build.clone(), dir: dir.clone(), plan: plan.clone() });
        }
        if let Some(job) = job {
            if resume_job {
                if self.game_running(Some(manifest)) {
                    return self.fail(Error::game_running("Close the game first, then update."));
                }
                self.st().plan = None;
                self.st().resume = Some(Kind::Update);
                return self.run_plan(manifest, &dir, plan);
            }
            self.st().resume = Some(Kind::Update);
            self.set_phase(Phase::Paused, "Paused");
            let files_done = job.files_total - plan.downloads.len();
            return self.emit_progress(&Progress {
                done_bytes: job.total_bytes - plan.download_bytes,
                total_bytes: job.total_bytes,
                speed_bps: 0,
                eta_s: None,
                file: String::new(),
                files_done,
                files_total: job.files_total,
            });
        }
        let msg = format!("{} files to download, {}", plan.downloads.len(), human_bytes(plan.download_bytes));
        if installed {
            self.set_phase(Phase::NeedsUpdate, &msg);
        } else {
            self.set_phase(Phase::NeedsInstall, &msg);
        }
    }

    /// Runs the planner with the verifying phase and progress while it hashes; adopts and forgets state
    /// entries as it goes (saved now and then and at the end).
    fn make_plan(&self, manifest: &Manifest, dir: &Path, mode: Mode) -> Result<Plan> {
        let mut state = InstallState::load(dir);
        let snapshot = state.clone();
        let mut dirty = false;
        let mut last_save = Instant::now();
        let mut last_emit: Option<Instant> = None;
        let mut shown = false;
        let started = Instant::now();
        let msg = if mode == Mode::Repair { "Checking every file…" } else { "Checking files…" };
        let res = planner::plan(
            manifest,
            dir,
            &snapshot,
            mode,
            &|| self.ctl.stopped(),
            &mut |vp| {
                if !shown {
                    shown = true;
                    self.set_phase(Phase::Verifying, msg);
                }
                if last_emit.is_some_and(|t| t.elapsed() < Duration::from_millis(250)) && vp.done_bytes < vp.total_bytes
                {
                    return;
                }
                last_emit = Some(Instant::now());
                let secs = started.elapsed().as_secs_f64();
                let speed = if secs > 0.2 { (vp.done_bytes as f64 / secs) as u64 } else { 0 };
                let left = vp.total_bytes - vp.done_bytes.min(vp.total_bytes);
                self.emit_progress(&Progress {
                    done_bytes: vp.done_bytes,
                    total_bytes: vp.total_bytes,
                    speed_bps: speed,
                    eta_s: (speed > 0).then(|| left.div_ceil(speed)),
                    file: vp.file.clone(),
                    files_done: vp.files_done,
                    files_total: vp.files_total,
                });
            },
            &mut |p, entry| {
                match entry {
                    Some(e) => state.record(e),
                    None => state.forget(p),
                }
                dirty = true;
                if last_save.elapsed() >= SAVE_EVERY {
                    if let Err(e) = state.save(dir) {
                        log::warn!("{e}");
                    }
                    last_save = Instant::now();
                }
            },
        );
        if dirty {
            state.save(dir)?;
        }
        res
    }

    fn update_flow(&self, kind: Kind) {
        let Some(manifest) = self.live_manifest() else {
            return self.check_flow(true);
        };
        let Some(dir) = self.install_dir() else {
            return self.set_phase(Phase::NeedsInstall, "");
        };
        if self.game_running(Some(&manifest)) {
            return self.fail(Error::game_running("Close the game first, then update."));
        }
        self.st().resume = Some(kind);
        let cached = {
            let mut st = self.st();
            match st.plan.take() {
                Some(c) if c.build == manifest.build && c.dir == dir => Some(c.plan),
                _ => None,
            }
        };
        let plan = match cached {
            Some(p) => p,
            None => match self.make_plan(&manifest, &dir, Mode::Fast) {
                Ok(p) => p,
                Err(e) if e.is_cancelled() => return self.after_stop(),
                Err(e) => return self.fail(e),
            },
        };
        self.run_plan(&manifest, &dir, plan);
    }

    fn repair_flow(&self) {
        let Some(manifest) = self.live_manifest() else {
            return self.check_flow(false);
        };
        let Some(dir) = self.install_dir().filter(|d| d.is_dir()) else {
            return self.set_phase(Phase::NeedsInstall, "");
        };
        if self.game_running(Some(&manifest)) {
            return self.fail(Error::game_running("Close the game first, then repair."));
        }
        {
            let mut st = self.st();
            st.resume = Some(Kind::Repair);
            st.plan = None;
        }
        let plan = match self.make_plan(&manifest, &dir, Mode::Repair) {
            Ok(p) => p,
            Err(e) if e.is_cancelled() => return self.after_stop(),
            Err(e) => return self.fail(e),
        };
        // Damaged files were dropped from the state, so a resumed download plans them again.
        self.st().resume = Some(Kind::Update);
        self.run_plan(&manifest, &dir, plan);
    }

    fn install_flow(&self, dir: PathBuf, desktop: bool, start_menu: bool) {
        if let Err(e) = fs::create_dir_all(&dir) {
            return self.fail(Error::io(format!("creating {}", dir.display()), &e));
        }
        let manifest = match self.live_manifest() {
            Some(m) => m,
            None => match self.load_live_manifest() {
                Ok(m) => m,
                Err(e) if e.code == Code::Network => {
                    return self.fail(Error::network("The update server can't be reached. Try again later."))
                }
                Err(e) => return self.fail(e),
            },
        };
        let settings = {
            let mut st = self.st();
            st.settings.install_dir = Some(dir.display().to_string());
            st.settings.shortcuts = desktop || start_menu;
            st.plan = None;
            st.settings.clone()
        };
        if let Err(e) = settings.save(&self.cfg.config_dir) {
            log::warn!("could not save settings: {e}");
        }
        log::info!("installing into {}", dir.display());
        if let Some(exe) = &self.cfg.current_exe {
            match selfupdate::ensure_install_copy(exe, &dir) {
                Ok(copy) => {
                    if let Err(e) = shortcut::create(&copy, &dir, desktop, start_menu) {
                        log::warn!("shortcuts: {e}");
                    }
                }
                Err(e) => log::warn!("could not copy the launcher into the install folder: {e}"),
            }
        }
        self.st().resume = Some(Kind::Install);
        let plan = match self.make_plan(&manifest, &dir, Mode::Fast) {
            Ok(p) => p,
            Err(e) if e.is_cancelled() => return self.after_stop(),
            Err(e) => return self.fail(e),
        };
        self.run_plan(&manifest, &dir, plan);
    }

    /// Downloads the plan's files (state saved as files land; progress counted over the whole job, also
    /// across restarts), then deletes stale files and records the build. Ends in ready, paused,
    /// needs_* (cancelled) or error.
    fn run_plan(&self, manifest: &Manifest, dir: &Path, plan: Plan) {
        if !plan.downloads.is_empty() {
            let parts: u64 = plan
                .downloads
                .iter()
                .filter_map(|j| paths::safe_join(dir, &j.p).ok())
                .filter_map(|p| fs::metadata(paths::part_path(&p)).ok())
                .map(|m| m.len())
                .sum();
            let need = plan.download_bytes.saturating_sub(parts);
            if let Some(free) = sys::free_space(dir) {
                if free < need.saturating_add(DISK_MARGIN) {
                    return self.fail(Error::new(
                        Code::DiskFull,
                        format!(
                            "Not enough free space: {} needed, {} free on this drive.",
                            human_bytes(need + DISK_MARGIN),
                            human_bytes(free)
                        ),
                    ));
                }
            }
            let mut state = InstallState::load(dir);
            let job = state.job.clone().filter(|j| job_fits(j, &manifest.build, &plan)).unwrap_or(JobMark {
                build: manifest.build.clone(),
                total_bytes: plan.download_bytes,
                files_total: plan.downloads.len(),
            });
            state.job = Some(job.clone());
            if let Err(e) = state.save(dir) {
                return self.fail(e);
            }
            let base_bytes = job.total_bytes - plan.download_bytes;
            let base_files = job.files_total - plan.downloads.len();
            self.st().pending_bytes = plan.download_bytes;
            self.set_phase(
                Phase::Downloading,
                &format!("Downloading {} files, {}", plan.downloads.len(), human_bytes(plan.download_bytes)),
            );
            let tasks: Vec<Task> = plan
                .downloads
                .iter()
                .map(|j| Task {
                    url: self.http.url(&manifest.object_path(&j.h)),
                    mirror: j.u.clone(),
                    dest: Dest::Install { root: dir.to_path_buf(), rel: j.p.clone() },
                    size: j.s,
                    sha256: j.h.clone(),
                    label: j.p.clone(),
                })
                .collect();
            let opts = Options {
                parallel: self.st().settings.parallel as usize,
                backoff: self.cfg.retry_backoff,
                ..Options::default()
            };
            let mut last_save = Instant::now();
            let res = download::run(
                &self.http,
                &tasks,
                &opts,
                &self.ctl,
                &mut |p| {
                    let mut q = p.clone();
                    q.done_bytes += base_bytes;
                    q.total_bytes = job.total_bytes;
                    q.files_done += base_files;
                    q.files_total = job.files_total;
                    self.emit_progress(&q)
                },
                &mut |i, target| {
                    let j = &plan.downloads[i];
                    let meta = fs::metadata(target).map_err(|e| Error::io(format!("reading {}", j.p), &e))?;
                    state.record(FileState {
                        p: j.p.clone(),
                        s: j.s,
                        h: j.h.clone(),
                        size: meta.len(),
                        mtime: mtime_ns(&meta),
                        once: j.once,
                    });
                    if last_save.elapsed() >= SAVE_EVERY || j.s >= BIG_FILE {
                        state.save(dir)?;
                        last_save = Instant::now();
                    }
                    Ok(())
                },
            );
            let saved = state.save(dir);
            match res {
                Ok(()) => {}
                Err(e) if e.is_cancelled() => return self.after_stop(),
                Err(e) => {
                    let e = if e.code == Code::Io && self.game_running(Some(manifest)) {
                        Error::game_running(format!("{} Close the game and try again.", e.message))
                    } else {
                        e
                    };
                    return self.fail(e);
                }
            }
            if let Err(e) = saved {
                return self.fail(e);
            }
        }
        if let Err(e) = self.finish_install(manifest, dir, &plan) {
            return self.fail(e);
        }
        self.set_phase(Phase::Ready, "");
    }

    /// Deletes stale tracked files, records build, exe and realmlist, clears the job mark and refreshes
    /// the window's facts.
    fn finish_install(&self, manifest: &Manifest, dir: &Path, plan: &Plan) -> Result<()> {
        let mut state = InstallState::load(dir);
        planner::delete_stale(dir, &plan.deletes, &mut state);
        state.build.clone_from(&manifest.build);
        state.exe.clone_from(&manifest.exe);
        state.realmlist.clone_from(&manifest.realmlist);
        state.job = None;
        state.save(dir)?;
        {
            let mut st = self.st();
            st.pending_bytes = 0;
            st.resume = None;
            st.plan = None;
            st.last_progress = None;
        }
        self.refresh_local();
        Ok(())
    }

    /// After a stopped job: paused (resume continues), or back to needs_install/needs_update.
    fn after_stop(&self) {
        let reason = self.take_stop_reason();
        self.ctl.clear();
        match reason {
            StopReason::Shutdown => {}
            StopReason::Pause => {
                self.set_phase(Phase::Paused, "Paused");
                let last = self.st().last_progress.clone();
                if let Some(mut p) = last {
                    p.speed_bps = 0;
                    p.eta_s = None;
                    self.emit_progress(&p);
                }
            }
            StopReason::Cancel | StopReason::None => self.discard_job(),
        }
    }

    /// Drops the unfinished job (its `.part` files stay for a later download) and shows needs_install or
    /// needs_update.
    fn discard_job(&self) {
        if let Some(dir) = self.install_dir() {
            if InstallState::exists(&dir) {
                let mut state = InstallState::load(&dir);
                if state.job.take().is_some() {
                    if let Err(e) = state.save(&dir) {
                        log::warn!("{e}");
                    }
                }
            }
        }
        {
            let mut st = self.st();
            st.resume = None;
            st.last_progress = None;
        }
        self.refresh_local();
        if self.st().installed {
            self.set_phase(Phase::NeedsUpdate, "Stopped")
        } else {
            self.set_phase(Phase::NeedsInstall, "")
        }
    }

    fn play_flow(self: &Arc<Self>) {
        let Some(dir) = self.install_dir() else {
            return self.set_phase(Phase::NeedsInstall, "");
        };
        let before = self.st().phase;
        let before_msg = self.st().message.clone();
        let manifest = self.manifest();
        let mut state = InstallState::load(&dir);
        let exe = self.exe_name(manifest.as_deref(), Some(&state));
        let expected = match manifest.as_deref() {
            Some(m) => m.file(&m.exe).map(|f| f.h.clone()),
            None => state.files.get(&exe).map(|f| f.h.clone()),
        };
        let realm = manifest
            .as_ref()
            .map(|m| m.realmlist.clone())
            .or_else(|| Some(state.realmlist.clone()).filter(|r| !r.is_empty()))
            .unwrap_or_else(|| self.cfg.launcher.realmlist.clone());
        self.set_phase(Phase::Launching, "Starting the game…");
        let Some(expected) = expected else {
            return self.fail(Error::launch(format!(
                "{exe} is not among the realm's files, so the launcher will not start it."
            )));
        };
        if let Err(e) = launch::verify_exe(&dir, &exe, &state, &expected) {
            return self.fail(e);
        }
        if let Err(e) = realmlist::apply(&dir, &realm) {
            return self.fail(e);
        }
        if let Some(m) = manifest.as_deref() {
            match cache::apply_epoch(&dir, &mut state, m.cache_epoch) {
                Ok(true) => {
                    if let Err(e) = state.save(&dir) {
                        log::warn!("{e}");
                    }
                }
                Ok(false) => {}
                Err(e) => log::warn!("could not empty the cache: {e}"),
            }
        }
        let mut child = match launch::start_game(&dir, &exe) {
            Ok(c) => c,
            Err(e) => return self.fail(e),
        };
        log::info!("started {exe} (pid {})", child.id());
        self.set_phase(Phase::Playing, "");
        if self.st().settings.close_on_play {
            return self.sink.quit();
        }
        let me = self.clone();
        let (back, msg) =
            if before == Phase::Offline { (Phase::Offline, before_msg) } else { (Phase::Ready, String::new()) };
        thread::spawn(move || {
            let status = child.wait();
            log::info!("game exited: {status:?}");
            if me.st().phase == Phase::Playing {
                me.set_phase(back, &msg);
            }
        });
    }

    fn clear_cache_flow(&self) {
        let Some(dir) = self.install_dir() else {
            return;
        };
        if self.game_running(self.manifest().as_deref()) {
            self.sink.error(Code::GameRunning, "Close the game first, then clear the cache.");
            return;
        }
        match cache::clear_cache(&dir) {
            Ok(()) => log::info!("cache cleared"),
            Err(e) => self.sink.error(e.code, &e.message),
        }
    }

    // ---- realm status ----

    fn server_target(&self) -> ServerTarget {
        let st = self.st();
        if let Some(s) = st.manifest.as_ref().and_then(|m| m.server.as_ref()) {
            let name = if s.name.is_empty() { "Bleakhold".to_string() } else { s.name.clone() };
            return ServerTarget { name, host: s.host.clone(), auth_port: s.auth_port, world_port: s.world_port };
        }
        let realm =
            st.manifest.as_ref().map(|m| m.realmlist.clone()).unwrap_or_else(|| self.cfg.launcher.realmlist.clone());
        let (host, port) = match realm.rsplit_once(':') {
            Some((h, p)) if p.parse::<u16>().is_ok() => (h.to_string(), p.parse().unwrap_or(3724)),
            _ => (realm, 3724),
        };
        let name = st
            .manifest
            .as_ref()
            .map(|m| m.product.clone())
            .filter(|p| !p.is_empty())
            .unwrap_or_else(|| "Bleakhold".into());
        ServerTarget { name, host, auth_port: port, world_port: 8085 }
    }

    fn server_loop(self: Arc<Self>) {
        while !self.shutdown.load(Ordering::SeqCst) {
            self.probe_now.store(false, Ordering::SeqCst);
            let target = self.server_target();
            let s = server::probe(&target, self.cfg.probe_timeout);
            if self.shutdown.load(Ordering::SeqCst) {
                return;
            }
            let view =
                ServerView { name: target.name, online: s.online, auth: s.auth, world: s.world, ping_ms: s.ping_ms };
            self.st().server = Some(view.clone());
            self.sink.server(&view);
            let end = Instant::now() + self.cfg.server_interval;
            while Instant::now() < end {
                if self.shutdown.load(Ordering::SeqCst) || self.probe_now.load(Ordering::SeqCst) {
                    break;
                }
                thread::sleep(Duration::from_millis(100));
            }
        }
    }
}

/// Whether an unfinished job mark still describes `plan` (same build, and the plan is what is left of it).
fn job_fits(job: &JobMark, build: &str, plan: &Plan) -> bool {
    job.build == build && job.total_bytes >= plan.download_bytes && job.files_total >= plan.downloads.len()
}
