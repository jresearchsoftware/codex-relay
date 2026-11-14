//! Local root-only adoption evidence from this very running Reviewer.
//! This socket is not HTTP/MCP and grants no publication or network identity.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, io};

pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn config_digest(config: &Value) -> String {
    let mut effective = config.clone();
    // These validated fields describe the source package, not loaded behavior.
    effective
        .as_object_mut()
        .expect("config object")
        .remove("artifact");
    digest(&serde_json::to_vec(&effective).expect("config serialization"))
}

pub fn capture(config: &Value, ca: &[u8]) -> io::Result<Value> {
    let environment: BTreeMap<_, _> = std::env::vars().collect();
    capture_with_environment(config, ca, &environment)
}

fn capture_with_environment(
    config: &Value,
    ca: &[u8],
    environment: &BTreeMap<String, String>,
) -> io::Result<Value> {
    let file = |name: &str| -> io::Result<String> {
        Ok(digest(&fs::read(environment.get(name).ok_or_else(
            || io::Error::new(io::ErrorKind::NotFound, "adoption input missing"),
        )?)?))
    };
    let env_files = environment
        .get("REVIEWER_ADOPTION_ENV_FILES")
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::NotFound,
                "adoption environment files missing",
            )
        })?;
    let mut files = BTreeMap::new();
    for path in env_files.split(':') {
        if !path.starts_with('/') || files.contains_key(path) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "adoption input invalid",
            ));
        }
        files.insert(path.to_string(), digest(&fs::read(path)?));
    }
    Ok(json!({"schemaVersion":1,"pid":std::process::id(),
        "config":config_digest(config),
        "environment":digest(&serde_json::to_vec(&environment)?),
        "ca":digest(ca),"key":file("GITHUB_APP_PRIVATE_KEY_FILE")?,
        "unit":file("REVIEWER_ADOPTION_UNIT_FILE")?,"environmentFiles":files}))
}

#[cfg(unix)]
pub async fn serve(path: &str, proof: Value) -> io::Result<()> {
    use std::os::unix::fs::{FileTypeExt, PermissionsExt};
    use std::path::Path;
    use tokio::{io::AsyncWriteExt, net::UnixListener};
    let path = Path::new(path);
    // Only a stale socket in the dedicated service-private directory is removable.
    match fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_socket() => fs::remove_file(path)?,
        Ok(_) => {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "adoption socket occupied",
            ))
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => (),
        Err(error) => return Err(error),
    }
    let listener = UnixListener::bind(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    let bytes = serde_json::to_vec(&proof)?;
    loop {
        let (mut stream, _) = listener.accept().await?;
        // The caller cannot supply a UID/header. Linux authenticates the peer.
        if stream.peer_cred()?.uid() != 0 {
            continue;
        }
        // Bounded writes to a single root caller; no requests, secrets or mutation.
        let _ = stream.write_all(&bytes).await;
        let _ = stream.shutdown().await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_source_provenance_is_excluded_from_loaded_configuration() {
        let a = json!({"artifact":{"commit":"a"},"owner":"alice","service":{"bind_port":1}});
        let mut b = a.clone();
        b["artifact"]["commit"] = json!("b");
        assert_eq!(config_digest(&a), config_digest(&b));
        b["owner"] = json!("bob");
        assert_ne!(config_digest(&a), config_digest(&b));
        b = a.clone();
        b["service"]["bind_port"] = json!(2);
        assert_ne!(config_digest(&a), config_digest(&b));
    }

    #[test]
    fn frozen_evidence_uses_consumed_config_and_ca_even_after_disk_policy_changes() {
        let directory =
            std::env::temp_dir().join(format!("reviewer-loaded-inputs-{}", std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        let key = directory.join("key");
        let unit = directory.join("unit");
        let env = directory.join("env");
        let config_path = directory.join("config");
        fs::write(&key, "synthetic-private-input").unwrap();
        fs::write(&unit, "unit").unwrap();
        fs::write(&env, "environment").unwrap();
        let environment: BTreeMap<String, String> = BTreeMap::from([
            (
                "GITHUB_APP_PRIVATE_KEY_FILE".into(),
                key.to_str().unwrap().into(),
            ),
            (
                "REVIEWER_ADOPTION_UNIT_FILE".into(),
                unit.to_str().unwrap().into(),
            ),
            (
                "REVIEWER_ADOPTION_ENV_FILES".into(),
                env.to_str().unwrap().into(),
            ),
        ]);
        let loaded = json!({"artifact":{"commit":"a"},"owner":"alice"});
        let proof = capture_with_environment(&loaded, b"consumed-ca", &environment).unwrap();
        fs::write(&config_path, r#"{"owner":"bob"}"#).unwrap();
        assert_eq!(proof["config"], config_digest(&loaded));
        assert_ne!(proof["config"], config_digest(&json!({"owner":"bob"})));
        assert_eq!(proof["ca"], digest(b"consumed-ca"));
        assert_ne!(proof["ca"], digest(b"replacement-ca"));
        assert!(!proof.to_string().contains("synthetic-private-input"));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn missing_optional_input_is_an_error_without_a_partial_proof_or_panic() {
        let directory =
            std::env::temp_dir().join(format!("reviewer-missing-inputs-{}", std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        let present = directory.join("present");
        fs::write(&present, "synthetic-private-input").unwrap();
        let missing = directory.join("missing");
        let environment: BTreeMap<String, String> = BTreeMap::from([
            (
                "GITHUB_APP_PRIVATE_KEY_FILE".into(),
                present.to_str().unwrap().into(),
            ),
            (
                "REVIEWER_ADOPTION_UNIT_FILE".into(),
                present.to_str().unwrap().into(),
            ),
            (
                "REVIEWER_ADOPTION_ENV_FILES".into(),
                present.to_str().unwrap().into(),
            ),
        ]);
        for name in environment.keys() {
            let mut inputs = environment.clone();
            inputs.insert(name.clone(), missing.to_str().unwrap().into());
            assert!(capture_with_environment(&json!({}), b"consumed-ca", &inputs).is_err());
        }
        fs::remove_dir_all(directory).unwrap();
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn private_socket_authenticates_kernel_peer_and_returns_only_frozen_proof() {
        use tokio::{io::AsyncReadExt, net::UnixStream};
        let path =
            std::env::temp_dir().join(format!("reviewer-loaded-proof-{}.sock", std::process::id()));
        let _ = fs::remove_file(&path);
        let target = path.to_str().unwrap().to_owned();
        let proof = json!({"schemaVersion":1,"pid":std::process::id(),"config":"frozen"});
        let expected = proof.clone();
        let server = tokio::spawn(async move { serve(&target, proof).await });
        let mut stream = loop {
            match UnixStream::connect(&path).await {
                Ok(stream) => break stream,
                Err(_) => {
                    assert!(!server.is_finished(), "proof server failed before bind");
                    tokio::task::yield_now().await;
                }
            }
        };
        let uid = stream.peer_cred().unwrap().uid();
        let mut bytes = Vec::new();
        stream.read_to_end(&mut bytes).await.unwrap();
        if uid == 0 {
            assert_eq!(serde_json::from_slice::<Value>(&bytes).unwrap(), expected);
        } else {
            assert!(
                bytes.is_empty(),
                "non-root callers receive no loaded evidence"
            );
        }
        server.abort();
        fs::remove_file(path).unwrap();
    }
}
