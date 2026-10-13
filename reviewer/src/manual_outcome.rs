//! A narrow mTLS-authenticated handoff to the protected Writer capability.
//! No caller can choose a program, configuration, credential or Writer operation.
use crate::*;
use std::process::Stdio;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

const MAX_INPUT: usize = 60_000;
const MAX_RECEIPT: usize = 32 * 1024;

pub(crate) fn tool(repositories: &BTreeSet<String>) -> Value {
    json!({"name":"submit_manual_outcome",
        "description":"Submit the result of an already admitted manual Codex attempt directly to trusted Writer. Writer validates binding and publishes or recovers one canonical Writer Bot Outcome. This is a claim submission, not independent acceptance; it never starts Codex, merges, or closes an Issue.",
        "inputSchema":{"type":"object","additionalProperties":false,"required":["repository","task","run_id","result"],"properties":{
            "repository":repository_schema(repositories),
            "task":{"type":"integer","minimum":1,"maximum":9007199254740991_u64},
            "run_id":{"type":"integer","minimum":1,"maximum":9007199254740991_u64},
            "result":{"type":"object"}}},
        "annotations":{"readOnlyHint":false,"destructiveHint":true,"idempotentHint":true,"openWorldHint":true}})
}

pub(crate) fn valid_input(
    repositories: &BTreeSet<String>,
    args: &Value,
) -> Result<(), &'static str> {
    let object = args.as_object().ok_or("INVALID_MANUAL_OUTCOME")?;
    if object.len() != 4
        || !["repository", "task", "run_id", "result"]
            .iter()
            .all(|key| object.contains_key(*key))
    {
        return Err("INVALID_MANUAL_OUTCOME");
    }
    if args["repository"]
        .as_str()
        .is_none_or(|repo| !repositories.contains(repo))
    {
        return Err("REPOSITORY_NOT_ALLOWED");
    }
    if args["task"]
        .as_u64()
        .is_none_or(|task| task == 0 || task > 9_007_199_254_740_991)
        || args["run_id"]
            .as_u64()
            .is_none_or(|run| run == 0 || run > 9_007_199_254_740_991)
        || args["result"]
            .as_object()
            .is_none_or(|result| result.is_empty())
    {
        return Err("INVALID_MANUAL_OUTCOME");
    }
    if serde_json::to_vec(args).map_or(true, |bytes| bytes.len() > MAX_INPUT) {
        return Err("MANUAL_OUTCOME_TOO_LARGE");
    }
    Ok(())
}

fn receipt(args: &Value, writer_actor: &str, bytes: &[u8]) -> Result<Value, &'static str> {
    let response = serde_json::from_slice::<strict_json::StrictJson>(bytes)
        .map_err(|_| "WRITER_RECEIPT_INVALID")?
        .0;
    // Never return root helper diagnostics, raw output or caller-selected URLs.
    if let Some(code) = response["error_code"].as_str().filter(|code| {
        !code.is_empty()
            && code.len() <= 100
            && code
                .bytes()
                .all(|ch| ch.is_ascii_uppercase() || ch.is_ascii_digit() || ch == b'_')
    }) {
        return Ok(json!({"content":[{"type":"text","text":code}],"isError":true}));
    }
    let status = response["status"]
        .as_str()
        .filter(|status| ["PUBLISHED", "RECOVERED", "DUPLICATE_SUPPRESSED"].contains(status))
        .ok_or("WRITER_RECEIPT_INVALID")?;
    let outcome = &response["outcome"];
    let native_id = outcome["id"]
        .as_u64()
        .filter(|id| *id > 0 && *id <= 9_007_199_254_740_991)
        .ok_or("WRITER_RECEIPT_INVALID")?;
    let parent = &outcome["parent"];
    let number = parent["number"]
        .as_u64()
        .filter(|id| *id > 0 && *id <= 9_007_199_254_740_991)
        .ok_or("WRITER_RECEIPT_INVALID")?;
    let segment = match parent["kind"].as_str() {
        Some("issue") if parent["number"] == args["task"] => "issues",
        Some("pull_request") => "pull",
        _ => return Err("WRITER_RECEIPT_INVALID"),
    };
    let expected_url = format!(
        "https://github.com/{}/{segment}/{number}#issuecomment-{native_id}",
        args["repository"].as_str().unwrap()
    );
    if response["repository"] != args["repository"]
        || response["task"] != args["task"]
        || response["run_id"] != args["run_id"]
        || response["writer_actor"] != writer_actor
        || outcome["parent"] != args["result"]["parent"]
        || outcome["url"] != expected_url
        || outcome["sha256"]
            .as_str()
            .is_none_or(|hash| !is_lower_hex(hash, 64))
    {
        return Err("WRITER_RECEIPT_INVALID");
    }
    Ok(
        json!({"content":[{"type":"text","text":status}],"structuredContent":{
        "status":status,"repository":args["repository"],"task":args["task"],"run_id":args["run_id"],
        "outcome":{"id":native_id,"url":expected_url,"sha256":outcome["sha256"],"parent":{"kind":parent["kind"],"number":number}},
        "writer_actor":writer_actor,"independent_acceptance":false,"merge_performed":false,"issue_closure_performed":false}}),
    )
}

