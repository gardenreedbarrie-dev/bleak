//! `launcher.log` in the config folder, rotated at 1 MB (the old log is kept as `launcher.log.1`).
//! Plugs into the `log` facade: the launcher's own messages from `info` up, other crates' from `warn`.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::SystemTime;

use crate::util::utc_timestamp;

pub const LOG_FILE: &str = "launcher.log";
pub const MAX_LOG_BYTES: u64 = 1 << 20;

/// An append-only log file that rotates itself.
pub struct LogFile {
    path: PathBuf,
    max: u64,
    file: Option<File>,
    size: u64,
}

impl LogFile {
    pub fn open(path: PathBuf, max: u64) -> LogFile {
        let mut l = LogFile { path, max, file: None, size: 0 };
        l.reopen();
        l
    }

    fn reopen(&mut self) {
        if let Some(dir) = self.path.parent() {
            let _ = fs::create_dir_all(dir);
        }
        self.file = OpenOptions::new().create(true).append(true).open(&self.path).ok();
        self.size = fs::metadata(&self.path).map(|m| m.len()).unwrap_or(0);
        if self.size >= self.max {
            self.rotate();
        }
    }

    fn rotate(&mut self) {
        self.file = None;
        let mut old = self.path.clone().into_os_string();
        old.push(".1");
        let _ = fs::remove_file(&old);
        let _ = fs::rename(&self.path, &old);
        self.file = OpenOptions::new().create(true).append(true).open(&self.path).ok();
        self.size = 0;
    }

    pub fn write_line(&mut self, line: &str) {
        let n = line.len() as u64 + 1;
        if self.size > 0 && self.size + n > self.max {
            self.rotate();
        }
        if let Some(f) = self.file.as_mut() {
            if writeln!(f, "{line}").is_ok() {
                self.size += n;
            }
        }
    }
}

struct Logger {
    file: Mutex<LogFile>,
}

impl log::Log for Logger {
    fn enabled(&self, meta: &log::Metadata) -> bool {
        let ours = meta.target().starts_with("bleakhold");
        meta.level() <= if ours { log::Level::Info } else { log::Level::Warn }
    }

    fn log(&self, record: &log::Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let line = format!("{} {:<5} {}", utc_timestamp(SystemTime::now()), record.level(), record.args());
        if let Ok(mut f) = self.file.lock() {
            f.write_line(&line);
        }
        if cfg!(debug_assertions) {
            eprintln!("{line}");
        }
    }

    fn flush(&self) {}
}

/// Installs the file logger for `<config_dir>/launcher.log`. A second call does nothing.
pub fn init(config_dir: &Path) {
    let logger = Logger { file: Mutex::new(LogFile::open(config_dir.join(LOG_FILE), MAX_LOG_BYTES)) };
    if log::set_boxed_logger(Box::new(logger)).is_ok() {
        log::set_max_level(log::LevelFilter::Info);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rotates_at_the_limit() {
        let dir = std::env::temp_dir().join(format!("bh-log-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        let path = dir.join(LOG_FILE);
        let mut l = LogFile::open(path.clone(), 100);
        for i in 0..10 {
            l.write_line(&format!("line {i:02} 0123456789"));
        }
        let cur = fs::read_to_string(&path).unwrap();
        let old = fs::read_to_string(dir.join("launcher.log.1")).unwrap();
        assert!(cur.len() <= 100 && old.len() <= 100, "{} {}", cur.len(), old.len());
        assert!(cur.ends_with("line 09 0123456789\n"));
        assert!(old.contains("line 0"));
        drop(l);
        // An oversized log is rotated when opened.
        fs::write(&path, vec![b'x'; 150]).unwrap();
        let _l = LogFile::open(path.clone(), 100);
        assert_eq!(fs::metadata(&path).unwrap().len(), 0);
        assert_eq!(fs::metadata(dir.join("launcher.log.1")).unwrap().len(), 150);
        fs::remove_dir_all(&dir).unwrap();
    }
}
