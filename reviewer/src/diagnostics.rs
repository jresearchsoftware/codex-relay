//! Bounded, redacted causes on the existing host service journal. These details
//! never become MCP output or publication authority.
use std::fmt::Debug;

const LIMIT: usize = 4096;

pub(crate) fn bounded(message: &str) -> (String, bool) {
    let mut text = message.to_owned();
    // Remove complete and partial credential tokens, including a token cut by
    // the bounded upstream response read. Do not inspect credential files.
    for prefix in [
        "github_pat_",
        "ghp_",
        "gho_",
        "ghu_",
        "ghs_",
        "ghr_",
        "sk-",
        "eyJ",
    ] {
        while let Some(start) = text.find(prefix) {
            let end = text[start..]
                .find(|ch: char| !(ch.is_ascii_alphanumeric() || "._-".contains(ch)))
                .map_or(text.len(), |length| start + length);
            text.replace_range(start..end, "[REDACTED]");
        }
    }
    while let Some(start) = text.find("-----BEGIN ") {
        if !text[start..].contains("PRIVATE KEY-----") {
            break;
        }
        let end = text[start..]
            .find("-----END ")
            .and_then(|offset| {
                text[start + offset + 9..]
                    .find("-----")
                    .map(|length| start + offset + 9 + length + 5)
            })
            .unwrap_or(text.len());
        text.replace_range(start..end, "[REDACTED PRIVATE KEY]");
    }
    // Native rejection messages and helper stderr can contain labelled secrets.
    for key in [
        "authorization",
        "bearer",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
        "api_key",
        "api-key",
        "apikey",
        "password",
        "passwd",
        "secret",
        "token",
    ] {
        let mut offset = 0;
        loop {
            let lowercase = text.to_ascii_lowercase();
            let Some(found) = lowercase[offset..].find(key) else {
                break;
            };
            let after = offset + found + key.len();
            let tail = &text[after..];
            let skipped = tail.len()
                - tail
                    .trim_start_matches(['"', '\'', ' ', ':', '=', '\t'])
                    .len();
            let mut start = after + skipped;
            if key == "authorization" {
                for scheme in ["bearer ", "basic "] {
                    if text[start..].to_ascii_lowercase().starts_with(scheme) {
                        start += scheme.len();
                        break;
                    }
                }
            }
            if skipped == 0 || start == text.len() {
                offset = after;
                continue;
            }
            let end = text[start..]
                .find(|ch: char| ch.is_whitespace() || ['"', '\'', ',', '}', ';'].contains(&ch))
                .map_or(text.len(), |length| start + length);
            if start < end && &text[start..end] != "[REDACTED]" {
                text.replace_range(start..end, "[REDACTED]");
                offset = start + "[REDACTED]".len();
            } else {
                offset = after;
            }
        }
    }
    let truncated = text.len() > LIMIT;
    if truncated {
        let mut end = LIMIT;
        while !text.is_char_boundary(end) {
            end -= 1;
        }
        text.truncate(end);
    }
    (text, truncated)
}

#[track_caller]
pub(crate) fn record(code: &str, phase: &str, cause: &str) {
    let source = std::panic::Location::caller();
    let (cause, truncated) = bounded(cause);
    tracing::error!(event = "relay_failure_cause", code, phase,
        source = %source, cause, cause_truncated = truncated);
}

