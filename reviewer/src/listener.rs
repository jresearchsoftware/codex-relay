//! Preserve the existing private TCP ingress across a managed service restart.
use std::{io, net::SocketAddr};

pub async fn bind(address: SocketAddr) -> io::Result<tokio::net::TcpListener> {
    let pid = std::env::var("LISTEN_PID").ok();
    let count = std::env::var("LISTEN_FDS").ok();
    match (pid.as_deref(), count.as_deref()) {
        (None, None) => tokio::net::TcpListener::bind(address).await,
        (Some(pid), Some("1")) if pid == std::process::id().to_string() => {
            #[cfg(unix)]
            {
                use std::os::fd::FromRawFd;
                // systemd supplies exactly fd 3, and transfers it to this PID.
                // Ownership is taken once; no other code touches this descriptor.
                let listener = unsafe { std::net::TcpListener::from_raw_fd(3) };
                if listener.local_addr()? != address {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "inherited listener does not match configured private bind",
                    ));
                }
                listener.set_nonblocking(true)?;
                tokio::net::TcpListener::from_std(listener)
            }
            #[cfg(not(unix))]
            Err(io::Error::new(
                io::ErrorKind::Unsupported,
                "inherited listener requires Unix",
            ))
        }
        _ => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid socket activation identity or descriptor count",
        )),
    }
}
