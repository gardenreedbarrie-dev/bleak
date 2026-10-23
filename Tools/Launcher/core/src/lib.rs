//! Bleakhold Launcher engine.
//!
//! Everything the launcher does that is not drawing a window lives here, so it can be tested on any
//! platform: the signed manifest ([`manifest`], [`signature`]), the path rules ([`paths`]), the plan of
//! what to download ([`planner`]), the downloader ([`download`]), the local state ([`state`],
//! [`settings`]), realmlist and `Config.wtf` ([`realmlist`]), the cache epoch ([`cache`]), the
//! launcher's own update ([`selfupdate`]) and the state machine that ties it together ([`engine`]).
//! `Tools/Launcher/DESIGN.md` is the contract all of it implements.

pub mod cache;
pub mod config;
pub mod download;
pub mod engine;
pub mod error;
pub mod folder;
pub mod http;
pub mod launch;
pub mod logger;
pub mod manifest;
pub mod paths;
pub mod planner;
pub mod realmlist;
pub mod selfupdate;
pub mod server;
pub mod settings;
pub mod shortcut;
pub mod signature;
pub mod state;
pub mod sys;
pub mod util;

pub use config::LauncherConfig;
pub use download::{Control, Progress};
pub use engine::{Engine, EngineConfig, Phase, Sink};
pub use error::{Code, Error, Result};
pub use folder::FolderInfo;
pub use manifest::Manifest;
pub use server::ServerStatus;
pub use settings::Settings;
pub use state::InstallState;
