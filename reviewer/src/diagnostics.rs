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
        "password",
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
            if key == "authorization" && text[start..].to_ascii_lowercase().starts_with("bearer ") {
                start += "bearer ".len();
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
    }
}
