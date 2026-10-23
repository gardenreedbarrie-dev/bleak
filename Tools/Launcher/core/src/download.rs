//! The downloader (DESIGN.md "Update rules" 4): worker threads fetch objects in parallel into
//! `<path>.part`, resume a `.part` with an HTTP `Range` request, stream every byte through SHA-256, retry
//! three times, then rename the verified file over the target. A shared limiter caps the speed, a
//! [`Control`] stops everything (pause, cancel), and a progress callback gets bytes, speed, ETA and the
//! current file a few times a second.

use std::collections::VecDeque;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{mpsc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::error::{Error, Result};
use crate::http::{Body, Http};
use crate::paths;

/// Stop switch and live speed limit shared by the engine and the workers.
#[derive(Debug, Default)]
pub struct Control {
    stop: AtomicBool,
    limit_bps: AtomicU64,
}

impl Control {
    pub fn new() -> Control {
        Control::default()
    }

    /// Ask every running download and hash to stop (pause, cancel, shutdown).
    pub fn request_stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
    }

    /// Clear the stop request before starting new work.
    pub fn clear(&self) {
        self.stop.store(false, Ordering::SeqCst);
    }

    pub fn stopped(&self) -> bool {
        self.stop.load(Ordering::SeqCst)
    }

    /// Bytes per second over all workers, 0 = no limit. Takes effect immediately.
    pub fn set_limit_bps(&self, bps: u64) {
        self.limit_bps.store(bps, Ordering::SeqCst);
    }

    pub fn limit_bps(&self) -> u64 {
        self.limit_bps.load(Ordering::SeqCst)
    }
}

/// The `progress` event (DESIGN.md "Window ↔ backend").
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct Progress {
    pub done_bytes: u64,
    pub total_bytes: u64,
    pub speed_bps: u64,
    /// Seconds left, `null` while the speed is unknown.
    pub eta_s: Option<u64>,
    pub file: String,
    pub files_done: usize,
    pub files_total: usize,
}

/// Where a task's file goes.
#[derive(Clone, Debug)]
pub enum Dest {
    /// A manifest path inside the install folder: validated and checked again right before writing.
    Install { root: PathBuf, rel: String },
    /// A path the caller chose (the launcher's own update, next to the running exe).
    Path(PathBuf),
}

impl Dest {
    fn resolve(&self) -> Result<PathBuf> {
        match self {
            Dest::Install { root, rel } => paths::prepare_write(root, rel),
            Dest::Path(p) => Ok(p.clone()),
        }
    }
}

/// One object to fetch.
#[derive(Clone, Debug)]
pub struct Task {
    pub url: String,
    pub dest: Dest,
    pub size: u64,
    pub sha256: String,
    /// Shown as the current file.
    pub label: String,
}

#[derive(Clone, Debug)]
pub struct Options {
    pub parallel: usize,
    /// Tries per file before giving up.
    pub tries: u32,
    /// Wait after a failed try (doubles each time).
    pub backoff: Duration,
    /// How often progress is reported.
    pub progress_interval: Duration,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            parallel: 4,
            tries: 3,
            backoff: Duration::from_secs(1),
            progress_interval: Duration::from_millis(250),
        }
    }
}

const BUF: usize = 64 * 1024;

struct Ctx<'a> {
    http: &'a Http,
    tasks: &'a [Task],
    opts: &'a Options,
    ctl: &'a Control,
    abort: AtomicBool,
    next: AtomicUsize,
    done: AtomicU64,
    net: AtomicU64,
    current: Mutex<String>,
    limiter: Limiter,
}

impl Ctx<'_> {
    fn should_stop(&self) -> bool {
        self.ctl.stopped() || self.abort.load(Ordering::SeqCst)
    }
}

enum Msg {
    Done(usize, PathBuf),
    Failed(Error),
}

