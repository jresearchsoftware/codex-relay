//! Process-local acceptance boundary; durable native-effect recovery stays in Store.
//! Only kernel-authenticated root peers can change this state. No public MCP tool.
use serde_json::{json, Value};
use std::{
    io,
    sync::{Arc, Mutex},
};

#[derive(Default)]
struct State {
    paused: bool,
    writer_paused: bool,
    draining: bool,
    ready: bool,
    requests: usize,
    mutations: usize,
    writer: usize,
}

#[derive(Clone, Default)]
pub struct Maintenance(Arc<Mutex<State>>);

pub struct Guard {
    maintenance: Maintenance,
    mutation: bool,
    writer: bool,
}

impl Drop for Guard {
    fn drop(&mut self) {
        let mut state = self.maintenance.0.lock().expect("maintenance state");
        if self.mutation {
            state.mutations -= 1;
            state.writer -= usize::from(self.writer);
        } else {
            state.requests -= 1;
        }
    }
}

impl Maintenance {
    pub fn from_environment() -> io::Result<Self> {
        let state = Self::default();
        if let Ok(path) = std::env::var("REVIEWER_MAINTENANCE_FILE") {
            match std::fs::symlink_metadata(&path) {
                Ok(meta) => {
                    #[cfg(unix)]
                    {
                        use std::os::unix::fs::{MetadataExt, PermissionsExt};
                        if !meta.is_file()
                            || meta.uid() != 0
                            || meta.nlink() != 1
                            || meta.permissions().mode() & 0o777 != 0o640
                        {
                            return Err(io::Error::new(
                                io::ErrorKind::PermissionDenied,
                                "maintenance record unsafe",
                            ));
                        }
                    }
                    match std::fs::read(path) {
                        Ok(bytes) => state.load_record(&bytes)?,
                        // An acknowledged resume can remove the record while
                        // this replacement is starting.
                        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
                        Err(error) => return Err(error),
                    }
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => (),
                Err(error) => return Err(error),
            }
        }
        Ok(state)
    }

    fn load_record(&self, bytes: &[u8]) -> io::Result<()> {
        let record: Value = serde_json::from_slice::<crate::strict_json::StrictJson>(bytes)?.0;
        let valid_operation = record["operation"].as_str().is_some_and(|value| {
            value.len() == 36
                && value.bytes().enumerate().all(|(index, byte)| {
                    if matches!(index, 8 | 13 | 18 | 23) {
                        byte == b'-'
                    } else {
                        byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
                    }
                })
        });
        if record["schemaVersion"] != 1
            || !valid_operation
            || record.as_object().is_none_or(|object| object.len() != 3)
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "maintenance record invalid",
            ));
        }
        let command = record["command"]
            .as_str()
            .filter(|value| matches!(*value, "pause" | "pause-writer" | "resume"))
            .ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidData, "maintenance command invalid")
            })?;
        self.command(command)?;
        Ok(())
    }

    pub fn ready(&self) {
        self.0.lock().expect("maintenance state").ready = true;
    }

    pub fn draining(&self) {
        let mut state = self.0.lock().expect("maintenance state");
        state.draining = true;
        state.ready = false;
    }

    pub fn request(&self) -> Option<Guard> {
        let mut state = self.0.lock().expect("maintenance state");
        // Axum owns connection acceptance during graceful shutdown. A request
        // it already dispatched can reach this middleware after SIGTERM.
        if state.paused {
            return None;
        }
        state.requests += 1;
        Some(Guard {
            maintenance: self.clone(),
            mutation: false,
            writer: false,
        })
    }

    pub fn mutation(&self, writer: bool) -> Option<Guard> {
        let mut state = self.0.lock().expect("maintenance state");
        // A request accepted before graceful shutdown retains ownership. Full
        // pause is checked at request admission; Writer pause is a separate
        // dependency barrier checked immediately before any helper can start.
        if writer && state.writer_paused {
            return None;
        }
        state.mutations += 1;
        state.writer += usize::from(writer);
        Some(Guard {
            maintenance: self.clone(),
            mutation: true,
            writer,
        })
    }

    pub fn command(&self, command: &str) -> io::Result<Value> {
        let mut state = self.0.lock().expect("maintenance state");
        match command {
            "status" => (),
            "pause" => state.paused = true,
            "pause-writer" => state.writer_paused = true,
            "resume" if !state.draining => {
                state.paused = false;
                state.writer_paused = false;
            }
            _ => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "maintenance command invalid",
                ))
            }
        }
        Ok(json!({"schemaVersion":1,"pid":std::process::id(),
            "resumeMarkerSupported":true,
            "ready":state.ready,"accepting":!state.paused && !state.draining,
            "writerAccepting":!state.paused && !state.writer_paused && !state.draining,
            "paused":state.paused,"writerPaused":state.writer_paused,
            "draining":state.draining,"activeRequests":state.requests,
            "activeMutations":state.mutations,"activeWriter":state.writer}))
    }
}