#[track_caller]
pub(crate) fn failure(code: &'static str, cause: impl Debug) -> &'static str {
    record(code, "observed", &format!("{cause:?}"));
    code
}

#[cfg(test)]
pub(crate) fn capture() -> (
    impl tracing::Subscriber + Send + Sync,
    std::sync::Arc<std::sync::Mutex<Vec<u8>>>,
) {
    use std::{
        io,
        sync::{Arc, Mutex},
    };
    struct Writer(Arc<Mutex<Vec<u8>>>);
    impl io::Write for Writer {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes);
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    // Keep a disabled registrar alive before enabling the first capture. With
    // only one Dispatch, tracing-core's callsite registration consults the
    // emitting thread's default. An unscoped test can then cache `never` before
    // the captured future is first polled. Two live registrars force interest
    // calculation across subscribers instead, without a global default or
    // serializing tests. The anchor alone keeps the global max level OFF.
    static ANCHOR: std::sync::OnceLock<tracing::Dispatch> = std::sync::OnceLock::new();
    ANCHOR.get_or_init(|| {
        tracing::Dispatch::new(
            tracing_subscriber::fmt()
                .with_max_level(tracing::level_filters::LevelFilter::OFF)
                .with_writer(io::sink)
                .finish(),
        )
    });
    let bytes = Arc::new(Mutex::new(Vec::new()));
    let writer = bytes.clone();
    (
        tracing_subscriber::fmt()
            .without_time()
            .with_ansi(false)
            .with_writer(move || Writer(writer.clone()))
            .finish(),
        bytes,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capture_survives_first_unscoped_observation() {
        // A fresh process is essential: another capture in the test suite can
        // keep the callsite enabled and hide the first-subscriber interleaving.
        const CHILD: &str = "RELAY_DIAGNOSTIC_CAPTURE_CHILD";
        if std::env::var_os(CHILD).is_none() {
            let result = std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "diagnostics::tests::capture_survives_first_unscoped_observation",
                    "--nocapture",
                ])
                .env(CHILD, "1")
                .output()
                .unwrap();
            assert!(
                result.status.success(),
                "isolated capture failed: {}{}",
                String::from_utf8_lossy(&result.stdout),
                String::from_utf8_lossy(&result.stderr)
            );
            assert!(
                String::from_utf8_lossy(&result.stdout).contains("1 passed; 0 failed"),
                "isolated regression did not execute: {}",
                String::from_utf8_lossy(&result.stdout)
            );
            return;
        }

        let (subscriber, journal) = capture();
        let dispatch = tracing::Dispatch::new(subscriber);
        // A parallel test without a subscriber can be the first caller after
        // WithSubscriber creates its Dispatch but before its future is polled.
        record("UNSCOPED", "fixture", "outside capture");
        tracing::dispatcher::with_default(&dispatch, || {
            record("CAPTURED", "fixture", "native E422; secret=private-value");
        });
        let journal = String::from_utf8(journal.lock().unwrap().clone()).unwrap();
        assert!(
            journal.contains("native E422"),
            "missing original cause: {journal}"
        );
        assert!(journal.contains("CAPTURED"), "{journal}");
        assert!(!journal.contains("UNSCOPED"), "{journal}");
        assert!(!journal.contains("private-value"), "{journal}");
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn concurrent_captures_keep_their_own_causes_across_polls() {
        use tracing::instrument::WithSubscriber;
        let barrier = std::sync::Arc::new(tokio::sync::Barrier::new(8));
        let mut tasks = Vec::new();
        for index in 0..8 {
            let (subscriber, journal) = capture();
            let barrier = barrier.clone();
            let task = tokio::spawn(
                async move {
                    barrier.wait().await;
                    for _ in 0..32 {
                        tokio::task::yield_now().await;
                        record(
                            "CAPTURED",
                            "fixture",
                            &format!("request-{index}; token=private-value"),
                        );
                    }
                }
                .with_subscriber(subscriber),
            );
            tasks.push((index, task, journal));
        }
        for (index, task, journal) in tasks {
            task.await.unwrap();
            let journal = String::from_utf8(journal.lock().unwrap().clone()).unwrap();
            assert_eq!(
                journal.matches(&format!("request-{index}")).count(),
                32,
                "{journal}"
            );
            for other in (0..8).filter(|other| *other != index) {
                assert!(!journal.contains(&format!("request-{other}")), "{journal}");
            }
            assert!(!journal.contains("private-value"), "{journal}");
        }
    }

    #[test]
    fn preserves_native_cause_and_redacts_credentials_with_bounded_unicode() {
        let (cause, truncated) = bounded("EACCES (os error 13): rejected; Authorization: Bearer plain-secret; token=private-value github_pat_private sk-private eyJ.private.signature");
        assert!(cause.contains("EACCES (os error 13)"));
        for secret in [
            "plain-secret",
            "private-value",
            "github_pat_private",
            "sk-private",
            "eyJ.private.signature",
        ] {
            assert!(!cause.contains(secret), "{cause}");
        }
        assert!(!truncated);
        let (cause, truncated) = bounded(&"é".repeat(LIMIT));
        assert!(truncated);
        assert!(cause.len() <= LIMIT);
        assert_eq!(
            bounded("-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY----- rest").0,
            "[REDACTED PRIVATE KEY] rest"
        );
        let _ = bounded("token ,😄😄😄😄😄😄");
        let (cause, _) = bounded("Authorization: Basic fixture-basic-credential; api_key=private-api-key; passwd=private-password");
        for secret in [
            "fixture-basic-credential",
            "private-api-key",
            "private-password",
        ] {
            assert!(!cause.contains(secret), "{cause}");
        }
    }
}
