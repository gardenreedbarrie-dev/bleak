//! The launcher's error type. Every error carries one of the codes the window knows (DESIGN.md, event
//! `error`), plus `cancelled` for a stop the player asked for, which is never shown as an error.

use std::fmt;
use std::io;

use serde::Serialize;

/// What went wrong, as the window sees it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Code {
    Network,
    Signature,
    Manifest,
    DiskFull,
    GameRunning,
    Hash,
    Io,
    Launch,
    /// The player paused or stopped; not an error to report.
    Cancelled,
}

impl Code {
    pub fn as_str(self) -> &'static str {
        match self {
            Code::Network => "network",
            Code::Signature => "signature",
            Code::Manifest => "manifest",
            Code::DiskFull => "disk_full",
            Code::GameRunning => "game_running",
            Code::Hash => "hash",
            Code::Io => "io",
            Code::Launch => "launch",
            Code::Cancelled => "cancelled",
        }
    }
}

impl fmt::Display for Code {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// An error with its code and a message a player can read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Error {
    pub code: Code,
    pub message: String,
}

pub type Result<T> = std::result::Result<T, Error>;

impl Error {
    pub fn new(code: Code, message: impl Into<String>) -> Self {
        Error { code, message: message.into() }
    }

    pub fn network(message: impl Into<String>) -> Self {
        Self::new(Code::Network, message)
    }

    pub fn signature(message: impl Into<String>) -> Self {
        Self::new(Code::Signature, message)
    }

    pub fn manifest(message: impl Into<String>) -> Self {
        Self::new(Code::Manifest, message)
    }

    pub fn hash(message: impl Into<String>) -> Self {
        Self::new(Code::Hash, message)
    }

    pub fn io_msg(message: impl Into<String>) -> Self {
        Self::new(Code::Io, message)
    }

    pub fn launch(message: impl Into<String>) -> Self {
        Self::new(Code::Launch, message)
    }

    pub fn game_running(message: impl Into<String>) -> Self {
        Self::new(Code::GameRunning, message)
    }

    pub fn cancelled() -> Self {
        Self::new(Code::Cancelled, "Stopped.")
    }

    pub fn is_cancelled(&self) -> bool {
        self.code == Code::Cancelled
    }

    /// An I/O error while doing `what`, classified: a full disk is `disk_full`, a file another program
    /// holds open (the game) is `game_running`, anything else is `io`.
    pub fn io(what: impl fmt::Display, err: &io::Error) -> Self {
        if crate::sys::is_disk_full(err) {
            Self::new(Code::DiskFull, format!("The disk is full ({what}). Free some space and try again."))
        } else if crate::sys::is_in_use(err) {
            Self::new(Code::GameRunning, format!("{what}: the file is in use. Close the game and try again."))
        } else {
            Self::new(Code::Io, format!("{what}: {err}"))
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for Error {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_serialize_like_the_contract() {
        let all = [
            (Code::Network, "network"),
            (Code::Signature, "signature"),
            (Code::Manifest, "manifest"),
            (Code::DiskFull, "disk_full"),
            (Code::GameRunning, "game_running"),
            (Code::Hash, "hash"),
            (Code::Io, "io"),
            (Code::Launch, "launch"),
        ];
        for (code, name) in all {
            assert_eq!(code.as_str(), name);
            assert_eq!(serde_json::to_string(&code).unwrap(), format!("\"{name}\""));
        }
    }

    #[test]
    fn io_errors_are_classified() {
        let other = io::Error::new(io::ErrorKind::PermissionDenied, "denied");
        assert_eq!(Error::io("writing x", &other).code, Code::Io);
        #[cfg(unix)]
        {
            let full = io::Error::from_raw_os_error(libc::ENOSPC);
            assert_eq!(Error::io("writing x", &full).code, Code::DiskFull);
            let busy = io::Error::from_raw_os_error(libc::ETXTBSY);
            assert_eq!(Error::io("writing x", &busy).code, Code::GameRunning);
        }
    }
}