pub(crate) async fn submit(app: &RepositoryTarget<'_>, args: &Value) -> Value {
    if !app.policy.manual_outcome_enabled {
        return task_authority::error("MANUAL_OUTCOME_CAPABILITY_DISABLED");
    }
    let operation = async {
        let mut child = tokio::process::Command::new(&app.policy.manual_outcome_client_path)
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .current_dir("/")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .map_err(|_| "WRITER_CAPABILITY_UNAVAILABLE")?;
        let mut stdin = child.stdin.take().ok_or("WRITER_CAPABILITY_UNAVAILABLE")?;
        let bytes = serde_json::to_vec(args).map_err(|_| "INVALID_MANUAL_OUTCOME")?;
        stdin
            .write_all(&bytes)
            .await
            .map_err(|_| "WRITER_CAPABILITY_UNAVAILABLE")?;
        stdin
            .shutdown()
            .await
            .map_err(|_| "WRITER_CAPABILITY_UNAVAILABLE")?;
        drop(stdin);
        let mut bytes = Vec::new();
        child
            .stdout
            .take()
            .ok_or("WRITER_CAPABILITY_UNAVAILABLE")?
            .take((MAX_RECEIPT + 1) as u64)
            .read_to_end(&mut bytes)
            .await
            .map_err(|_| "WRITER_RECEIPT_UNAVAILABLE")?;
        if bytes.len() > MAX_RECEIPT {
            return Err("WRITER_RECEIPT_TOO_LARGE");
        }
        let status = child
            .wait()
            .await
            .map_err(|_| "WRITER_RECEIPT_UNAVAILABLE")?;
        // A nonzero helper exit can still carry a bounded public error code.
        let result = receipt(args, &app.policy.writer_actor, &bytes)?;
        if !status.success() && result["isError"] != true {
            return Err("WRITER_RECEIPT_UNAVAILABLE");
        }
        Ok(result)
    };
    match tokio::time::timeout(std::time::Duration::from_secs(60), operation).await {
        Ok(Ok(result)) => result,
        Ok(Err(code)) => task_authority::error(code),
        Err(_) => task_authority::error("WRITER_CAPABILITY_TIMEOUT"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn input() -> Value {
        json!({"repository":"example-org/sample-project","task":24,"run_id":10,"result":{"parent":{"kind":"issue","number":24},"summary":"Bounded result"}})
    }
    #[test]
    fn bounded_submission_rejects_transport_and_identity_overrides() {
        let repositories = BTreeSet::from(["example-org/sample-project".into()]);
        valid_input(&repositories, &input()).unwrap();
        for key in [
            "command",
            "config",
            "credential",
            "operation",
            "owner_authorization",
        ] {
            let mut args = input();
            args[key] = json!("caller-selected");
            assert_eq!(
                valid_input(&repositories, &args),
                Err("INVALID_MANUAL_OUTCOME")
            );
        }
        for run in [
            json!(0),
            json!("run-10"),
            json!(-1),
            json!(1.5),
            Value::Null,
        ] {
            let mut args = input();
            args["run_id"] = json!(run);
            assert_eq!(
                valid_input(&repositories, &args),
                Err("INVALID_MANUAL_OUTCOME")
            );
        }
        let mut args = input();
        args["result"] = json!({"summary":"x".repeat(MAX_INPUT)});
        assert_eq!(
            valid_input(&repositories, &args),
            Err("MANUAL_OUTCOME_TOO_LARGE")
        );
    }
    #[test]
    fn only_exact_public_writer_receipt_is_exposed() {
        let args = input();
        let public = json!({"status":"PUBLISHED","repository":args["repository"],"task":24,"run_id":10,"writer_actor":"writer[bot]",
            "outcome":{"id":99,"url":"https://github.com/example-org/sample-project/issues/24#issuecomment-99","sha256":"a".repeat(64),"parent":{"kind":"issue","number":24}},"protected_diagnostic":"private"});
        let result = receipt(&args, "writer[bot]", &serde_json::to_vec(&public).unwrap()).unwrap();
        assert!(!result.to_string().contains("private"));
        assert_eq!(result["structuredContent"]["independent_acceptance"], false);
        for key in ["repository", "run_id", "writer_actor"] {
            let mut invalid = public.clone();
            invalid[key] = json!("unexpected");
            assert_eq!(
                receipt(&args, "writer[bot]", &serde_json::to_vec(&invalid).unwrap()),
                Err("WRITER_RECEIPT_INVALID")
            );
        }
        let mut wrong_parent = public.clone();
        wrong_parent["outcome"]["parent"] = json!({"kind":"pull_request","number":25});
        wrong_parent["outcome"]["url"] =
            json!("https://github.com/example-org/sample-project/pull/25#issuecomment-99");
        assert_eq!(
            receipt(
                &args,
                "writer[bot]",
                &serde_json::to_vec(&wrong_parent).unwrap()
            ),
            Err("WRITER_RECEIPT_INVALID")
        );
        let error = receipt(
            &args,
            "writer[bot]",
            br#"{"error_code":"MANUAL_OUTCOME_BINDING_INVALID","private":"secret"}"#,
        )
        .unwrap();
        assert!(!error.to_string().contains("secret"));
    }

    #[test]
    fn public_receipt_status_is_publication_only() {
        let args = input();
        let mut public = json!({"repository":args["repository"],"task":24,"run_id":10,"writer_actor":"writer[bot]",
            "outcome":{"id":99,"url":"https://github.com/example-org/sample-project/issues/24#issuecomment-99","sha256":"a".repeat(64),"parent":{"kind":"issue","number":24}}});
        for status in ["PUBLISHED", "RECOVERED", "DUPLICATE_SUPPRESSED"] {
            public["status"] = json!(status);
            let result =
                receipt(&args, "writer[bot]", &serde_json::to_vec(&public).unwrap()).unwrap();
            assert_eq!(result["structuredContent"]["status"], status);
            assert!(result["structuredContent"]
                .get("execution_status")
                .is_none());
        }
        for status in [
            "IMPLEMENTED",
            "IMPLEMENTED_PENDING_FRESH_REVIEW",
            "BLOCKED",
            "APPROVE",
            "PASS",
            "published",
            "",
        ] {
            public["status"] = json!(status);
            assert_eq!(
                receipt(&args, "writer[bot]", &serde_json::to_vec(&public).unwrap()),
                Err("WRITER_RECEIPT_INVALID")
            );
        }
    }

    #[test]
    fn large_complete_v3_and_v4_claims_fit_without_truncation() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../contracts/fixtures/publication-rendering.json"
        ))
        .unwrap();
        let repositories = BTreeSet::from(["example-org/sample-project".into()]);
        for version in ["3.0", "4.0"] {
            let mut record = fixture["cases"]
                .as_array()
                .unwrap()
                .iter()
                .find(|case| {
                    case["record"]["kind"] == "outcome"
                        && case["record"]["schema_version"] == version
                })
                .unwrap()["record"]
                .clone();
            record["limitations"] = json!(vec!["x".repeat(3000); 18]);
            task_authority::validate_record(&record).unwrap();
            let args = json!({"repository":record["repository"],"task":record["task"],"run_id":10,"result":record});
            let bytes = serde_json::to_vec(&args).unwrap();
            assert!(bytes.len() > 54_000 && bytes.len() < MAX_INPUT);
            valid_input(&repositories, &args).unwrap();
            assert_eq!(
                serde_json::from_slice::<Value>(&bytes).unwrap()["result"]["limitations"],
                args["result"]["limitations"]
            );
        }
    }
}