/// Downloads every task. `on_done(index, target)` runs on the calling thread after each file is in
/// place (the engine records it in the state); an error from it stops the run. Returns `Cancelled` when
/// the control was stopped before everything was done, or the first real error.
pub fn run(
    http: &Http,
    tasks: &[Task],
    opts: &Options,
    ctl: &Control,
    on_progress: &mut dyn FnMut(&Progress),
    on_done: &mut dyn FnMut(usize, &Path) -> Result<()>,
) -> Result<()> {
    let total: u64 = tasks.iter().map(|t| t.size).sum();
    let ctx = Ctx {
        http,
        tasks,
        opts,
        ctl,
        abort: AtomicBool::new(false),
        next: AtomicUsize::new(0),
        done: AtomicU64::new(0),
        net: AtomicU64::new(0),
        current: Mutex::new(String::new()),
        limiter: Limiter::default(),
    };
    let workers = opts.parallel.clamp(1, 8).min(tasks.len().max(1));
    let mut files_done = 0usize;
    let mut first_err: Option<Error> = None;
    let mut meter = SpeedMeter::new(Duration::from_secs(5));
    let mut report = |ctx: &Ctx, files_done: usize, meter: &mut SpeedMeter| {
        let done = ctx.done.load(Ordering::SeqCst).min(total);
        let speed = meter.sample(Instant::now(), ctx.net.load(Ordering::SeqCst));
        let p = Progress {
            done_bytes: done,
            total_bytes: total,
            speed_bps: speed,
            eta_s: (speed > 0).then(|| (total - done).div_ceil(speed)),
            file: ctx.current.lock().map(|s| s.clone()).unwrap_or_default(),
            files_done,
            files_total: tasks.len(),
        };
        on_progress(&p);
    };

    thread::scope(|s| {
        // the first report goes out before any worker runs, so it always reads where the download starts
        report(&ctx, 0, &mut meter);
        let (tx, rx) = mpsc::channel::<Msg>();
        for _ in 0..workers {
            let tx = tx.clone();
            let ctx = &ctx;
            s.spawn(move || worker(ctx, tx));
        }
        drop(tx);
        let mut last = Instant::now();
        loop {
            match rx.recv_timeout(opts.progress_interval) {
                Ok(Msg::Done(i, target)) => {
                    files_done += 1;
                    if let Err(e) = on_done(i, &target) {
                        ctx.abort.store(true, Ordering::SeqCst);
                        if first_err.as_ref().is_none_or(Error::is_cancelled) {
                            first_err = Some(e);
                        }
                    }
                }
                Ok(Msg::Failed(e)) => {
                    if first_err.as_ref().is_none_or(Error::is_cancelled) {
                        first_err = Some(e);
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {}
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
            if last.elapsed() >= opts.progress_interval {
                report(&ctx, files_done, &mut meter);
                last = Instant::now();
            }
        }
        report(&ctx, files_done, &mut meter);
    });

    if files_done == tasks.len() && first_err.as_ref().is_none_or(Error::is_cancelled) {
        return Ok(());
    }
    match first_err {
        Some(e) => Err(e),
        None => Err(Error::cancelled()),
    }
}

fn worker(ctx: &Ctx, tx: mpsc::Sender<Msg>) {
    loop {
        if ctx.should_stop() {
            return;
        }
        let i = ctx.next.fetch_add(1, Ordering::SeqCst);
        let Some(task) = ctx.tasks.get(i) else { return };
        if let Ok(mut c) = ctx.current.lock() {
            c.clone_from(&task.label);
        }
        let res = task.dest.resolve().and_then(|target| fetch_with_retries(ctx, task, &target).map(|_| target));
        match res {
            Ok(target) => {
                let _ = tx.send(Msg::Done(i, target));
            }
            Err(e) => {
                ctx.abort.store(true, Ordering::SeqCst);
                let _ = tx.send(Msg::Failed(e));
                return;
            }
        }
    }
}

enum Attempt {
    Cancelled,
    /// Retrying will not help.
    Fatal(Error),
    /// A network problem; the `.part` is kept and the next try resumes it.
    Net(Error),
    /// The data was wrong; the `.part` is gone.
    Mismatch,
    /// A resumed `.part` was stale (from an older version of the file); start over, once for free.
    Restart,
}

fn fetch_with_retries(ctx: &Ctx, task: &Task, target: &Path) -> Result<()> {
    let part = paths::part_path(target);
    let mut tries = 0u32;
    let mut free_restart = true;
    loop {
        if ctx.should_stop() {
            return Err(Error::cancelled());
        }
        let failure = match attempt(ctx, task, target, &part) {
            Ok(()) => return Ok(()),
            Err(Attempt::Cancelled) => return Err(Error::cancelled()),
            Err(Attempt::Fatal(e)) => return Err(e),
            Err(Attempt::Restart) if free_restart => {
                free_restart = false;
                log::info!("{}: partial download was stale, starting over", task.label);
                continue;
            }
            Err(Attempt::Restart) | Err(Attempt::Mismatch) => Error::hash(format!(
                "{} did not match its checksum after {} tries. The server's copy may be damaged; try again later.",
                task.label, ctx.opts.tries
            )),
            Err(Attempt::Net(e)) => e,
        };
        tries += 1;
        log::warn!("{}: try {tries} failed: {}", task.label, failure.message);
        if tries >= ctx.opts.tries {
            return Err(failure);
        }
        let wait = ctx.opts.backoff * 2u32.saturating_pow(tries - 1);
        let end = Instant::now() + wait;
        while Instant::now() < end {
            if ctx.should_stop() {
                return Err(Error::cancelled());
            }
            thread::sleep(Duration::from_millis(20).min(wait));
        }
    }
}

/// Bytes of the current file counted in the shared progress; taken back unless the file finished.
struct FileBytes<'a> {
    done: &'a AtomicU64,
    counted: u64,
    keep: bool,
}

impl FileBytes<'_> {
    fn add(&mut self, n: u64) {
        self.done.fetch_add(n, Ordering::SeqCst);
        self.counted += n;
    }

    fn reset(&mut self) {
        self.done.fetch_sub(self.counted, Ordering::SeqCst);
        self.counted = 0;
    }
}

impl Drop for FileBytes<'_> {
    fn drop(&mut self) {
        if !self.keep {
            self.reset();
        }
    }
}

