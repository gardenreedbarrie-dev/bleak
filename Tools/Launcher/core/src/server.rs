//! Realm status: a TCP connect (with timeout) to the auth and world ports; ping is the connect time.

use std::net::{TcpStream, ToSocketAddrs};
use std::time::{Duration, Instant};

use serde::Serialize;

/// The `server` event.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct ServerStatus {
    /// Both ports answer: the realm is playable.
    pub online: bool,
    pub auth: bool,
    pub world: bool,
    /// Connect time to the auth port (or the world port when auth is down), `null` when neither answers.
    pub ping_ms: Option<u64>,
}

/// Where to probe.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ServerTarget {
    pub name: String,
    pub host: String,
    pub auth_port: u16,
    pub world_port: u16,
}

/// Connect time to `host:port`, `None` when it does not answer within `timeout`.
pub fn connect_time(host: &str, port: u16, timeout: Duration) -> Option<Duration> {
    let addrs: Vec<_> = (host, port).to_socket_addrs().ok()?.collect();
    for addr in addrs {
        let t = Instant::now();
        if TcpStream::connect_timeout(&addr, timeout).is_ok() {
            return Some(t.elapsed());
        }
    }
    None
}

pub fn probe(target: &ServerTarget, timeout: Duration) -> ServerStatus {
    let auth = connect_time(&target.host, target.auth_port, timeout);
    let world = connect_time(&target.host, target.world_port, timeout);
    ServerStatus {
        online: auth.is_some() && world.is_some(),
        auth: auth.is_some(),
        world: world.is_some(),
        ping_ms: auth.or(world).map(|d| (d.as_millis() as u64).max(1)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn probes_open_and_closed_ports() {
        let open = TcpListener::bind("127.0.0.1:0").unwrap();
        let closed = TcpListener::bind("127.0.0.1:0").unwrap();
        let closed_port = closed.local_addr().unwrap().port();
        drop(closed);
        let t = ServerTarget {
            name: "x".into(),
            host: "127.0.0.1".into(),
            auth_port: open.local_addr().unwrap().port(),
            world_port: closed_port,
        };
        let s = probe(&t, Duration::from_millis(500));
        assert!(s.auth && !s.world && !s.online);
        assert!(s.ping_ms.unwrap() >= 1);
        let both = ServerTarget { world_port: t.auth_port, ..t.clone() };
        assert!(probe(&both, Duration::from_millis(500)).online);
        let none = ServerTarget { auth_port: closed_port, world_port: closed_port, ..t };
        assert_eq!(probe(&none, Duration::from_millis(500)), ServerStatus::default());
    }
}