pub fn unavailable() -> axum::response::Response {
    use axum::{http::StatusCode, response::IntoResponse};
    (
        StatusCode::SERVICE_UNAVAILABLE,
        [("Retry-After", "5")],
        "REVIEWER_MAINTENANCE\n",
    )
        .into_response()
}

pub async fn track(
    axum::extract::State(maintenance): axum::extract::State<Maintenance>,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    let Some(_accepted) = maintenance.request() else {
        return unavailable();
    };
    next.run(request).await
}

#[cfg(unix)]
pub async fn serve(path: &str, maintenance: Maintenance, artifact: Value) -> io::Result<()> {
    use std::{
        fs,
        os::unix::fs::{FileTypeExt, PermissionsExt},
        time::Duration,
    };
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::UnixListener,
    };
    match fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_socket() => fs::remove_file(path)?,
        Ok(_) => {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "maintenance socket occupied",
            ))
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(error) => return Err(error),
    }
    let listener = UnixListener::bind(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    loop {
        let (mut stream, _) = listener.accept().await?;
        if stream.peer_cred()?.uid() != 0 {
            continue;
        }
        let maintenance = maintenance.clone();
        let artifact = artifact.clone();
        tokio::spawn(async move {
            let result = tokio::time::timeout(Duration::from_secs(2), async {
                let mut command = Vec::new();
                loop {
                    let byte = stream.read_u8().await?;
                    if byte == b'\n' {
                        break;
                    }
                    if command.len() >= 32 {
                        return Err(io::Error::new(
                            io::ErrorKind::InvalidInput,
                            "maintenance command too long",
                        ));
                    }
                    command.push(byte);
                }
                let mut status =
                    maintenance.command(std::str::from_utf8(&command).map_err(|_| {
                        io::Error::new(io::ErrorKind::InvalidInput, "maintenance command encoding")
                    })?)?;
                status["artifact"] = artifact;
                stream.write_all(&serde_json::to_vec(&status)?).await?;
                stream.shutdown().await
            })
            .await;
            if !matches!(result, Ok(Ok(()))) {
                tracing::warn!(event = "maintenance_control_failed");
            }
        });
    }
}