fn io_fatal(what: String, e: &io::Error) -> Attempt {
    Attempt::Fatal(Error::io(what, e))
}

fn attempt(ctx: &Ctx, task: &Task, target: &Path, part: &Path) -> std::result::Result<(), Attempt> {
    let mut fb = FileBytes { done: &ctx.done, counted: 0, keep: false };
    let partname = part.display().to_string();

    // A link in place of the .part would be written through: never follow one.
    if fs::symlink_metadata(part).is_ok_and(|m| m.file_type().is_symlink()) {
        fs::remove_file(part).map_err(|e| io_fatal(format!("removing {partname}"), &e))?;
    }
    let mut existing = fs::metadata(part).map(|m| m.len()).unwrap_or(0);
    if existing > task.size {
        fs::remove_file(part).map_err(|e| io_fatal(format!("removing {partname}"), &e))?;
        existing = 0;
    }

    let mut hasher = Sha256::new();
    if existing > 0 && !hash_prefix(ctx, part, existing, &mut hasher, &mut fb)? {
        let _ = fs::remove_file(part);
        existing = 0;
        hasher = Sha256::new();
        fb.reset();
    }
    let resumed = existing > 0;

    if existing == task.size {
        if hex(&hasher.finalize()) != task.sha256 {
            let _ = fs::remove_file(part);
            return Err(if resumed { Attempt::Restart } else { Attempt::Mismatch });
        }
        if !part.exists() {
            File::create(part).map_err(|e| io_fatal(format!("creating {partname}"), &e))?;
        }
        finish(part, target)?;
        fb.keep = true;
        return Ok(());
    }

    let (mut reader, mut file) = match ctx.http.get_from(&task.url, existing) {
        Err(e) => return Err(Attempt::Net(e)),
        Ok(Body::RangeNotSatisfiable) => {
            let _ = fs::remove_file(part);
            return Err(Attempt::Restart);
        }
        Ok(Body::Partial(r)) => {
            let f =
                OpenOptions::new().append(true).open(part).map_err(|e| io_fatal(format!("opening {partname}"), &e))?;
            (r, f)
        }
        Ok(Body::Full(r)) => {
            if existing > 0 {
                existing = 0;
                hasher = Sha256::new();
                fb.reset();
            }
            let f = File::create(part).map_err(|e| io_fatal(format!("creating {partname}"), &e))?;
            (r, f)
        }
    };

    let mut written = existing;
    let mut buf = vec![0u8; BUF];
    loop {
        if ctx.should_stop() {
            let _ = file.flush();
            return Err(Attempt::Cancelled);
        }
        let n = match reader.read(&mut buf) {
            Ok(n) => n,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => {
                let _ = file.flush();
                return Err(Attempt::Net(Error::network(format!("{}: {e}", task.label))));
            }
        };
        if n == 0 {
            break;
        }
        if written + n as u64 > task.size {
            drop(file);
            let _ = fs::remove_file(part);
            return Err(if resumed { Attempt::Restart } else { Attempt::Mismatch });
        }
        file.write_all(&buf[..n]).map_err(|e| io_fatal(format!("writing {partname}"), &e))?;
        hasher.update(&buf[..n]);
        written += n as u64;
        fb.add(n as u64);
        ctx.net.fetch_add(n as u64, Ordering::SeqCst);
        ctx.limiter.consume(n as u64, ctx.ctl.limit_bps(), &|| ctx.should_stop());
    }
    if written < task.size {
        let _ = file.flush();
        return Err(Attempt::Net(Error::network(format!(
            "{}: the connection closed after {written} of {} bytes",
            task.label, task.size
        ))));
    }
    if hex(&hasher.finalize()) != task.sha256 {
        drop(file);
        let _ = fs::remove_file(part);
        return Err(if resumed { Attempt::Restart } else { Attempt::Mismatch });
    }
    file.sync_all().map_err(|e| io_fatal(format!("writing {partname}"), &e))?;
    drop(file);
    finish(part, target)?;
    fb.keep = true;
    Ok(())
}

