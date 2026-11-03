//! Bleakhold Launcher: the window. Everything the launcher does lives in `bleakhold_launcher_core` (the
//! engine); this file only opens the window, forwards the window's commands to the engine and turns the
//! engine's reports into the events of `Tools/Launcher/DESIGN.md`.

// A windowed program: no console window, also in debug builds.
#![windows_subsystem = "windows"]

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use bleakhold_launcher_core::engine::{Engine, EngineConfig, Phase, ServerView, Sink, StateView};
use bleakhold_launcher_core::{logger, selfupdate, sys, util, Code, FolderInfo, LauncherConfig, Progress};
use serde::Serialize;
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager, Monitor, State, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

/// Where the update server is, the manifest key and the fallback realmlist (compiled in).
const LAUNCHER_JSON: &str = include_str!("../launcher.json");
/// The window's designed size (logical pixels).
const WIDTH: f64 = 1180.0;
const HEIGHT: f64 = 700.0;

/// A failed command: the promise rejects with `{ code, message }`.
#[derive(Debug, Serialize)]
struct CmdError {
    code: &'static str,
    message: String,
}

impl From<bleakhold_launcher_core::Error> for CmdError {
    fn from(e: bleakhold_launcher_core::Error) -> Self {
        CmdError { code: e.code.as_str(), message: e.message }
    }
}

impl CmdError {
    fn new(code: Code, message: impl Into<String>) -> Self {
        CmdError { code: code.as_str(), message: message.into() }
    }
}

type CmdResult<T = ()> = Result<T, CmdError>;

/// Sends the engine's reports to the window as events.
struct WindowSink {
    app: AppHandle,
}

impl Sink for WindowSink {
    fn phase(&self, phase: Phase, message: &str) {
        let _ = self.app.emit("phase", json!({ "phase": phase, "message": message }));
    }

    fn progress(&self, progress: &Progress) {
        let _ = self.app.emit("progress", progress);
    }

    fn error(&self, code: Code, message: &str) {
        let _ = self.app.emit("error", json!({ "code": code.as_str(), "message": message }));
    }

    fn server(&self, status: &ServerView) {
        let _ = self.app.emit("server", status);
    }

    fn quit(&self) {
        self.app.exit(0);
    }
}

// ---- commands (DESIGN.md "Window ↔ backend"); arguments are snake_case exactly as the contract says ----

#[tauri::command(rename_all = "snake_case")]
async fn get_state(engine: State<'_, Engine>) -> CmdResult<StateView> {
    Ok(engine.state())
}

#[tauri::command(rename_all = "snake_case")]
async fn choose_folder(window: WebviewWindow, engine: State<'_, Engine>) -> CmdResult<Option<String>> {
    // Open the dialog where the current or suggested folder is (its nearest existing parent).
    let start = sys::nearest_existing(&PathBuf::from(engine.state().install_dir));
    let picked = tauri::async_runtime::spawn_blocking(move || {
        let mut dialog = window.dialog().file().set_title("Choose a folder for Bleakhold").set_parent(&window);
        if let Some(dir) = start {
            dialog = dialog.set_directory(dir);
        }
        dialog.blocking_pick_folder()
    })
    .await
    .map_err(|e| CmdError::new(Code::Io, format!("The folder dialog failed: {e}")))?;
    match picked {
        None => Ok(None),
        Some(p) => p
            .simplified()
            .into_path()
            .map(|p| Some(p.display().to_string()))
            .map_err(|e| CmdError::new(Code::Io, format!("That folder can't be used: {e}"))),
    }
}

#[tauri::command(rename_all = "snake_case")]
async fn folder_info(path: String, engine: State<'_, Engine>) -> CmdResult<FolderInfo> {
    Ok(engine.folder_info(&path)?)
}

#[tauri::command(rename_all = "snake_case")]
async fn install(path: String, desktop_shortcut: bool, start_menu: bool, engine: State<'_, Engine>) -> CmdResult {
    Ok(engine.install(&path, desktop_shortcut, start_menu)?)
}

