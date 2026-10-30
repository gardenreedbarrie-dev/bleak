//! Small helpers shared by the modules.

use std::fs::{self, File, Metadata};
use std::io::Write;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

/// True for `http://…` and `https://…` with a host, and nothing else (no `file:`, `javascript:`, …).
pub fn is_http_url(url: &str) -> bool {
    let rest = if let Some(r) = strip_prefix_ignore_case(url, "https://") {
        r
    } else if let Some(r) = strip_prefix_ignore_case(url, "http://") {
        r
    } else {
        return false;
    };
    let host = rest.split(['/', '?', '#']).next().unwrap_or("");
    !host.is_empty()
        && !host.contains('@')
        && url.len() <= 2048
        && !url.chars().any(|c| c.is_control() || c.is_whitespace())
}

fn strip_prefix_ignore_case<'a>(s: &'a str, prefix: &str) -> Option<&'a str> {
    if s.len() >= prefix.len() && s.is_char_boundary(prefix.len()) && s[..prefix.len()].eq_ignore_ascii_case(prefix) {
        Some(&s[prefix.len()..])
    } else {
        None
    }
}

/// Writes `bytes` to `path` through `<path>.tmp` and a rename, so a crash leaves the old or the new
/// file, never half of one.
pub fn write_atomic(path: &Path, bytes: &[u8]) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(".tmp");
    let tmp = std::path::PathBuf::from(tmp);
    {
        let mut f = File::create(&tmp)?;
        f.write_all(bytes)?;
        f.sync_all()?;
    }
    fs::rename(&tmp, path)
}

/// Modification time in nanoseconds since 1970 (0 when the platform cannot tell).
pub fn mtime_ns(meta: &Metadata) -> u64 {
    meta.modified()
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_nanos().min(u64::MAX as u128) as u64)
        .unwrap_or(0)
}

/// `YYYY-MM-DD HH:MM:SS` in UTC.
pub fn utc_timestamp(t: SystemTime) -> String {
    let secs = t.duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    let (y, m, d) = civil_from_days(days);
    format!("{y:04}-{m:02}-{d:02} {:02}:{:02}:{:02}", rem / 3600, (rem / 60) % 60, rem % 60)
}

/// Days since 1970-01-01 to a proleptic Gregorian date (Howard Hinnant's algorithm).
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

/// `1.5 GB`, for messages.
pub fn human_bytes(n: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];
    let mut v = n as f64;
    let mut i = 0;
    while v >= 1000.0 && i < UNITS.len() - 1 {
        v /= 1000.0;
        i += 1;
    }
    if i == 0 {
        format!("{n} B")
    } else {
        format!("{v:.1} {}", UNITS[i])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn http_urls_only() {
        for ok in ["http://185.217.124.41:8090/", "https://discord.gg/x", "HTTPS://Example.org/a?b#c"] {
            assert!(is_http_url(ok), "{ok}");
        }
        for bad in [
            "file:///C:/Windows",
            "javascript:alert(1)",
            "http://",
            "https:///x",
            "ftp://x",
            "C:\\Games",
            "http://a b",
            "http://user@host/",
            "mailto:x@y",
            "",
        ] {
            assert!(!is_http_url(bad), "{bad}");
        }
    }

    #[test]
    fn timestamps_and_sizes() {
        assert_eq!(utc_timestamp(UNIX_EPOCH), "1970-01-01 00:00:00");
        assert_eq!(utc_timestamp(UNIX_EPOCH + Duration::from_secs(1_792_713_600 + 3661)), "2026-10-23 01:01:01");
        assert_eq!(utc_timestamp(UNIX_EPOCH + Duration::from_secs(951_782_400)), "2000-02-29 00:00:00");
        assert_eq!(human_bytes(512), "512 B");
        assert_eq!(human_bytes(1_500_000_000), "1.5 GB");
    }

    #[test]
    fn atomic_write_replaces() {
        let dir = std::env::temp_dir().join(format!("bh-util-{}", std::process::id()));
        let p = dir.join("sub/f.json");
        write_atomic(&p, b"one").unwrap();
        write_atomic(&p, b"two").unwrap();
        assert_eq!(fs::read(&p).unwrap(), b"two");
        assert!(!dir.join("sub/f.json.tmp").exists());
        fs::remove_dir_all(&dir).unwrap();
    }
}