/// Hashes the first `len` bytes of an existing `.part`. `Ok(false)` when it cannot be read.
fn hash_prefix(
    ctx: &Ctx,
    part: &Path,
    len: u64,
    hasher: &mut Sha256,
    fb: &mut FileBytes,
) -> std::result::Result<bool, Attempt> {
    let Ok(f) = File::open(part) else {
        return Ok(false);
    };
    let mut r = f.take(len);
    let mut buf = vec![0u8; 1 << 20];
    let mut got = 0u64;
    loop {
        if ctx.should_stop() {
            return Err(Attempt::Cancelled);
        }
        match r.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                hasher.update(&buf[..n]);
                got += n as u64;
                fb.add(n as u64);
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(_) => return Ok(false),
        }
    }
    Ok(got == len)
}

/// Moves the verified `.part` over the target (replacing it, also on Windows; a read-only target gets
/// its flag cleared first).
fn finish(part: &Path, target: &Path) -> std::result::Result<(), Attempt> {
    rename_over(part, target).map_err(|e| io_fatal(format!("replacing {}", target.display()), &e))
}

pub(crate) fn rename_over(from: &Path, to: &Path) -> io::Result<()> {
    match fs::rename(from, to) {
        Err(e) if e.kind() == io::ErrorKind::PermissionDenied => {
            if let Ok(meta) = fs::metadata(to) {
                let mut perm = meta.permissions();
                if perm.readonly() {
                    #[allow(clippy::permissions_set_readonly_false)]
                    perm.set_readonly(false);
                    fs::set_permissions(to, perm)?;
                    return fs::rename(from, to);
                }
            }
            Err(e)
        }
        other => other,
    }
}

/// Lower-case hex.
pub fn hex(bytes: &[u8]) -> String {
    const D: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push(D[(b >> 4) as usize] as char);
        s.push(D[(b & 15) as usize] as char);
    }
    s
}

/// SHA-256 of a whole file, calling `on_bytes` as it reads and stopping when `stop` says so.
pub fn hash_file(path: &Path, stop: &dyn Fn() -> bool, on_bytes: &mut dyn FnMut(u64)) -> Result<String> {
    let mut f = File::open(path).map_err(|e| Error::io(format!("reading {}", path.display()), &e))?;
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        if stop() {
            return Err(Error::cancelled());
        }
        match f.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                hasher.update(&buf[..n]);
                on_bytes(n as u64);
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(e) => return Err(Error::io(format!("reading {}", path.display()), &e)),
        }
    }
    Ok(hex(&hasher.finalize()))
}