#[tauri::command(rename_all = "snake_case")]
async fn check(engine: State<'_, Engine>) -> CmdResult {
    engine.check();
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn update(engine: State<'_, Engine>) -> CmdResult {
    engine.update();
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn pause(engine: State<'_, Engine>) -> CmdResult {
    engine.pause();
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn resume(engine: State<'_, Engine>) -> CmdResult {
    engine.resume();
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn cancel(engine: State<'_, Engine>) -> CmdResult {
    engine.cancel();
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn repair(engine: State<'_, Engine>) -> CmdResult {
    engine.repair();
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn play(engine: State<'_, Engine>) -> CmdResult {
    Ok(engine.play()?)
}

#[tauri::command(rename_all = "snake_case")]
async fn save_settings(settings: Value, engine: State<'_, Engine>) -> CmdResult {
    engine.save_settings(&settings)?;
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn open_folder(app: AppHandle, engine: State<'_, Engine>) -> CmdResult {
    let dir = engine
        .install_dir()
        .filter(|d| d.is_dir())
        .ok_or_else(|| CmdError::new(Code::Io, "The game is not installed yet."))?;
    app.opener()
        .open_path(dir.display().to_string(), None::<&str>)
        .map_err(|e| CmdError::new(Code::Io, format!("The folder could not be opened: {e}")))
}

#[tauri::command(rename_all = "snake_case")]
async fn open_url(url: String, app: AppHandle) -> CmdResult {
    if !util::is_http_url(&url) {
        return Err(CmdError::new(Code::Io, "Only web links (http and https) can be opened."));
    }
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| CmdError::new(Code::Io, format!("The link could not be opened: {e}")))
}

#[tauri::command(rename_all = "snake_case")]
async fn clear_cache(engine: State<'_, Engine>) -> CmdResult {
    engine.clear_cache();
    Ok(())
}

#[tauri::command(rename_all = "snake_case")]
async fn minimize(window: WebviewWindow) -> CmdResult {
    window.minimize().map_err(|e| CmdError::new(Code::Io, e.to_string()))
}

#[tauri::command(rename_all = "snake_case")]
async fn close(window: WebviewWindow) -> CmdResult {
    window.close().map_err(|e| CmdError::new(Code::Io, e.to_string()))
}

// ---- start ----

/// The window's size and position (logical pixels): the designed 1180x700, or smaller at the same aspect
/// ratio when the monitor's work area is smaller (e.g. 1080p at 150 %; the page scales itself), centred
/// on the work area. `None` for the position when the monitor is unknown (then the window is centred).
fn window_geometry(monitor: Option<Monitor>) -> (f64, f64, Option<(f64, f64)>) {
    let Some(m) = monitor else { return (WIDTH, HEIGHT, None) };
    let scale = m.scale_factor().max(0.5);
    let area = m.work_area();
    let (aw, ah) = (area.size.width as f64 / scale, area.size.height as f64 / scale);
    let k = (aw * 0.96 / WIDTH).min(ah * 0.96 / HEIGHT).min(1.0);
    let (w, h) = ((WIDTH * k).floor(), (HEIGHT * k).floor());
    let x = area.position.x as f64 / scale + (aw - w) / 2.0;
    let y = area.position.y as f64 / scale + (ah - h) / 2.0;
    (w, h, Some((x.max(0.0).round(), y.max(0.0).round())))
}

/// Creates the window from its `tauri.conf.json` entry (which has `"create": false`) at the size and
/// place [`window_geometry`] gives, so it never has to be resized or moved after it appears.
fn create_window(app: &tauri::App) -> Result<WebviewWindow, Box<dyn std::error::Error>> {
    let conf = app
        .config()
        .app
        .windows
        .iter()
        .find(|w| w.label == "main")
        .cloned()
        .ok_or("tauri.conf.json has no \"main\" window")?;
    let (w, h, pos) = window_geometry(app.primary_monitor().ok().flatten());
    let builder = WebviewWindowBuilder::from_config(app, &conf)?.inner_size(w, h);
    let builder = match pos {
        Some((x, y)) => builder.position(x, y),
        None => builder.center(),
    };
    let window = builder.build()?;
    let _ = window.set_focus();
    Ok(window)
}

fn launcher_config() -> LauncherConfig {
    LauncherConfig::parse(LAUNCHER_JSON).unwrap_or_else(|e| {
        // A broken launcher.json is a build mistake: start anyway and say so (no key = error phase).
        log::error!("{e}");
        LauncherConfig {
            base_url: "http://127.0.0.1/".into(),
            public_key: String::new(),
            realmlist: "127.0.0.1".into(),
        }
    })
}

fn main() {
    // A freshly updated launcher first waits for the old one to exit (it holds the single-instance lock).
    let (after_update, args) = selfupdate::parse_args(std::env::args_os().skip(1));
    if let Some(pid) = after_update {
        sys::wait_for_pid(pid, Duration::from_secs(15));
    }
    let config_dir = sys::config_dir();
    logger::init(&config_dir);

    let mut cfg = EngineConfig::new(env!("CARGO_PKG_VERSION"), launcher_config(), config_dir);
    cfg.current_exe = std::env::current_exe().ok();
    cfg.args = args;

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(move |app| {
            create_window(app)?;
            let sink = Arc::new(WindowSink { app: app.handle().clone() });
            app.manage(Engine::new(cfg, sink));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_state,
            choose_folder,
            folder_info,
            install,
            check,
            update,
            pause,
            resume,
            cancel,
            repair,
            play,
            save_settings,
            open_folder,
            open_url,
            clear_cache,
            minimize,
            close,
        ])
        .build(tauri::generate_context!());
    let app = match app {
        Ok(a) => a,
        Err(e) => {
            log::error!("the window could not be created: {e}");
            std::process::exit(1);
        }
    };
    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            // Stop a running download so the state is saved and the .part files stay resumable.
            if let Some(engine) = handle.try_state::<Engine>() {
                engine.shutdown(Duration::from_secs(3));
            }
        }
    });
}