pub async fn shutdown(maintenance: Maintenance) {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};
        let mut terminate = signal(SignalKind::terminate()).expect("termination signal");
        tokio::select! {
            _ = terminate.recv() => (),
            _ = tokio::signal::ctrl_c() => (),
        }
    }
    #[cfg(not(unix))]
    tokio::signal::ctrl_c().await.expect("interrupt signal");
    maintenance.draining();
    tracing::info!(event = "reviewer_draining");
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pause_and_writer_barrier_preserve_already_accepted_work() {
        let state = Maintenance::default();
        state.ready();
        let request = state.request().unwrap();
        let writer = state.mutation(true).unwrap();
        let status = state.command("pause-writer").unwrap();
        assert_eq!(status["activeWriter"], 1);
        assert!(state.mutation(true).is_none());
        assert!(state.request().is_some());
        assert!(state.mutation(false).is_some());
        state.command("pause").unwrap();
        assert!(state.request().is_none());
        drop(writer);
        drop(request);
        assert_eq!(state.command("status").unwrap()["activeRequests"], 0);
        assert_eq!(state.command("status").unwrap()["activeWriter"], 0);
        state.command("resume").unwrap();
        assert!(state.request().is_some());
        state.draining();
        let status = state.command("status").unwrap();
        assert_eq!(status["accepting"], false);
        assert_eq!(status["ready"], false);
        assert!(state.request().is_some());
        assert!(state.command("resume").is_err());
        assert!(
            state.mutation(false).is_some(),
            "accepted request keeps publication ownership"
        );
    }

    #[test]
    fn replacement_loads_exact_durable_pause_and_refuses_malformed_records() {
        let state = Maintenance::default();
        state.load_record(br#"{"schemaVersion":1,"operation":"12345678-1234-1234-1234-123456789abc","command":"pause-writer"}"#).unwrap();
        assert!(state.request().is_some());
        assert!(state.mutation(true).is_none());
        for bytes in [
            br#"{"schemaVersion":1,"operation":"bad","command":"pause-writer"}"#.as_slice(),
            br#"{"schemaVersion":1,"operation":"12345678-1234-1234-1234-123456789abc","command":"invalid"}"#.as_slice(),
            br#"{"schemaVersion":1,"schemaVersion":1,"operation":"12345678-1234-1234-1234-123456789abc","command":"pause"}"#.as_slice(),
        ] { assert!(state.load_record(bytes).is_err()); }
    }

    #[test]
    fn replacement_loads_durable_resume_without_pausing_intake() {
        let state = Maintenance::default();
        state
            .load_record(br#"{"schemaVersion":1,"operation":"12345678-1234-1234-1234-123456789abc","command":"resume"}"#)
            .unwrap();
        state.ready();
        let status = state.command("status").unwrap();
        assert_eq!(status["resumeMarkerSupported"], true);
        assert_eq!(status["accepting"], true);
        assert_eq!(status["writerAccepting"], true);
        assert!(state.request().is_some());
        assert!(state.mutation(true).is_some());
    }

    #[tokio::test]
    async fn retained_listener_serves_pending_request_after_old_accepted_call_completes() {
        use axum::{routing::post, Router};
        use tokio::{
            sync::{oneshot, Notify},
            time::{timeout, Duration},
        };
        let retained = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        retained.set_nonblocking(true).unwrap();
        let address = retained.local_addr().unwrap();
        let started = Arc::new(Notify::new());
        let release = Arc::new(Notify::new());
        let handler = {
            let started = started.clone();
            let release = release.clone();
            move || async move {
                started.notify_one();
                release.notified().await;
                "old-completed"
            }
        };
        let (stop, stopped) = oneshot::channel::<()>();
        let old_listener =
            tokio::net::TcpListener::from_std(retained.try_clone().unwrap()).unwrap();
        let old = tokio::spawn(async move {
            axum::serve(old_listener, Router::new().route("/mcp", post(handler)))
                .with_graceful_shutdown(async {
                    let _ = stopped.await;
                })
                .await
                .unwrap();
        });
        let old_call = tokio::spawn(async move {
            reqwest::Client::new()
                .post(format!("http://{address}/mcp"))
                .send()
                .await
                .unwrap()
                .text()
                .await
                .unwrap()
        });
        timeout(Duration::from_secs(2), started.notified())
            .await
            .unwrap();
        stop.send(()).unwrap();
        // Wait until axum has consumed shutdown and closed its accept loop.
        tokio::time::sleep(Duration::from_millis(50)).await;
        let mut pending = tokio::spawn(async move {
            reqwest::Client::new()
                .post(format!("http://{address}/mcp"))
                .send()
                .await
                .unwrap()
                .text()
                .await
                .unwrap()
        });
        assert!(timeout(Duration::from_millis(50), &mut pending)
            .await
            .is_err());
        release.notify_one();
        assert_eq!(
            timeout(Duration::from_secs(2), old_call)
                .await
                .unwrap()
                .unwrap(),
            "old-completed"
        );
        timeout(Duration::from_secs(2), old).await.unwrap().unwrap();
        let next_listener = tokio::net::TcpListener::from_std(retained).unwrap();
        let next = tokio::spawn(async move {
            axum::serve(
                next_listener,
                Router::new().route("/mcp", post(|| async { "new-served" })),
            )
            .await
            .unwrap();
        });
        assert_eq!(
            timeout(Duration::from_secs(2), pending)
                .await
                .unwrap()
                .unwrap(),
            "new-served"
        );
        next.abort();
    }
}