/// SHA-256 of bytes in memory.
pub fn sha256_hex(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

/// Shared speed limit: each worker books the time its bytes take at the allowed rate and sleeps until
/// then. A quarter second of credit keeps it smooth.
#[derive(Default)]
struct Limiter {
    next: Mutex<Option<Instant>>,
}

impl Limiter {
    fn consume(&self, n: u64, rate: u64, stop: &dyn Fn() -> bool) {
        if rate == 0 {
            return;
        }
        let wait = {
            let Ok(mut g) = self.next.lock() else { return };
            let now = Instant::now();
            let floor = now.checked_sub(Duration::from_millis(250)).unwrap_or(now);
            let base = match *g {
                Some(t) if t > floor => t,
                _ => floor,
            };
            let t = base + Duration::from_secs_f64(n as f64 / rate as f64);
            *g = Some(t);
            t.saturating_duration_since(now)
        };
        let end = Instant::now() + wait;
        while !stop() {
            let left = end.saturating_duration_since(Instant::now());
            if left.is_zero() {
                break;
            }
            thread::sleep(left.min(Duration::from_millis(50)));
        }
    }
}

/// Speed over the last few seconds.
struct SpeedMeter {
    samples: VecDeque<(Instant, u64)>,
    window: Duration,
}

impl SpeedMeter {
    fn new(window: Duration) -> SpeedMeter {
        SpeedMeter { samples: VecDeque::new(), window }
    }

    fn sample(&mut self, now: Instant, bytes: u64) -> u64 {
        self.samples.push_back((now, bytes));
        while self.samples.len() > 2 && now.duration_since(self.samples[0].0) > self.window {
            self.samples.pop_front();
        }
        let (t0, b0) = self.samples[0];
        let dt = now.duration_since(t0).as_secs_f64();
        if dt < 0.2 {
            return 0;
        }
        ((bytes.saturating_sub(b0)) as f64 / dt) as u64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_and_hash() {
        assert_eq!(hex(&[0, 15, 255]), "000fff");
        assert_eq!(sha256_hex(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
        let p = std::env::temp_dir().join(format!("bh-hash-{}", std::process::id()));
        fs::write(&p, b"abc").unwrap();
        let mut seen = 0;
        assert_eq!(hash_file(&p, &|| false, &mut |n| seen += n).unwrap(), sha256_hex(b"abc"));
        assert_eq!(seen, 3);
        assert!(hash_file(&p, &|| true, &mut |_| {}).unwrap_err().is_cancelled());
        fs::remove_file(&p).unwrap();
    }

    #[test]
    fn limiter_holds_the_rate() {
        let l = Limiter::default();
        let t = Instant::now();
        for _ in 0..10 {
            l.consume(100_000, 2_000_000, &|| false);
        }
        // 1 MB at 2 MB/s with 0.25 s credit: about 0.25 s.
        let el = t.elapsed();
        assert!(el >= Duration::from_millis(200) && el < Duration::from_secs(2), "{el:?}");
        let t = Instant::now();
        l.consume(10_000_000, 1, &|| true);
        assert!(t.elapsed() < Duration::from_millis(100));
    }

    #[test]
    fn speed_meter() {
        let mut m = SpeedMeter::new(Duration::from_secs(5));
        let t = Instant::now();
        assert_eq!(m.sample(t, 0), 0);
        assert_eq!(m.sample(t + Duration::from_secs(1), 1000), 1000);
        assert_eq!(m.sample(t + Duration::from_secs(2), 3000), 1500);
        assert_eq!(m.sample(t + Duration::from_secs(10), 3000), 0);
    }

    #[test]
    fn rename_replaces_read_only_targets() {
        let dir = std::env::temp_dir().join(format!("bh-rename-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let (a, b) = (dir.join("a"), dir.join("b"));
        fs::write(&a, b"new").unwrap();
        fs::write(&b, b"old").unwrap();
        let mut perm = fs::metadata(&b).unwrap().permissions();
        perm.set_readonly(true);
        fs::set_permissions(&b, perm).unwrap();
        rename_over(&a, &b).unwrap();
        assert_eq!(fs::read(&b).unwrap(), b"new");
        fs::remove_dir_all(&dir).unwrap();
    }
}
