//! The plan (DESIGN.md "Update rules" 3 and 5): which files to download and which tracked files to delete.
//!
//! A file needs downloading when it is missing, its size differs, or (size equal, but its size or
//! modification time differ from the state, or the state has no entry for it) its SHA-256 differs.
//! "Repair" hashes every file. `once` files are only checked for presence. A file found right by hash is
//! adopted into the state; one found wrong is dropped from it, so a later fast plan cannot trust it.

use std::collections::HashSet;
use std::fs;
use std::path::Path;
use std::time::Instant;

use crate::download::hash_file;
use crate::error::Result;
use crate::manifest::{FileEntry, Manifest};
use crate::paths;
use crate::state::{FileState, InstallState};
use crate::util::mtime_ns;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// Trust the state's size and modification time; hash only what changed.
    Fast,
    /// Hash every file.
    Repair,
}

/// One file to download.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Job {
    pub p: String,
    pub s: u64,
    pub h: String,
    pub once: bool,
}

impl From<&FileEntry> for Job {
    fn from(f: &FileEntry) -> Job {
        Job { p: f.p.clone(), s: f.s, h: f.h.clone(), once: f.once }
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Plan {
    pub downloads: Vec<Job>,
    /// Tracked files the manifest no longer lists.
    pub deletes: Vec<String>,
    /// Sum of all manifest sizes.
    pub total_bytes: u64,
    /// Sum of the sizes to download.
    pub download_bytes: u64,
}

impl Plan {
    pub fn is_empty(&self) -> bool {
        self.downloads.is_empty() && self.deletes.is_empty()
    }
}

/// Progress of the hashing part of planning.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct VerifyProgress {
    pub done_bytes: u64,
    pub total_bytes: u64,
    pub file: String,
    pub files_done: usize,
    pub files_total: usize,
}

/// What the planner decided about one hashed file: `Some` adopts it into the state, `None` forgets it.
pub type Verified<'a> = &'a mut dyn FnMut(&str, Option<FileState>);

/// Builds the plan for `manifest` in `install`. `on_progress` is called while files are hashed (not
/// throttled), `on_verified` for every hashed file. Stops with `Cancelled` when `stop` says so.
pub fn plan(
    manifest: &Manifest,
    install: &Path,
    state: &InstallState,
    mode: Mode,
    stop: &dyn Fn() -> bool,
    on_progress: &mut dyn FnMut(&VerifyProgress),
    on_verified: Verified,
) -> Result<Plan> {
    let mut plan = Plan { total_bytes: manifest.total_bytes(), ..Default::default() };
    let mut to_hash: Vec<&FileEntry> = Vec::new();

    for f in &manifest.files {
        let path = paths::safe_join(install, &f.p)?;
        let meta = match fs::metadata(&path) {
            Ok(m) if m.is_file() => m,
            _ => {
                plan.downloads.push(f.into());
                continue;
            }
        };
        if f.once {
            continue;
        }
        if meta.len() != f.s {
            plan.downloads.push(f.into());
            continue;
        }
        let trusted = mode == Mode::Fast
            && state.files.get(&f.p).is_some_and(|e| {
                e.h == f.h && e.s == f.s && e.size == meta.len() && e.mtime == mtime_ns(&meta) && !e.once
            });
        if !trusted {
            to_hash.push(f);
        }
    }

    if !to_hash.is_empty() {
        let mut vp = VerifyProgress {
            total_bytes: to_hash.iter().map(|f| f.s).sum(),
            files_total: to_hash.len(),
            ..Default::default()
        };
        let started = Instant::now();
        for f in to_hash {
            if stop() {
                return Err(crate::Error::cancelled());
            }
            let path = paths::safe_join(install, &f.p)?;
            vp.file.clone_from(&f.p);
            on_progress(&vp);
            let before = vp.done_bytes;
            let h = hash_file(&path, stop, &mut |n| {
                vp.done_bytes += n;
                on_progress(&vp);
            })?;
            vp.done_bytes = before + f.s;
            vp.files_done += 1;
            if h == f.h {
                let meta = fs::metadata(&path).map_err(|e| crate::Error::io(format!("reading {}", f.p), &e))?;
                on_verified(
                    &f.p,
                    Some(FileState {
                        p: f.p.clone(),
                        s: f.s,
                        h: f.h.clone(),
                        size: meta.len(),
                        mtime: mtime_ns(&meta),
                        once: false,
                    }),
                );
            } else {
                on_verified(&f.p, None);
                plan.downloads.push(f.into());
            }
        }
        on_progress(&vp);
        log::info!("verified {} files in {:.1} s", vp.files_total, started.elapsed().as_secs_f64());
    }

    plan.deletes = stale_files(manifest, state);
    plan.download_bytes = plan.downloads.iter().map(|j| j.s).sum();
    Ok(plan)
}

/// Tracked files the manifest no longer lists: never `once` files, and never a path the manifest still
/// lists under another case (on Windows that is the same file).
pub fn stale_files(manifest: &Manifest, state: &InstallState) -> Vec<String> {
    let listed: HashSet<String> = manifest.files.iter().map(|f| f.p.to_lowercase()).collect();
    state.files.values().filter(|e| !e.once && !listed.contains(&e.p.to_lowercase())).map(|e| e.p.clone()).collect()
}

/// Deletes tracked files the manifest dropped (and their `.part`), forgets them in the state, and
/// removes folders that became empty. Paths are validated again; failures are logged and skipped
/// (the file stays tracked and is tried again next time).
pub fn delete_stale(install: &Path, deletes: &[String], state: &mut InstallState) {
    for rel in deletes {
        let Ok(path) = paths::safe_join(install, rel) else {
            state.forget(rel);
            continue;
        };
        if let Some(parent) = path.parent() {
            if parent.exists() && paths::ensure_inside(install, parent).is_err() {
                log::warn!("not deleting {rel}: it leads outside the install folder");
                state.forget(rel);
                continue;
            }
        }
        let _ = fs::remove_file(paths::part_path(&path));
        match fs::remove_file(&path) {
            Ok(()) => {
                log::info!("deleted {rel}");
                state.forget(rel);
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => state.forget(rel),
            Err(e) => {
                log::warn!("could not delete {rel}: {e}");
                continue;
            }
        }
        let mut dir = path.parent();
        while let Some(d) = dir {
            if d == install || !d.starts_with(install) || fs::remove_dir(d).is_err() {
                break;
            }
            dir = d.parent();
        }
    }
}
