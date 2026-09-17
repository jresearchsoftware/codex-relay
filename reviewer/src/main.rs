use axum::{
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    middleware,
    response::IntoResponse,
    routing::post,
    Json, Router,
};
use clap::Parser;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    net::{IpAddr, SocketAddr},
    sync::{Arc, Mutex},
};
use unicode_normalization::UnicodeNormalization;
mod executable_cr;
mod github;
mod mtls_identity;
mod store;
mod strict_json;
#[derive(Clone, Parser)]
struct Args {
    #[arg(long, env = "REVIEWER_MCP_CONFIG")]
    config: String,
}

#[derive(Debug, PartialEq)]
struct RuntimeConfig {
    policy: ReviewPolicy,
    repository: String,
    host: String,
    port: u16,
    mount: String,
    bind_mode: String,
    bind_network: String,
    gateway_validated: bool,
}

#[derive(Clone)]
struct App {
    policy: ReviewPolicy,
    repository: String,
    enabled: bool,
    store: Arc<Mutex<store::Store>>,
    github: github::Github,
    trusted_client_ca: Arc<Vec<u8>>,
    #[cfg(test)]
    observed_arguments: tests::ObservedArguments,
}
fn err(id: Value, code: i32, message: &str) -> Value {
    json!({"jsonrpc":"2.0","id":id,"error":{"code":code,"message":message}})
}
fn tools(validation_names: &[String], repository: &str) -> Value {
    let check = json!({
        "name": "check_pr_review_target",
        "description": "Check an allowlisted PR review target without mutation.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": false,
            "required": ["repository", "pr_number", "expected_head_sha"],
            "properties": {
                "repository": {"type": "string", "const": repository},
                "pr_number": {"type": "integer", "minimum": 1, "maximum": 9007199254740991_u64},
                "expected_head_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}
            }
        },
        "annotations": {"readOnlyHint": true, "destructiveHint": false, "openWorldHint": true}
    });
    let finding = json!({
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "severity", "title", "detail", "evidence"],
        "properties": {
            "id": {"type": "string", "minLength": 1, "maxLength": 64},
            "severity": {"enum": ["blocker", "major", "minor", "suggestion"]},
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "detail": {"type": "string", "minLength": 1, "maxLength": 3000},
            "evidence": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 500}}
        }
    });
    let mut submit = json!({
        "name": "submit_pr_review",
        "description": "Publish an exact-head GitHub review and SHA-bound check. REQUEST_CHANGES requires structured change_request; Reviewer validates and renders all executable data. APPROVE uses review_body only (optional non-executable structured_findings).",
        "inputSchema": {
            "type": "object",
            "additionalProperties": false,
            "required": ["repository", "pr_number", "expected_head_sha", "action"],
            "properties": {
                "repository": {"type": "string", "const": repository},
                "pr_number": {"type": "integer", "minimum": 1, "maximum": 9007199254740991_u64},
                "expected_head_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                "action": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES"]},
                "review_body": {"type": "string", "minLength": 1, "maxLength": 12000},
                "structured_findings": {"type": "array", "maxItems": 30},
            }
        },
        "annotations": {"readOnlyHint": false, "destructiveHint": true, "idempotentHint": true, "openWorldHint": true}
    });
    submit["inputSchema"]["properties"]["structured_findings"] =
        json!({"type": "array", "maxItems": 30, "items": finding});
    submit["inputSchema"]["properties"]["change_request"] =
        executable_cr::input_schema(validation_names);
    json!([check, submit])
}
fn valid_input(
    validation_names: &[String],
    repository: &str,
    name: &str,
    arguments: &Value,
) -> Result<(), &'static str> {
    let expected: &[&str] = if name == "check_pr_review_target" {
        &["repository", "pr_number", "expected_head_sha"]
    } else if name == "submit_pr_review" {
        &[
            "repository",
            "pr_number",
            "expected_head_sha",
            "action",
            "review_body",
            "structured_findings",
            "change_request",
        ]
    } else {
        return Err("UNKNOWN_TOOL");
    };
    if arguments
        .as_object()
        .is_none_or(|m| m.keys().any(|key| !expected.contains(&key.as_str())))
    {
        return Err("INVALID_PAYLOAD");
    }
    let repo = arguments.get("repository").and_then(Value::as_str);
    if repo != Some(repository) {
        return Err("REPOSITORY_NOT_ALLOWED");
    }
    if arguments
        .get("pr_number")
        .and_then(Value::as_i64)
        .is_none_or(|n| !(1..=9_007_199_254_740_991).contains(&n))
    {
        return Err("INVALID_PR_NUMBER");
    }
    let sha = arguments
        .get("expected_head_sha")
        .and_then(Value::as_str)
        .unwrap_or("");
    if sha.len() != 40
        || !sha
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return Err("INVALID_HEAD_SHA");
    }
    if name == "submit_pr_review" {
        if !matches!(
            arguments.get("action").and_then(Value::as_str),
            Some("APPROVE") | Some("REQUEST_CHANGES")
        ) {
            return Err("ACTION_NOT_ALLOWED");
        }
        if serde_json::to_vec(arguments).map_or(true, |bytes| {
            bytes.len()
                > executable_cr::definition()["max_payload_bytes"]
                    .as_u64()
                    .unwrap() as usize
        }) {
            return Err("PAYLOAD_TOO_LARGE");
        }
        if arguments["action"] == "REQUEST_CHANGES" {
            if arguments.get("review_body").is_some()
                || arguments.get("structured_findings").is_some()
            {
                return Err("STRUCTURED_CHANGE_REQUEST_REQUIRED");
            }
            executable_cr::render(validation_names, arguments)?;
            return Ok(());
        }
        if arguments.get("change_request").is_some() {
            return Err("APPROVAL_REMEDIATION_FIELDS");
        }
        let body = arguments
            .get("review_body")
            .and_then(Value::as_str)
            .unwrap_or("");
        if body.trim().is_empty()
            || body.len() > 12_000
            || !body.nfc().eq(body.chars())
            || body.to_ascii_lowercase().contains("filecite")
            || body
                .chars()
                .any(|c| c.is_control() && c != '\n' && c != '\r' && c != '\t')
        {
            return Err("INVALID_REVIEW_BODY");
        }
        if let Some(findings) = arguments.get("structured_findings") {
            if findings
                .as_array()
                .is_none_or(|fs| fs.len() > 30 || fs.iter().any(|f| !valid_finding(f)))
            {
                return Err("INVALID_FINDINGS");
            }
        }
    }
    Ok(())
}
fn valid_task_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    let mut has_digit = false;
    for ch in chars.by_ref() {
        if ch.is_ascii_digit() {
            has_digit = true;
        } else if !ch.is_ascii_uppercase() {
            return false;
        }
    }
    has_digit
}

fn valid_part_identifier(value: &str) -> bool {
    value != "0"
        && !value.is_empty()
        && value
            .chars()
            .all(|ch| ch.is_ascii_uppercase() || ch.is_ascii_digit())
        && value.chars().any(|ch| ch.is_ascii_digit())
}
fn valid_finding(finding: &Value) -> bool {
    let Some(f) = finding.as_object() else {
        return false;
    };
    if f.len() != 5
        || ["id", "severity", "title", "detail", "evidence"]
            .iter()
            .any(|key| !f.contains_key(*key))
    {
        return false;
    }
    let valid_text = |key, max| {
        f.get(key).and_then(Value::as_str).is_some_and(|value| {
            !value.trim().is_empty()
                && value.len() <= max
                && value.nfc().eq(value.chars())
                && !value.chars().any(char::is_control)
        })
    };
    let evidence = f.get("evidence").and_then(Value::as_array);
    valid_text("id", 64)
        && matches!(
            f.get("severity").and_then(Value::as_str),
            Some("blocker" | "major" | "minor" | "suggestion")
        )
        && valid_text("title", 200)
        && valid_text("detail", 3000)
        && evidence.is_some_and(|xs| {
            xs.len() <= 10
                && xs.iter().all(|x| {
                    x.as_str().is_some_and(|s| {
                        !s.trim().is_empty()
                            && s.len() <= 500
                            && s.nfc().eq(s.chars())
                            && !s.chars().any(char::is_control)
                    })
                })
        })
}
fn operation_id(validation_names: &[String], arguments: &Value) -> String {
    let body = review_body(validation_names, arguments);
    let body_hash = format!("{:x}", Sha256::digest(body.as_bytes()));
    let finding_digest = finding_digest(validation_names, arguments);
    let value = format!(
        "{}:{}:{}:{}:{}:{body_hash}:{finding_digest}",
        arguments["repository"],
        arguments["pr_number"],
        arguments["expected_head_sha"],
        arguments["action"],
        "connected-reviewer-shape"
    );
    format!("{:x}", Sha256::digest(value.as_bytes()))
}
fn review_body(validation_names: &[String], arguments: &Value) -> String {
    if arguments["action"] == "REQUEST_CHANGES" {
        executable_cr::render(validation_names, arguments).expect("validated CR before publication")
    } else {
        arguments["review_body"]
            .as_str()
            .unwrap_or("")
            .trim()
            .to_string()
    }
}
fn native_review_body(validation_names: &[String], arguments: &Value, operation: &str) -> String {
    format!(
        "{}\n\n<!-- jresearchsoftware-reviewer-relay:v1 operation={operation} -->",
        review_body(validation_names, arguments)
    )
}
fn finding_digest(validation_names: &[String], arguments: &Value) -> String {
    let findings = if arguments["action"] == "REQUEST_CHANGES" {
        executable_cr::normalized(validation_names, &arguments["change_request"])
            .expect("validated CR")["findings"]
            .clone()
    } else {
        arguments
            .get("structured_findings")
            .cloned()
            .unwrap_or(json!([]))
    };
    format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&findings).unwrap_or_default())
    )
}
#[derive(Clone, Debug, PartialEq)]
struct ReviewPolicy {
    validation_names: Vec<String>,
    base_branch: String,
    check_name: String,
    slug: String,
    app_id: String,
    installation_id: String,
    actor: String,
}
fn review_policy(config: &Value) -> ReviewPolicy {
    let field = |value: &Value| {
        value
            .as_str()
            .filter(|s| !s.is_empty())
            .expect("Reviewer consumer field required")
            .to_string()
    };
    let policy = ReviewPolicy {
        validation_names: executable_cr::validation_names(config),
        base_branch: field(&config["baseBranch"]),
        check_name: field(&config["reviewCheckName"]),
        slug: field(&config["githubApp"]["slug"]),
        app_id: field(&config["githubApp"]["appId"]),
        installation_id: field(&config["githubApp"]["installationId"]),
        actor: field(&config["githubApp"]["expectedActor"]),
    };
    let branch = &policy.base_branch;
    assert!(
        !branch.is_empty()
            && branch.len() <= 240
            && branch.starts_with(|c: char| c.is_ascii_alphanumeric())
            && branch
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.' | b'/'))
            && !branch.contains("..")
            && !branch.ends_with('.')
            && branch
                .split('/')
                .all(|part| !part.is_empty() && !part.starts_with('.') && !part.ends_with(".lock")),
        "Invalid base branch"
    );
    assert!(
        policy.check_name.len() <= 100
            && policy
                .check_name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b' ')),
        "Invalid check name"
    );
    assert!(
        policy.slug.len() <= 100
            && policy.slug.starts_with(|c: char| c.is_ascii_alphanumeric())
            && policy
                .slug
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
            && policy.actor == format!("{}[bot]", policy.slug),
        "Invalid Reviewer actor"
    );
    for id in [&policy.app_id, &policy.installation_id] {
        assert!(
            id.len() <= 16 && !id.starts_with('0') && id.bytes().all(|b| b.is_ascii_digit()),
            "Invalid App identity"
        );
    }
    let writer = field(&config["writerActor"]);
    let writer_slug = writer.strip_suffix("[bot]").expect("Invalid Writer actor");
    assert!(
        !writer_slug.is_empty()
            && writer_slug.len() <= 100
            && writer_slug.starts_with(|c: char| c.is_ascii_alphanumeric())
            && writer_slug
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
            && writer != policy.actor,
        "Writer and Reviewer must be valid separate identities"
    );
    policy
}
fn identity_matches(policy: &ReviewPolicy, identity: &Value) -> bool {
    identity.get("slug").and_then(Value::as_str) == Some(policy.slug.as_str())
        && identity
            .get("id")
            .and_then(Value::as_u64)
            .map(|id| id.to_string())
            .as_deref()
            == Some(policy.app_id.as_str())
}

fn target_binding_rejection(
    policy: &ReviewPolicy,
    pr: &Value,
    arguments: &Value,
) -> Option<&'static str> {
    if pr.get("number") != Some(&arguments["pr_number"])
        || pr.pointer("/base/ref").and_then(Value::as_str) != Some(policy.base_branch.as_str())
        || pr.pointer("/base/repo/full_name") != Some(&arguments["repository"])
        || pr.pointer("/head/repo/full_name") != Some(&arguments["repository"])
    {
        return Some("PR_TARGET_MISMATCH");
    }
    None
}

fn publication_rejection(pr: &Value, expected_head_sha: &Value) -> Option<&'static str> {
    let state = pr.get("state").and_then(Value::as_str);
    let merged = pr.get("merged").and_then(Value::as_bool);
    let draft = pr.get("draft").and_then(Value::as_bool);
    let head = pr.pointer("/head/sha").and_then(Value::as_str);
    if state.is_none() || merged.is_none() || draft.is_none() || head.is_none() {
        return Some("PR_STATE_UNAVAILABLE");
    }
    if state != Some("open") {
        return Some(if merged == Some(true) {
            "PR_MERGED"
        } else {
            "PR_NOT_OPEN"
        });
    }
    if merged == Some(true) {
        return Some("PR_MERGED");
    }
    if draft == Some(true) {
        return Some("DRAFT_PR_NOT_READY");
    }
    if pr.pointer("/head/sha") != Some(expected_head_sha) {
        return Some("STALE_HEAD");
    }
    None
}
fn new_cr_step_rejection(pr: &Value, arguments: &Value) -> Option<&'static str> {
    if arguments["action"] != "REQUEST_CHANGES" {
        return None;
    }
    let Some(labels) = pr["labels"].as_array() else {
        return Some("STEP_LABEL_MISSING");
    };
    let steps: Vec<&str> = labels
        .iter()
        .filter_map(|label| label["name"].as_str())
        .filter(|name| name.to_ascii_lowercase().starts_with("step"))
        .collect();
    if steps.is_empty() {
        return Some("STEP_LABEL_MISSING");
    }
    if steps.len() != 1 {
        return Some("STEP_LABEL_MULTIPLE");
    }
    let step = steps[0]
        .strip_prefix("step-")
        .and_then(|number| number.parse::<u64>().ok());
    let Some(step) = step.filter(|n| *n > 0 && *n < 9_007_199_254_740_991) else {
        return Some("STEP_LABEL_INVALID");
    };
    if steps[0] != format!("step-{step}") {
        return Some("STEP_LABEL_INVALID");
    }
    if arguments["change_request"]["step"].as_u64() != Some(step + 1) {
        return Some("CHANGE_REQUEST_STEP_MISMATCH");
    }
    None
}

async fn mcp(
    State(app): State<App>,
    headers: HeaderMap,
    Json(strict_json::StrictJson(request)): Json<strict_json::StrictJson>,
) -> impl IntoResponse {
    if headers.get("origin").is_some() {
        return (
            StatusCode::FORBIDDEN,
            Json(err(Value::Null, -32000, "ORIGIN_NOT_ALLOWED")),
        )
            .into_response();
    };
    let accept = headers
        .get("accept")
        .and_then(|x| x.to_str().ok())
        .unwrap_or("");
    if !(accept.is_empty()
        || accept.contains("application/json") && accept.contains("text/event-stream"))
    {
        return (
            StatusCode::NOT_ACCEPTABLE,
            Json(err(Value::Null, -32000, "ACCEPT_HEADER_REQUIRED")),
        )
            .into_response();
    }
    let id = request.get("id").cloned().unwrap_or(Value::Null);
    let result = match request.get("method").and_then(Value::as_str) {
        Some("initialize") => {
            json!({"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"codex-relay-reviewer","version":"0.1.0"}})
        }
        Some("tools/list") => json!({"tools":tools(&app.policy.validation_names, &app.repository)}),
        Some("tools/call") => {
            let name = request
                .pointer("/params/name")
                .and_then(Value::as_str)
                .unwrap_or("");
            let arguments = request.pointer("/params/arguments").unwrap_or(&Value::Null);
            // Test-only observation at the validation boundary; never log caller payloads.
            #[cfg(test)]
            app.observed_arguments
                .lock()
                .expect("argument observations")
                .push((name.to_string(), arguments.clone()));
            if let Err(code) = valid_input(
                &app.policy.validation_names,
                &app.repository,
                name,
                arguments,
            ) {
                json!({"content":[{"type":"text","text":code}],"isError":true})
            } else if name == "check_pr_review_target" {
                match app
                    .github
                    .get_pr(
                        arguments["repository"].as_str().unwrap_or(""),
                        arguments["pr_number"].as_i64().unwrap_or(0),
                    )
                    .await
                {
                    Ok(pr) => match app.github.app_identity().await {
                        Ok(identity) if identity_matches(&app.policy, &identity) => {
                            if let Some(code) =
                                target_binding_rejection(&app.policy, &pr, arguments)
                            {
                                return (StatusCode::OK, Json(json!({"jsonrpc":"2.0","id":id,"result":{"content":[{"type":"text","text":code}],"isError":true}}))).into_response();
                            }
                            let state = pr.get("state").and_then(Value::as_str);
                            let draft = pr.get("draft").and_then(Value::as_bool);
                            let merged = pr.get("merged").and_then(Value::as_bool);
                            let current_head = pr.pointer("/head/sha").and_then(Value::as_str);
                            if state.is_none()
                                || draft.is_none()
                                || merged.is_none()
                                || current_head.is_none()
                            {
                                json!({"content":[{"type":"text","text":"PR_STATE_UNAVAILABLE"}],"isError":true})
                            } else {
                                json!({"content":[{"type":"text","text":"OK"}],"structuredContent":{"current_head_sha":current_head,"state":state,"draft":draft,"merged":merged,"ready_for_review":state == Some("open") && !merged.unwrap_or(true) && !draft.unwrap_or(true) && current_head == arguments["expected_head_sha"].as_str(),"author":pr.pointer("/user/login"),"authenticated_app_slug":identity.get("slug"),"expected_actor":app.policy.actor,"exact_head":current_head == arguments["expected_head_sha"].as_str()}})
                            }
                        }
                        Ok(_) => {
                            json!({"content":[{"type":"text","text":"ACTOR_VERIFICATION_FAILED"}],"isError":true})
                        }
                        Err(code) => {
                            json!({"content":[{"type":"text","text":code}],"isError":true})
                        }
                    },
                    Err(code) => json!({"content":[{"type":"text","text":code}],"isError":true}),
                }
            } else if name == "submit_pr_review" && !app.enabled {
                tracing::info!(event = "review_attempt", outcome = "RELAY_DISABLED", repository = %arguments["repository"], pr_number = ?arguments["pr_number"]);
                json!({"content":[{"type":"text","text":"RELAY_DISABLED"}],"isError":true})
            } else if name == "submit_pr_review" {
                let pr = match app.github.get_pr(arguments["repository"].as_str().unwrap_or(""),arguments["pr_number"].as_i64().unwrap_or(0)).await { Ok(value)=>value, Err(code)=>return (StatusCode::OK,Json(json!({"jsonrpc":"2.0","id":id,"result":{"content":[{"type":"text","text":code}],"isError":true}}))).into_response() };
                if let Some(outcome) = target_binding_rejection(&app.policy, &pr, arguments)
                    .or_else(|| publication_rejection(&pr, &arguments["expected_head_sha"]))
                {
                    tracing::info!(event = "review_attempt", outcome, repository = %arguments["repository"], pr_number = ?arguments["pr_number"]);
                    if outcome == "DRAFT_PR_NOT_READY" {
                        json!({"content":[{"type":"text", "text":outcome}],"isError":true,"structuredContent":{"draft":true,"ready_for_review":false,"current_head_sha":pr.pointer("/head/sha")}})
                    } else {
                        json!({"content":[{"type":"text","text":outcome}],"isError":true})
                    }
                } else {
                    match app.github.app_identity().await { Ok(x) if identity_matches(&app.policy, &x) => {}, Ok(_) => return (StatusCode::OK,Json(json!({"jsonrpc":"2.0","id":id,"result":{"content":[{"type":"text","text":"ACTOR_VERIFICATION_FAILED"}],"isError":true}}))).into_response(), Err(code) => return (StatusCode::OK,Json(json!({"jsonrpc":"2.0","id":id,"result":{"content":[{"type":"text","text":code}],"isError":true}}))).into_response() };
                    let operation = operation_id(&app.policy.validation_names, arguments);
                    let marker =
                        format!("jresearchsoftware-reviewer-relay:v1 operation={operation}");
                    let reserve = app.store.lock().expect("store lock").reserve(
                        &operation,
                        &finding_digest(&app.policy.validation_names, arguments),
                    );
                    match reserve {
                        Ok(false) => {
                            let known = app
                                .store
                                .lock()
                                .expect("store lock")
                                .known(&operation)
                                .ok()
                                .flatten();
                            if known
                                .as_ref()
                                .and_then(|x| x.actor_login.as_deref())
                                .is_some_and(|actor| actor != app.policy.actor)
                            {
                                return (StatusCode::OK, Json(json!({"jsonrpc":"2.0","id":id,"result":{"isError":true,"content":[{"type":"text","text":"ACTOR_VERIFICATION_FAILED"}]}}))).into_response();
                            }
                            if known
                                .as_ref()
                                .is_some_and(|x| x.status == "REVIEW_PUBLISHED")
                            {
                                match known.as_ref() {
                                    Some(operation_state) => {
                                        match (
                                            operation_state.review_id,
                                            operation_state.review_url.as_deref(),
                                            operation_state.actor_login.as_deref(),
                                        ) {
                                            (Some(review_id), Some(review_url), Some(actor)) => {
                                                complete_check(
                                                    &app,
                                                    &operation,
                                                    review_id,
                                                    review_url,
                                                    actor,
                                                    arguments,
                                                    "CHECK_RECOVERED",
                                                )
                                                .await
                                            }
                                            _ => {
                                                json!({"content":[{"type":"text","text":"INTERNAL_RELAY_ERROR"}],"isError":true})
                                            }
                                        }
                                    }
                                    None => {
                                        json!({"content":[{"type":"text","text":"INTERNAL_RELAY_ERROR"}],"isError":true})
                                    }
                                }
                            } else if known.as_ref().is_some_and(|x| x.status == "RESERVED") {
                                match app
                                    .github
                                    .find_review(
                                        arguments["repository"].as_str().unwrap_or(""),
                                        arguments["pr_number"].as_i64().unwrap_or(0),
                                        &marker,
                                    )
                                    .await
                                {
                                    Ok(Some(review)) => {
                                        record_review(
                                            &app,
                                            &operation,
                                            &review,
                                            "DUPLICATE_RECOVERED",
                                            arguments,
                                        )
                                        .await
                                    }
                                    Ok(None) => {
                                        json!({"content":[{"type":"text","text":"PUBLICATION_UNCERTAIN"}],"isError":true})
                                    }
                                    Err(code) => {
                                        json!({"content":[{"type":"text","text":code}],"isError":true})
                                    }
                                }
                            } else {
                                tracing::info!(event = "review_attempt", outcome = "DUPLICATE_SUPPRESSED", operation = %operation);
                                json!({"content":[{"type":"text","text":"DUPLICATE_SUPPRESSED"}],"structuredContent":{"status":known.as_ref().map(|x| &x.status),"review_id":known.as_ref().and_then(|x| x.review_id),"review_url":known.as_ref().and_then(|x| x.review_url.as_ref())}})
                            }
                        }
                        Ok(true) => match app
                            .github
                            .find_review(
                                arguments["repository"].as_str().unwrap_or(""),
                                arguments["pr_number"].as_i64().unwrap_or(0),
                                &marker,
                            )
                            .await
                        {
                            Ok(Some(review)) => {
                                record_review(
                                    &app,
                                    &operation,
                                    &review,
                                    "DUPLICATE_RECOVERED",
                                    arguments,
                                )
                                .await
                            }
                            Ok(None) => {
                                // Existing review/transport recovery above preserves
                                // its authorized Step. Only a genuinely new native
                                // CR advances from the current PR label. Owner
                                // orchestration checks the Issue and mutates labels.
                                if let Some(code) = new_cr_step_rejection(&pr, arguments) {
                                    return (StatusCode::OK, Json(json!({"jsonrpc":"2.0","id":id,"result":{"content":[{"type":"text","text":code}],"isError":true}}))).into_response();
                                }
                                let payload = json!({"commit_id":arguments["expected_head_sha"],"event":arguments["action"],"body":native_review_body(&app.policy.validation_names, arguments, &operation)});
                                match app
                                    .github
                                    .create_review(
                                        arguments["repository"].as_str().unwrap_or(""),
                                        arguments["pr_number"].as_i64().unwrap_or(0),
                                        &payload,
                                    )
                                    .await
                                {
                                    Ok(review) => {
                                        record_review(
                                            &app,
                                            &operation,
                                            &review,
                                            "PUBLISHED",
                                            arguments,
                                        )
                                        .await
                                    }
                                    Err(code) => {
                                        let _ = app
                                            .store
                                            .lock()
                                            .expect("store lock")
                                            .retryable_failure(&operation);
                                        tracing::warn!(event = "review_attempt", outcome = "RETRYABLE_FAILURE", operation = %operation, error_code = code);
                                        json!({"content":[{"type":"text","text":code}],"isError":true})
                                    }
                                }
                            }
                            Err(code) => {
                                json!({"content":[{"type":"text","text":code}],"isError":true})
                            }
                        },
                        Err(_) => {
                            json!({"content":[{"type":"text","text":"INTERNAL_RELAY_ERROR"}],"isError":true})
                        }
                    }
                }
            } else {
                json!({"content":[{"type":"text","text":"MOCK_ONLY_NOT_CONFIGURED"}],"isError":true})
            }
        }
        _ => return (StatusCode::OK, Json(err(id, -32601, "Method not found"))).into_response(),
    };
    (
        StatusCode::OK,
        Json(json!({"jsonrpc":"2.0","id":id,"result":result})),
    )
        .into_response()
}
async fn complete_check(
    app: &App,
    operation: &str,
    review_id: i64,
    url: &str,
    actor: &str,
    arguments: &Value,
    outcome: &str,
) -> Value {
    let repository = arguments["repository"].as_str().unwrap_or("");
    let sha = arguments["expected_head_sha"].as_str().unwrap_or("");
    let check = match app.github.find_check(repository, sha, operation).await {
        Ok(Some(check)) => check,
        Ok(None) => {
            let action = arguments["action"].as_str().unwrap_or("");
            let conclusion = if action == "APPROVE" {
                "success"
            } else {
                "failure"
            };
            let title = if action == "APPROVE" {
                "Review approved"
            } else {
                "Changes requested"
            };
            let payload = json!({
                "name":app.policy.check_name,
                "head_sha":sha,
                "external_id":operation,
                "status":"completed",
                "conclusion":conclusion,
                "output":{"title":title,"summary":"GitHub App review completed for this exact pull-request head."}
            });
            match app.github.create_check(repository, &payload).await {
                Ok(value) => value,
                Err(code) => {
                    let _ = app
                        .store
                        .lock()
                        .expect("store lock")
                        .check_retryable_failure(operation, "CHECK_CREATION_RETRYABLE_FAILURE");
                    return json!({"content":[{"type":"text","text":"REVIEW_PUBLISHED_CHECK_FAILED"}],"isError":true,"structuredContent":{"review_id":review_id,"reviewed_sha":sha,"check_stage":"CHECK_CREATION_RETRYABLE_FAILURE","error_code":code}});
                }
            }
        }
        Err(code) => {
            let _ = app
                .store
                .lock()
                .expect("store lock")
                .check_retryable_failure(operation, "CHECK_LOOKUP_RETRYABLE_FAILURE");
            return json!({"content":[{"type":"text","text":"REVIEW_PUBLISHED_CHECK_FAILED"}],"isError":true,"structuredContent":{"review_id":review_id,"reviewed_sha":sha,"check_stage":"CHECK_LOOKUP_RETRYABLE_FAILURE","error_code":code}});
        }
    };
    let check_id = check.get("id").and_then(Value::as_i64);
    let check_url = check.get("html_url").and_then(Value::as_str);
    if check.get("name").and_then(Value::as_str) != Some(app.policy.check_name.as_str())
        || check.get("head_sha").and_then(Value::as_str) != Some(sha)
        || check.pointer("/app/slug").and_then(Value::as_str) != Some(app.policy.slug.as_str())
        || check_id.is_none()
        || check_url.is_none()
    {
        let _ = app
            .store
            .lock()
            .expect("store lock")
            .check_retryable_failure(operation, "CHECK_VERIFICATION_RETRYABLE_FAILURE");
        return json!({"content":[{"type":"text","text":"CHECK_VERIFICATION_FAILED"}],"isError":true,"structuredContent":{"review_id":review_id,"reviewed_sha":sha,"check_stage":"CHECK_VERIFICATION_RETRYABLE_FAILURE"}});
    }
    if app
        .store
        .lock()
        .expect("store lock")
        .published(
            operation,
            check_id.unwrap_or_default(),
            check_url.unwrap_or(""),
        )
        .is_err()
    {
        return json!({"content":[{"type":"text","text":"INTERNAL_RELAY_ERROR"}],"isError":true});
    }
    json!({"content":[{"type":"text","text":outcome}],"structuredContent":{"review_id":review_id,"review_url":url,"check_run_id":check_id,"check_run_url":check_url,"actor_login":actor,"reviewed_sha":sha}})
}

async fn record_review(
    app: &App,
    operation: &str,
    review: &Value,
    outcome: &str,
    arguments: &Value,
) -> Value {
    if arguments["action"] == "REQUEST_CHANGES"
        && (review["state"] != "CHANGES_REQUESTED"
            || review["body"].as_str()
                != Some(
                    native_review_body(&app.policy.validation_names, arguments, operation).as_str(),
                ))
    {
        return json!({"content":[{"type":"text","text":"REVIEW_CONTRACT_VERIFICATION_FAILED"}],"isError":true});
    }
    let actor = review.pointer("/user/login").and_then(Value::as_str);
    let review_id = review.get("id").and_then(Value::as_i64);
    let url = review.get("html_url").and_then(Value::as_str);
    if review.get("commit_id") != Some(&arguments["expected_head_sha"])
        || actor != Some(app.policy.actor.as_str())
        || review_id.is_none()
        || url.is_none()
    {
        return json!({"content":[{"type":"text","text":"ACTOR_VERIFICATION_FAILED"}],"isError":true});
    }
    let review_id = review_id.unwrap_or_default();
    let url = url.unwrap_or("");
    let actor = actor.unwrap_or("");
    if app
        .store
        .lock()
        .expect("store lock")
        .review_published(operation, review_id, url, actor)
        .is_err()
    {
        return json!({"content":[{"type":"text","text":"INTERNAL_RELAY_ERROR"}],"isError":true});
    }
    complete_check(app, operation, review_id, url, actor, arguments, outcome).await
}
async fn sse_not_supported() -> StatusCode {
    StatusCode::METHOD_NOT_ALLOWED
}
fn router(app: App) -> Router {
    Router::new()
        .route("/mcp", post(mcp).get(sse_not_supported))
        .layer(DefaultBodyLimit::max(52_000))
        .route_layer(middleware::from_fn_with_state(
            app.trusted_client_ca.clone(),
            mtls_identity::require_identity_with_trust,
        ))
        .with_state(app)
}

fn valid_repository(repository: &str) -> bool {
    let Some((owner, name)) = repository.split_once('/') else {
        return false;
    };
    (1..=39).contains(&owner.len())
        && owner.starts_with(|c: char| c.is_ascii_alphanumeric())
        && owner.ends_with(|c: char| c.is_ascii_alphanumeric())
        && owner
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-')
        && !owner.contains("--")
        && (1..=100).contains(&name.len())
        && !matches!(name, "." | "..")
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
}

fn load_runtime_config(path: &str) -> RuntimeConfig {
    let text = fs::read_to_string(path).expect("REVIEWER_MCP_CONFIG must be readable");
    let config = serde_json::from_str::<strict_json::StrictJson>(&text)
        .expect("REVIEWER_MCP_CONFIG must be unambiguous JSON")
        .0;
    let repository = config["repository"]
        .as_str()
        .filter(|value| valid_repository(value))
        .expect("Reviewer config repository must be a bounded owner/repository identifier")
        .to_string();
    if config.get("mutation").is_some() {
        panic!("Remove obsolete mutation field; REVIEWER_RELAY_ENABLED alone controls publication");
    }
    if config["service"]["name"] != "reviewer-mcp" {
        panic!("Reviewer service contract is invalid");
    }
    let host = config["service"]["bind_address"]
        .as_str()
        .expect("Reviewer config bind_address is required")
        .to_string();
    let bind_mode = config["service"]["bind_mode"]
        .as_str()
        .expect("Reviewer config bind_mode is required")
        .to_string();
    let bind_network = config["service"]["bind_network"]
        .as_str()
        .expect("Reviewer config bind_network is required")
        .to_string();
    let gateway_validated = config["service"]["gateway_validated"]
        .as_bool()
        .expect("Reviewer config gateway_validated is required");
    if config["service"].get("bind_socket").is_some() {
        panic!("Reviewer Unix-socket transport is retired and cannot appear in the active config");
    }
    let port = config["service"]["bind_port"]
        .as_u64()
        .and_then(|value| u16::try_from(value).ok())
        .expect("Reviewer config bind_port is required");
    let mount = config["service"]["mount_path"]
        .as_str()
        .expect("Reviewer config mount_path is required")
        .to_string();
    let artifact_commit = config["artifact"]["commit"]
        .as_str()
        .expect("Reviewer config artifact commit is required");
    let artifact_sha256 = config["artifact"]["sha256"]
        .as_str()
        .expect("Reviewer config artifact sha256 is required");
    if !is_lower_hex(artifact_commit, 40) || !is_lower_hex(artifact_sha256, 64) {
        panic!("Reviewer config artifact identity is invalid or unresolved");
    }
    let policy = review_policy(&config);
    let runtime_config = RuntimeConfig {
        policy,
        repository,
        host,
        port,
        mount,
        bind_mode,
        bind_network,
        gateway_validated,
    };
    validate_effective_runtime_config(&runtime_config);
    runtime_config
}

fn is_lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_reviewer_bind(host: &str, mode: &str, network: &str, gateway_validated: bool) {
    match mode {
        "a_only_loopback" => {
            if host != "127.0.0.1" || !network.is_empty() || gateway_validated {
                panic!("A-only Reviewer bind must be exactly validated loopback 127.0.0.1");
            }
        }
        "nexus_gateway" | "private_gateway" => {
            let address = host
                .parse::<IpAddr>()
                .expect("Reviewer private gateway address must be an IPv4 address");
            let IpAddr::V4(address) = address else {
                panic!("Reviewer private gateway address must be IPv4")
            };
            if network.is_empty()
                || network.len() > 63
                || !network
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
                || !address.is_private()
                || !gateway_validated
                || address.is_loopback()
                || address.is_unspecified()
                || address.is_multicast()
                || address.octets() == [255, 255, 255, 255]
            {
                panic!("Reviewer private gateway must be a validated non-public host-side bridge gateway");
            }
        }
        _ => panic!("Reviewer bind mode is outside the admitted TCP-only contract"),
    }
}

fn validate_effective_runtime_config(config: &RuntimeConfig) {
    validate_reviewer_bind(
        &config.host,
        &config.bind_mode,
        &config.bind_network,
        config.gateway_validated,
    );
}

fn effective_runtime_config(args: &Args) -> RuntimeConfig {
    load_runtime_config(&args.config)
}

fn publication_enabled(value: Option<&str>) -> bool {
    // Only the exact opt-in enables writes. Unknown values stay disabled.
    value == Some("true")
}

#[tokio::main]
async fn main() {
    let a = Args::parse();
    let effective_config = effective_runtime_config(&a);
    validate_effective_runtime_config(&effective_config);
    let RuntimeConfig {
        policy,
        repository,
        host: configured_host,
        port: configured_port,
        mount: configured_mount,
        ..
    } = effective_config;
    if configured_mount != "/mcp" {
        panic!("REVIEWER_MCP_MOUNT_PATH must remain the canonical /mcp route")
    }
    tracing_subscriber::fmt()
        .with_env_filter("info")
        .with_target(false)
        .init();
    assert_eq!(
        std::env::var("GITHUB_APP_ID").ok().as_deref(),
        Some(policy.app_id.as_str()),
        "App credential/config mismatch"
    );
    assert_eq!(
        std::env::var("GITHUB_APP_INSTALLATION_ID").ok().as_deref(),
        Some(policy.installation_id.as_str()),
        "Installation credential/config mismatch"
    );
    let enabled = publication_enabled(std::env::var("REVIEWER_RELAY_ENABLED").ok().as_deref());
    tracing::info!(event = "publication_mode", enabled);
    let app = router(App {
        policy,
        repository,
        #[cfg(test)]
        observed_arguments: Default::default(),
        enabled,
        store: Arc::new(Mutex::new(
            store::Store::open(
                &std::env::var("REVIEWER_RELAY_DB")
                    .unwrap_or_else(|_| "reviewer-relay.sqlite3".into()),
            )
            .expect("database failed"),
        )),
        github: github::Github::new(),
        trusted_client_ca: Arc::new(
            fs::read(
                std::env::var("REVIEWER_CLIENT_CA_FILE")
                    .expect("REVIEWER_CLIENT_CA_FILE must be set"),
            )
            .expect("REVIEWER_CLIENT_CA_FILE must be readable"),
        ),
    });
    let addr: SocketAddr = format!("{}:{}", configured_host, configured_port)
        .parse()
        .expect("invalid host/port");
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("bind failed");
    axum::serve(listener, app).await.expect("server failed");
}
#[cfg(test)]
mod tests {
    fn test_policy() -> ReviewPolicy {
        ReviewPolicy {
            validation_names: Vec::new(),
            base_branch: "main".into(),
            check_name: "chatgpt-review".into(),
            slug: "example-reviewer".into(),
            app_id: "102".into(),
            installation_id: "202".into(),
            actor: "example-reviewer[bot]".into(),
        }
    }

    use super::*;
    mod portability;
    mod transport;
    use axum::{
        http::{Method, Uri},
        routing::any,
    };
    use minijinja::{context, Environment};
    use rcgen::{
        BasicConstraints, CertificateParams, DistinguishedName, DnType, ExtendedKeyUsagePurpose,
        IsCa, KeyPair,
    };
    use std::path::PathBuf;

    const HEAD: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const TEST_REPOSITORY: &str = "example-org/sample-project";

    const REMOVED_REVIEW_THREAD: &str = "Task 10 — Step 3 — CR-10-002 — test review";
    const REVIEW_BODY: &str = "## Change Request\n\nreview";

    pub(super) type ObservedArguments = Arc<Mutex<Vec<(String, Value)>>>;

    fn base_args(action: &str) -> Value {
        if action == "REQUEST_CHANGES" {
            return cr_fixture();
        }
        json!({"repository":"example-org/sample-project","pr_number":25,"expected_head_sha":HEAD,"action":action,"review_body":REVIEW_BODY})
    }

    fn http_args(findings: Value) -> Value {
        let mut input = cr_fixture();
        if !findings.as_array().unwrap().is_empty() {
            input["change_request"]["findings"] = findings;
        }
        input
    }

    fn fixture_path(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../contracts/test/fixtures")
            .join(name)
    }

    fn cr_fixture() -> Value {
        serde_json::from_str(
            &fs::read_to_string(fixture_path("executable-cr-v2-input.json")).unwrap(),
        )
        .unwrap()
    }

    fn assert_consumer_admits(arguments: &Value, publication: &Value) {
        assert_consumer_admits_with_config(arguments, publication, "example");
    }
    fn assert_consumer_admits_with_config(arguments: &Value, publication: &Value, consumer: &str) {
        use std::{
            io::Write,
            process::{Command, Stdio},
        };
        let driver = fixture_path("../../test-support/roundtrip-driver.mjs");
        let mut child = Command::new("node")
            .env(
                "RELAY_CONSUMER_CONFIG",
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join(format!("../consumer/fixtures/{consumer}.json")),
            )
            .arg(driver)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .expect("Node contract consumer");
        child
            .stdin
            .take()
            .unwrap()
            .write_all(
                &serde_json::to_vec(&json!({"arguments":arguments,"publication":publication}))
                    .unwrap(),
            )
            .unwrap();
        let output = child.wait_with_output().unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(String::from_utf8_lossy(&output.stdout)
            .contains("REVIEWER_PUBLICATION_REMEDIATION_ROUNDTRIP_PASS"));
    }

    #[tokio::test]
    async fn structured_cr_is_published_canonically_and_admitted_by_the_current_consumer() {
        let state = MockState::default();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let args = cr_fixture();
        let expected = fs::read_to_string(fixture_path("executable-cr-v2.md")).unwrap();
        assert_eq!(review_body(&[], &args), expected.trim_end());
        for expected_status in ["PUBLISHED", "DUPLICATE_SUPPRESSED"] {
            let result = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(
                result.pointer("/result/content/0/text"),
                Some(&json!(expected_status))
            );
        }
        let reviews = state.reviews.lock().unwrap();
        assert_eq!(reviews.len(), 1);
        assert!(reviews[0]["body"]
            .as_str()
            .unwrap()
            .starts_with(expected.trim_end()));
        assert_consumer_admits(&args, &reviews[0]);
    }

    #[tokio::test]
    async fn new_cr_publication_roundtrips_through_owner_step_sync_and_matching_launch() {
        let state = MockState::default();
        let mut pr = live_pr();
        pr["labels"] = json!([{"name":"step-5"}]);
        *state.pr.lock().unwrap() = Some(pr);
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let mut args = cr_fixture();
        args["change_request"]["step"] = json!(6);
        args["change_request"]["remediation_thread_title"] =
            json!("Task 24 — Step 6 — Correct the reviewed implementation");
        let result = rpc(
            &http,
            &url,
            1,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(
            result.pointer("/result/content/0/text"),
            Some(&json!("PUBLISHED"))
        );
        let reviews = state.reviews.lock().unwrap();
        assert_eq!(reviews.len(), 1);
        assert_consumer_admits(&args, &reviews[0]);
        // Step metadata mutation is owned by the ordinary owner client, never
        // the Reviewer App's native publication/check requests.
        assert!(!state
            .requests
            .lock()
            .unwrap()
            .iter()
            .any(|r| r.contains("/labels")));
    }

    #[tokio::test]
    async fn new_cr_requires_next_current_step_but_same_published_cr_retry_does_not_increment() {
        for (labels, code) in [
            (json!(null), "STEP_LABEL_MISSING"),
            (json!([]), "STEP_LABEL_MISSING"),
            (
                json!([{"name":"step-1"},{"name":"step-2"}]),
                "STEP_LABEL_MULTIPLE",
            ),
            (json!([{"name":"step-01"}]), "STEP_LABEL_INVALID"),
            (json!([{"name":"step-2"}]), "CHANGE_REQUEST_STEP_MISMATCH"),
        ] {
            let state = MockState::default();
            let mut pr = live_pr();
            pr["labels"] = labels;
            *state.pr.lock().unwrap() = Some(pr);
            let (http, url) = client_with_state(true, None, state.clone()).await;
            let args = cr_fixture();
            let result = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(result.pointer("/result/content/0/text"), Some(&json!(code)));
            assert!(state.reviews.lock().unwrap().is_empty());
        }
        let state = MockState::default();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let args = cr_fixture();
        let first = rpc(
            &http,
            &url,
            1,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(
            first.pointer("/result/content/0/text"),
            Some(&json!("PUBLISHED"))
        );
        let mut pr = live_pr();
        pr["labels"] = json!([{"name":"step-2"}]);
        *state.pr.lock().unwrap() = Some(pr);
        let retry = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(
            retry.pointer("/result/content/0/text"),
            Some(&json!("DUPLICATE_SUPPRESSED"))
        );
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
        assert!(new_cr_step_rejection(&json!({}), &base_args("APPROVE")).is_none());
    }

    #[tokio::test]
    async fn shared_invalid_cr_corpus_is_rejected_before_any_github_request() {
        let state = MockState::default();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let rows: Value = serde_json::from_str(
            &fs::read_to_string(fixture_path("executable-cr-v2-invalid.json")).unwrap(),
        )
        .unwrap();
        for row in rows.as_array().unwrap() {
            let mut args = cr_fixture();
            let keys = row["path"].as_array().unwrap();
            let mut parent = &mut args["change_request"];
            for key in &keys[..keys.len() - 1] {
                parent = if let Some(index) = key.as_u64() {
                    &mut parent[index as usize]
                } else {
                    &mut parent[key.as_str().unwrap()]
                };
            }
            let key = keys.last().unwrap().as_str().unwrap();
            if row["delete"] == true {
                parent.as_object_mut().unwrap().remove(key);
            } else {
                parent[key] = row["value"].clone();
            }
            let expected = row["producer_error"].as_str().unwrap();
            assert_eq!(
                valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &args),
                Err(expected),
                "{}",
                row["name"]
            );
            let response = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(
                response.pointer("/result/content/0/text"),
                Some(&json!(expected)),
                "{}",
                row["name"]
            );
        }
        assert!(state.requests.lock().unwrap().is_empty());
        assert!(state.reviews.lock().unwrap().is_empty());
    }

    #[test]
    fn every_declared_validation_and_safe_profile_round_trips_without_retired_authority() {
        for effort in [
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "future-effort",
            "unknown",
        ] {
            for subagents in [false, true] {
                let mut args = cr_fixture();
                args["change_request"]["codex_effort"] = json!(effort);
                args["change_request"]["subagents_allowed"] = json!(subagents);
                args["change_request"]["required_validation"] = executable_cr::definition()
                    ["input_schema"]["properties"]["required_validation"]["items"]["enum"]
                    .clone();
                assert_eq!(
                    valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &args),
                    Ok(())
                );
                assert_consumer_admits(
                    &args,
                    &json!({"event":"REQUEST_CHANGES", "commit_id":HEAD,"body":review_body(&[], &args)}),
                );
            }
        }
        let mut args = cr_fixture();
        args["change_request"]["step"] = json!(9_007_199_254_740_991u64);
        args["change_request"]["findings"][0]["problem"] = json!("Preserve \"quotes\", commas, colon: [lists], `code`, \\paths & <tags> — café 🦀. The ```reviewer-executable-cr fence is Reviewer-owned.");
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &args),
            Ok(())
        );
        assert_consumer_admits(
            &args,
            &json!({"event":"REQUEST_CHANGES", "commit_id":HEAD,"body":review_body(&[], &args)}),
        );
    }

    #[test]
    fn producer_bounds_the_aggregate_and_rendered_payload_and_requires_structured_cr() {
        let mut args = cr_fixture();
        let finding = args["change_request"]["findings"][0].clone();
        args["change_request"]["findings"] = json!(vec![finding; 31]);
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &args),
            Err("INVALID_CHANGE_REQUEST")
        );
        args = cr_fixture();
        args["change_request"]["findings"][0]["problem"] = json!("x".repeat(50_000));
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &args),
            Err("PAYLOAD_TOO_LARGE")
        );
        args = cr_fixture();
        for finding in args["change_request"]["findings"].as_array_mut().unwrap() {
            for key in ["problem", "impact", "remediation"] {
                finding[key] = json!("a&".repeat(1500));
            }
        }
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &args),
            Err("CR_RENDER_TOO_LARGE")
        );
        args = cr_fixture();
        args["review_body"] = json!("Manually serialized CR");
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &args),
            Err("STRUCTURED_CHANGE_REQUEST_REQUIRED")
        );
        let mut approve = base_args("APPROVE");
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &approve),
            Ok(())
        );
        approve["change_request"] = args["change_request"].clone();
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &approve),
            Err("APPROVAL_REMEDIATION_FIELDS")
        );
    }

    #[test]
    fn operation_identity_binds_all_execution_data_and_normalizes_omitted_defaults() {
        let args = cr_fixture();
        let original = operation_id(&[], &args);
        for (key, value) in [
            ("step", json!(3)),
            ("success_token", json!("READY")),
            ("blocked_outcome", json!("Explain why blocked.")),
            ("codex_model", json!("another-safe-model")),
            (
                "owner_policy_reconciliation",
                json!(["Reconcile the owner decision."]),
            ),
        ] {
            let mut changed = args.clone();
            changed["change_request"][key] = value;
            assert_ne!(original, operation_id(&[], &changed), "{key}");
        }
        let mut explicit = args.clone();
        explicit["change_request"]["subagents_allowed"] = json!(false);
        explicit["change_request"]["required_validation"]
            .as_array_mut()
            .unwrap()
            .reverse();
        assert_eq!(original, operation_id(&[], &explicit));
        // Repeating a Step is legal and never requires a history lookup.
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &explicit),
            Ok(())
        );
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &explicit),
            Ok(())
        );
    }

    #[tokio::test]
    async fn wrong_binding_and_publication_state_never_create_reviews() {
        for (path, value, code) in [
            ("/number", json!(116), "PR_TARGET_MISMATCH"),
            ("/base/ref", json!("other"), "PR_TARGET_MISMATCH"),
            (
                "/base/repo/full_name",
                json!("other/repo"),
                "PR_TARGET_MISMATCH",
            ),
            (
                "/head/repo/full_name",
                json!("other/repo"),
                "PR_TARGET_MISMATCH",
            ),
            ("/head/sha", json!("b".repeat(40)), "STALE_HEAD"),
            ("/state", json!("closed"), "PR_NOT_OPEN"),
            ("/merged", json!(true), "PR_MERGED"),
            ("/draft", json!(true), "DRAFT_PR_NOT_READY"),
            ("/draft", Value::Null, "PR_STATE_UNAVAILABLE"),
        ] {
            let state = MockState::default();
            let mut pr = live_pr();
            *pr.pointer_mut(path).unwrap() = value;
            *state.pr.lock().unwrap() = Some(pr);
            let (http, url) = client_with_state(true, None, state.clone()).await;
            let result = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":cr_fixture()}),
            )
            .await;
            assert_eq!(
                result.pointer("/result/content/0/text"),
                Some(&json!(code)),
                "{path}"
            );
            assert!(state.reviews.lock().unwrap().is_empty());
        }
        let state = MockState::default();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        for (key, value, code) in [
            ("repository", json!("other/repo"), "REPOSITORY_NOT_ALLOWED"),
            ("pr_number", json!(0), "INVALID_PR_NUMBER"),
            ("expected_head_sha", json!("main"), "INVALID_HEAD_SHA"),
            ("expected_head_sha", Value::Null, "INVALID_HEAD_SHA"),
        ] {
            let mut args = cr_fixture();
            args[key] = value;
            let result = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(result.pointer("/result/content/0/text"), Some(&json!(code)));
        }
        assert!(state.requests.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn duplicate_raw_json_and_oversized_transport_fail_before_github() {
        let state = MockState::default();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let raw = serde_json::to_string(&json!({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"submit_pr_review","arguments":cr_fixture()}})).unwrap();
        for body in [
            raw.replace("\"step\":1", "\"step\":1,\"step\":2"),
            " ".repeat(52_001),
        ] {
            let result = http
                .post(&url)
                .header(mtls_identity::VERIFIED_HEADER, "1")
                .header(mtls_identity::CERT_HEADER, encoded_certificate())
                .header("Content-Type", "application/json")
                .body(body)
                .send()
                .await
                .unwrap();
            assert!(result.status().is_client_error());
        }
        assert!(state.requests.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn returned_wrong_review_body_or_state_is_never_reported_as_executable_success() {
        let args = cr_fixture();
        let payload = json!({"commit_id":HEAD,"event":"REQUEST_CHANGES","body":native_review_body(&[], &args, &operation_id(&[], &args))});
        for (key, value) in [
            ("state", json!("APPROVED")),
            ("body", json!("Unrelated prose")),
        ] {
            let state = MockState::default();
            let mut response = native_review(&payload);
            response[key] = value;
            *state.review_response.lock().unwrap() = Some(response);
            let (http, url) = client_with_state(true, None, state.clone()).await;
            let result = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(
                result.pointer("/result/content/0/text"),
                Some(&json!("REVIEW_CONTRACT_VERIFICATION_FAILED"))
            );
            assert_eq!(state.reviews.lock().unwrap().len(), 1);
            assert!(!state
                .requests
                .lock()
                .unwrap()
                .iter()
                .any(|request| request.ends_with("/check-runs")));
        }
    }

    #[derive(Clone)]
    struct MockState {
        repository: String,
        policy: ReviewPolicy,
        installation_id: String,
        observed_arguments: ObservedArguments,
        requests: Arc<Mutex<Vec<String>>>,
        token_requests: Arc<Mutex<Vec<Value>>>,
        reviews: Arc<Mutex<Vec<Value>>>,
        pr: Arc<Mutex<Option<Value>>>,
        app_identity: Arc<Mutex<Option<Value>>>,
        review_response: Arc<Mutex<Option<Value>>>,
    }

    impl Default for MockState {
        fn default() -> Self {
            Self {
                repository: TEST_REPOSITORY.into(),
                policy: test_policy(),
                installation_id: "1".into(),
                observed_arguments: Default::default(),
                requests: Default::default(),
                token_requests: Default::default(),
                reviews: Default::default(),
                pr: Default::default(),
                app_identity: Default::default(),
                review_response: Default::default(),
            }
        }
    }

    fn live_pr() -> Value {
        live_pr_for_repository(TEST_REPOSITORY)
    }

    fn live_pr_for_repository(repository: &str) -> Value {
        json!({"number":25,"state":"open","draft":false,"merged":false,"labels":[{"name":"step-1"}],
            "base":{"ref":"main","repo":{"full_name":repository}},
            "head":{"sha":HEAD,"repo":{"full_name":repository}},"user":{"login":"author"}})
    }

    fn native_review(payload: &Value) -> Value {
        json!({"id":1,"html_url":"https://example/reviews/1","commit_id":payload["commit_id"],
            "body":payload["body"],"state":if payload["event"] == "APPROVE" { "APPROVED" } else { "CHANGES_REQUESTED" },
            "user":{"login":"example-reviewer[bot]"}})
    }

    fn encoded_certificate() -> String {
        let mut ca_params = CertificateParams::new(Vec::new()).expect("CA parameters");
        ca_params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
        ca_params.distinguished_name = DistinguishedName::new();
        ca_params
            .distinguished_name
            .push(DnType::CommonName, "test proxy CA");
        let ca_key = KeyPair::generate().expect("CA key");
        let ca = ca_params.self_signed(&ca_key).expect("CA certificate");
        let mut params = CertificateParams::new(vec!["mtls.prod.connectors.openai.com".into()])
            .expect("certificate parameters");
        params.distinguished_name = DistinguishedName::new();
        params
            .distinguished_name
            .push(DnType::CommonName, "OpenAI connector");
        params.extended_key_usages = vec![ExtendedKeyUsagePurpose::ClientAuth];
        let key = KeyPair::generate().expect("key");
        let cert = params.signed_by(&key, &ca, &ca_key).expect("certificate");
        cert.pem()
            .bytes()
            .map(|byte| match byte {
                b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                    char::from(byte).to_string()
                }
                _ => format!("%{byte:02X}"),
            })
            .collect()
    }

    async fn mock_github(
        State(state): State<MockState>,
        headers: HeaderMap,
        method: Method,
        uri: Uri,
        body: axum::body::Bytes,
    ) -> axum::response::Response {
        state
            .requests
            .lock()
            .unwrap()
            .push(format!("{method} {}", uri.path()));
        if headers.get("user-agent").and_then(|x| x.to_str().ok()) != Some(github::USER_AGENT) {
            return StatusCode::FORBIDDEN.into_response();
        }
        let authorization = headers.get("authorization").and_then(|x| x.to_str().ok());
        let token_path = format!("/app/installations/{}/access_tokens", state.installation_id);
        let app_endpoint = uri.path() == "/app" || uri.path() == token_path;
        let expected = if app_endpoint {
            "Bearer test-jwt"
        } else {
            "Bearer mock-installation-token"
        };
        if authorization != Some(expected) {
            return StatusCode::UNAUTHORIZED.into_response();
        }
        let check_mode = headers
            .get("x-test-check-mode")
            .and_then(|x| x.to_str().ok());
        let check_attempt = headers
            .get("x-test-check-attempt")
            .and_then(|x| x.to_str().ok());
        let repository_prefix = format!("/repos/{}/", state.repository);
        let path = uri
            .path()
            .strip_prefix(&repository_prefix)
            .unwrap_or(uri.path());
        if method == Method::POST && path == "check-runs" {
            if check_mode == Some("transient") && check_attempt == Some("1") {
                return StatusCode::SERVICE_UNAVAILABLE.into_response();
            }
            if check_mode == Some("uncertain") && check_attempt == Some("1") {
                return Json(json!({"id":2,"html_url":"https://example/check-runs/2"}))
                    .into_response();
            }
        }
        let value = match (method, path) {
            (Method::POST, value) if value == token_path => {
                let payload: Value = serde_json::from_slice(&body).unwrap();
                state.token_requests.lock().unwrap().push(payload.clone());
                let (_, name) = state.repository.split_once('/').unwrap();
                if payload["repositories"] != json!([name]) {
                    return StatusCode::FORBIDDEN.into_response();
                }
                json!({"token":"mock-installation-token", "expires_at":"2099-01-01T00:00:00Z"})
            }
            (Method::GET, "pulls/25") => state
                .pr
                .lock()
                .unwrap()
                .clone()
                .unwrap_or_else(|| { let mut pr = live_pr_for_repository(&state.repository); pr["base"]["ref"] = json!(state.policy.base_branch); pr }),
            (Method::GET, "/app") => state.app_identity.lock().unwrap().clone().unwrap_or_else(
                || json!({"slug":state.policy.slug,"id":state.policy.app_id.parse::<u64>().unwrap()}),
            ),
            (Method::GET, "pulls/25/reviews") => json!(state
                .reviews
                .lock()
                .unwrap()
                .iter()
                .map(|payload| { let mut review = native_review(payload); review["user"]["login"] = json!(state.policy.actor); review })
                .collect::<Vec<_>>()),
            (Method::POST, "pulls/25/reviews") => {
                let payload: Value = serde_json::from_slice(&body).unwrap();
                let response = state
                    .review_response
                    .lock()
                    .unwrap()
                    .clone()
                    .unwrap_or_else(|| { let mut review = native_review(&payload); review["user"]["login"] = json!(state.policy.actor); review });
                state.reviews.lock().unwrap().push(payload);
                response
            }
            (Method::GET, "commits/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/check-runs") => {
                json!({"check_runs":[]})
            }
            (Method::POST, "check-runs") => {
                json!({"id":2,"html_url":"https://example/check-runs/2","head_sha":HEAD,"name":state.policy.check_name,"app":{"slug":if check_mode == Some("wrong-app") { "other-app" } else { &state.policy.slug }}})
            }
            _ => return StatusCode::NOT_FOUND.into_response(),
        };
        Json(value).into_response()
    }

    async fn mock_api(state: MockState) -> String {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("github bind");
        let address = listener.local_addr().expect("github address");
        tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().fallback(any(mock_github)).with_state(state),
            )
            .await
            .expect("github serve");
        });
        format!("http://{address}")
    }

    async fn client_with_check_mode(
        enabled: bool,
        check_mode: Option<&str>,
    ) -> (reqwest::Client, String) {
        client_with_check_mode_and_approval(enabled, check_mode).await
    }

    async fn client_with_check_mode_and_approval(
        enabled: bool,
        check_mode: Option<&str>,
    ) -> (reqwest::Client, String) {
        client_with_state(enabled, check_mode, MockState::default()).await
    }

    async fn client_with_state(
        enabled: bool,
        check_mode: Option<&str>,
        state: MockState,
    ) -> (reqwest::Client, String) {
        client_with_repository(enabled, check_mode, state, TEST_REPOSITORY).await
    }

    async fn client_with_repository(
        enabled: bool,
        check_mode: Option<&str>,
        state: MockState,
        repository: &str,
    ) -> (reqwest::Client, String) {
        let observed_arguments = state.observed_arguments.clone();
        let policy = state.policy.clone();
        let installation_id = state.installation_id.clone();
        let github = github::Github::mock_api_with_check_mode(mock_api(state).await, check_mode)
            .with_test_installation(installation_id);
        let app = router(App {
            policy,
            repository: repository.into(),
            observed_arguments,
            enabled,
            store: Arc::new(Mutex::new(store::Store::open(":memory:").expect("store"))),
            github,
            trusted_client_ca: Arc::new(Vec::new()),
        });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("bind");
        let address = listener.local_addr().expect("address");
        tokio::spawn(async move {
            axum::serve(listener, app).await.expect("serve");
        });
        (reqwest::Client::new(), format!("http://{address}/mcp"))
    }

    async fn rpc(
        client: &reqwest::Client,
        url: &str,
        id: i64,
        method: &str,
        params: Value,
    ) -> Value {
        client
            .post(url)
            .header(mtls_identity::VERIFIED_HEADER, "1")
            .header(mtls_identity::CERT_HEADER, encoded_certificate())
            .header("Accept", "application/json, text/event-stream")
            .json(&json!({"jsonrpc":"2.0","id":id,"method":method,"params":params}))
            .send()
            .await
            .expect("request")
            .json()
            .await
            .expect("json")
    }

    #[test]
    fn exposes_exactly_two_tools_and_only_accepted_actions() {
        let listed = tools(&[], TEST_REPOSITORY);
        let names = listed
            .as_array()
            .unwrap()
            .iter()
            .map(|tool| tool["name"].as_str().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(names, vec!["check_pr_review_target", "submit_pr_review"]);
        assert_eq!(
            valid_input(
                &[],
                TEST_REPOSITORY,
                "submit_pr_review",
                &base_args("APPROVE")
            ),
            Ok(())
        );
        assert_eq!(
            valid_input(
                &[],
                TEST_REPOSITORY,
                "submit_pr_review",
                &base_args("REQUEST_CHANGES")
            ),
            Ok(())
        );
        assert_eq!(
            valid_input(
                &[],
                TEST_REPOSITORY,
                "submit_pr_review",
                &base_args("COMMENT")
            ),
            Err("ACTION_NOT_ALLOWED")
        );
    }

    #[test]
    fn connected_reviewer_shape_requires_no_unavailable_caller_metadata() {
        let missing = base_args("APPROVE");
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &missing),
            Ok(())
        );
        let mut extra = base_args("REQUEST_CHANGES");
        extra["human_approval"] = json!(true);
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &extra),
            Err("INVALID_PAYLOAD")
        );
    }

    #[test]
    fn current_part_identifier_accepts_alphanumeric_part_7a() {
        assert!(valid_task_identifier("42A"));
        assert!(valid_part_identifier("7A"));
        assert!(valid_part_identifier("7B"));
        assert!(!valid_part_identifier("0"));
    }

    #[test]
    fn reviewer_runtime_config_binds_the_deployable_service_and_artifact_identity() {
        let path = std::env::temp_dir().join(format!(
            "reviewer-config-{}-{}.json",
            std::process::id(),
            HEAD
        ));
        fs::write(&path, json!({
            "repository": "example-org/sample-project",
            "artifact": {"commit": HEAD, "sha256": "b".repeat(64)},
            "service": {"name": "reviewer-mcp", "bind_mode": "private_gateway", "bind_address": "172.18.0.1", "bind_network": "example-network", "gateway_validated": true, "bind_port": 8787, "mount_path": "/mcp"},
            "baseBranch":"main", "reviewCheckName":"chatgpt-review", "writerActor":"example-writer[bot]",
            "githubApp": {"slug": "example-reviewer", "appId": "102", "installationId": "202", "expectedActor": "example-reviewer[bot]"}
        }).to_string()).expect("write config");
        assert_eq!(
            load_runtime_config(path.to_str().unwrap()),
            RuntimeConfig {
                policy: test_policy(),
                repository: TEST_REPOSITORY.into(),
                host: "172.18.0.1".into(),
                port: 8787,
                mount: "/mcp".into(),
                bind_mode: "private_gateway".into(),
                bind_network: "example-network".into(),
                gateway_validated: true,
            }
        );
        fs::remove_file(path).expect("remove config");
    }

    #[test]
    fn reviewer_runtime_config_rejects_placeholder_artifact_identity() {
        let path = std::env::temp_dir().join(format!(
            "reviewer-placeholder-config-{}-{}.json",
            std::process::id(),
            HEAD
        ));
        fs::write(&path, json!({
            "repository": "example-org/sample-project",
            "artifact": {"commit": "UNAVAILABLE_UNTIL_RELEASE_STAGING", "sha256": "UNAVAILABLE_UNTIL_RELEASE_STAGING"},
            "service": {"name": "reviewer-mcp", "bind_mode": "private_gateway", "bind_address": "172.18.0.1", "bind_network": "example-network", "gateway_validated": true, "bind_port": 8787, "mount_path": "/mcp"},
            "baseBranch":"main", "reviewCheckName":"chatgpt-review", "writerActor":"example-writer[bot]",
            "githubApp": {"slug": "example-reviewer", "appId": "102", "installationId": "202", "expectedActor": "example-reviewer[bot]"}
        }).to_string()).expect("write config");
        let result = std::panic::catch_unwind(|| load_runtime_config(path.to_str().unwrap()));
        assert!(result.is_err());
        fs::remove_file(path).expect("remove config");
    }

    fn rendered_runtime_config(repository: &str) -> String {
        let template_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../examples/ansible/reviewer-mcp.json.j2");
        let template_source =
            fs::read_to_string(&template_path).expect("managed Reviewer template");
        let mut environment = Environment::new();
        environment.add_filter("bool", |value: bool| value.to_string());
        environment.add_filter("to_json", |value: String| {
            serde_json::to_string(&value).unwrap()
        });
        let template = environment
            .template_from_str(&template_source)
            .expect("managed Reviewer Jinja template");
        template
            .render(context! {
                relay_github_repository => repository,
                relay_release_commit => HEAD,
                relay_release_sha256 => "b".repeat(64),
                relay_reviewer_exec_start => "/opt/relay-example/current/bin/reviewer-mcp-http --config /etc/relay-example/reviewer-mcp.json",
                relay_reviewer_bind_mode => "private_gateway",
                relay_reviewer_bind_address => "172.18.0.1",
                relay_reviewer_bind_network => "example-network",
                relay_reviewer_gateway_validated => true,
                relay_evidence_root => "/var/lib/relay-example/evidence",
                relay_github_base_branch => "main",
                relay_review_check_name => "chatgpt-review",
                relay_writer_expected_actor => "example-writer[bot]",
                relay_reviewer_app_slug => "example-reviewer",
                relay_reviewer_app_id => "102",
                relay_reviewer_app_installation_id => "202",
                relay_reviewer_expected_actor => "example-reviewer[bot]",
            })
            .expect("render managed Reviewer Jinja template")
    }

    #[test]
    fn composed_managed_template_is_accepted_by_the_runtime_contract() {
        let rendered = rendered_runtime_config(TEST_REPOSITORY);
        assert!(!rendered.contains("{{"));
        assert!(!rendered.contains("UNAVAILABLE_UNTIL_RELEASE_STAGING"));

        let path = std::env::temp_dir().join(format!(
            "reviewer-managed-template-config-{}-{}.json",
            std::process::id(),
            HEAD
        ));
        fs::write(&path, &rendered).expect("write rendered managed config");
        let runtime_args = Args {
            config: path.to_str().unwrap().to_string(),
        };
        let loaded = effective_runtime_config(&runtime_args);
        validate_effective_runtime_config(&loaded);
        assert_eq!(
            loaded,
            RuntimeConfig {
                policy: test_policy(),
                repository: TEST_REPOSITORY.into(),
                host: "172.18.0.1".into(),
                port: 8787,
                mount: "/mcp".into(),
                bind_mode: "private_gateway".into(),
                bind_network: "example-network".into(),
                gateway_validated: true,
            }
        );

        let mut placeholder = serde_json::from_str::<Value>(&rendered).expect("rendered JSON");
        placeholder["artifact"]["commit"] =
            Value::String("UNAVAILABLE_UNTIL_RELEASE_STAGING".into());
        fs::write(&path, placeholder.to_string()).expect("write placeholder config");
        assert!(std::panic::catch_unwind(|| {
            let loaded = effective_runtime_config(&runtime_args);
            validate_effective_runtime_config(&loaded);
        })
        .is_err());

        let mut unvalidated = serde_json::from_str::<Value>(&rendered).expect("rendered JSON");
        unvalidated["service"]["gateway_validated"] = Value::Bool(false);
        fs::write(&path, unvalidated.to_string()).expect("write unvalidated config");
        assert!(std::panic::catch_unwind(|| {
            let loaded = effective_runtime_config(&runtime_args);
            validate_effective_runtime_config(&loaded);
        })
        .is_err());

        fs::remove_file(path).expect("remove rendered managed config");
    }

    #[test]
    fn managed_ansible_runtime_config_accepts_the_validated_private_gateway() {
        let path = std::env::temp_dir().join(format!(
            "reviewer-managed-private-config-{}-{}.json",
            std::process::id(),
            HEAD
        ));
        fs::write(&path, json!({
            "schemaVersion": "1.0",
            "repository": "example-org/sample-project",
            "artifact": {"commit": HEAD, "sha256": "b".repeat(64)},
            "service": {"name": "reviewer-mcp", "execBoundary": "/opt/relay-example/current/bin/reviewer-mcp-http --config /etc/relay-example/reviewer-mcp.json", "bind_mode": "private_gateway", "bind_address": "172.18.0.1", "bind_network": "example-network", "gateway_validated": true, "bind_port": 8787, "mount_path": "/mcp"},
            "baseBranch":"main", "reviewCheckName":"chatgpt-review", "writerActor":"example-writer[bot]",
            "githubApp": {"slug": "example-reviewer", "appId": "102", "installationId": "202", "expectedActor": "example-reviewer[bot]"}
        }).to_string()).expect("write config");
        assert_eq!(load_runtime_config(path.to_str().unwrap()).port, 8787);
        let mut retired_transport =
            serde_json::from_str::<Value>(&fs::read_to_string(&path).expect("read config"))
                .expect("parse config");
        retired_transport["service"]["bind_socket"] =
            Value::String("/run/relay-example-reviewer/mcp.sock".to_string());
        fs::write(&path, retired_transport.to_string()).expect("write retired transport config");
        assert!(std::panic::catch_unwind(|| load_runtime_config(path.to_str().unwrap())).is_err());
        fs::remove_file(path).expect("remove config");
    }

    #[test]
    fn reviewer_bind_contract_accepts_tcp_only_loopback_and_validated_private_gateway() {
        validate_reviewer_bind("127.0.0.1", "a_only_loopback", "", false);
        validate_reviewer_bind("172.18.0.1", "nexus_gateway", "example-network", true);
        validate_reviewer_bind("10.55.0.1", "private_gateway", "canary-bridge", true);
        for (host, mode, network, validated) in [
            ("0.0.0.0", "nexus_gateway", "example-network", true),
            ("192.0.2.10", "nexus_gateway", "other", true),
            ("172.18.0.1", "nexus_gateway", "example-network", false),
            ("127.0.0.1", "nexus_gateway", "example-network", true),
            ("172.18.0.1", "a_only_loopback", "", false),
            ("", "a_only_unix_socket", "", false),
        ] {
            let result =
                std::panic::catch_unwind(|| validate_reviewer_bind(host, mode, network, validated));
            assert!(result.is_err(), "unexpectedly accepted {host} {mode}");
        }
    }

    #[test]
    fn missing_config_is_rejected_instead_of_using_a_transport_default() {
        assert!(Args::try_parse_from(["reviewer-mcp"]).is_err());
    }

    #[test]
    fn connected_payload_rejects_removed_metadata_fields() {
        let mut duplicate_heading = base_args("REQUEST_CHANGES");
        duplicate_heading["review_thread_name"] = json!(REMOVED_REVIEW_THREAD);
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &duplicate_heading),
            Err("INVALID_PAYLOAD")
        );
    }

    #[test]
    fn rejects_ambiguous_non_normalized_and_control_payloads() {
        let mut extra = base_args("APPROVE");
        extra
            .as_object_mut()
            .unwrap()
            .insert("extra".into(), json!(true));
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &extra),
            Err("INVALID_PAYLOAD")
        );
        let mut finding = base_args("APPROVE");
        finding["structured_findings"] =
            json!([{"id":" ","severity":"major","title":"title","detail":"detail","evidence":[]}]);
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &finding),
            Err("INVALID_FINDINGS")
        );
        finding["structured_findings"] = json!([{"id":"F1","severity":"major","title":"e\u{301}","detail":"detail","evidence":[]}]);
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &finding),
            Err("INVALID_FINDINGS")
        );
        finding["structured_findings"] = json!([{"id":"F1","severity":"major","title":"title","detail":"detail","evidence":["bad\u{0000}"]}]);
        assert_eq!(
            valid_input(&[], TEST_REPOSITORY, "submit_pr_review", &finding),
            Err("INVALID_FINDINGS")
        );
    }

    #[test]
    fn operation_identity_includes_findings_and_route_is_canonical() {
        let first = base_args("REQUEST_CHANGES");
        let mut second = first.clone();
        second["change_request"]["findings"][0]["problem"] = json!("Changed");
        assert_ne!(operation_id(&[], &first), operation_id(&[], &second));
        assert!(Args::try_parse_from(["reviewer-mcp"]).is_err());
        assert!(Args::try_parse_from([
            "reviewer-mcp",
            "--config",
            "/etc/relay-example/reviewer-mcp.json"
        ])
        .is_ok());
    }

    #[test]
    fn draft_closed_merged_stale_and_malformed_targets_are_distinguishable() {
        let head = json!(HEAD);
        let valid = |state, draft, merged, actual| json!({"state":state,"draft":draft,"merged":merged,"head":{"sha":actual}});
        assert_eq!(
            publication_rejection(&valid("open", true, false, HEAD), &head),
            Some("DRAFT_PR_NOT_READY")
        );
        assert_eq!(
            publication_rejection(&valid("closed", false, false, HEAD), &head),
            Some("PR_NOT_OPEN")
        );
        assert_eq!(
            publication_rejection(&valid("closed", false, true, HEAD), &head),
            Some("PR_MERGED")
        );
        let stale = "b".repeat(40);
        assert_eq!(
            publication_rejection(&valid("open", false, false, &stale), &head),
            Some("STALE_HEAD")
        );
        assert_eq!(
            publication_rejection(&valid("open", false, false, HEAD), &head),
            None
        );
        assert_eq!(
            publication_rejection(&json!({"state":"open","head":{"sha":HEAD}}), &head),
            Some("PR_STATE_UNAVAILABLE")
        );
    }

    #[tokio::test]
    async fn http_mcp_security_contract_covers_live_lookup_duplicates_and_disable() {
        let (http, url) = client_with_check_mode(true, None).await;
        let init = rpc(&http, &url, 1, "initialize", json!({})).await;
        assert_eq!(
            init.pointer("/result/protocolVersion"),
            Some(&json!("2025-06-18"))
        );
        let listed = rpc(&http, &url, 2, "tools/list", json!({})).await;
        assert_eq!(
            listed
                .pointer("/result/tools")
                .and_then(Value::as_array)
                .unwrap()
                .len(),
            2
        );
        let checked = rpc(&http, &url, 3, "tools/call", json!({"name":"check_pr_review_target","arguments":{"repository":"example-org/sample-project","pr_number":25,"expected_head_sha":HEAD}})).await;
        assert_eq!(
            checked.pointer("/result/structuredContent/ready_for_review"),
            Some(&json!(true))
        );
        let args = http_args(json!([]));
        let published = rpc(
            &http,
            &url,
            4,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(
            published.pointer("/result/content/0/text"),
            Some(&json!("PUBLISHED"))
        );
        let duplicate = rpc(
            &http,
            &url,
            5,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(
            duplicate.pointer("/result/content/0/text"),
            Some(&json!("DUPLICATE_SUPPRESSED"))
        );
        let (disabled_http, disabled_url) = client_with_check_mode(false, None).await;
        let disabled = rpc(
            &disabled_http,
            &disabled_url,
            6,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(
            disabled.pointer("/result/content/0/text"),
            Some(&json!("RELAY_DISABLED"))
        );
    }

    #[tokio::test]
    async fn connected_reviewer_shape_does_not_require_caller_approval() {
        let (http, url) = client_with_check_mode(true, None).await;
        let permitted = rpc(
            &http,
            &url,
            10,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":http_args(json!([]))}),
        )
        .await;
        assert_eq!(
            permitted.pointer("/result/content/0/text"),
            Some(&json!("PUBLISHED"))
        );
    }

    #[tokio::test]
    async fn check_publication_failure_and_uncertain_response_recover_without_duplicate_review() {
        for mode in ["transient", "uncertain"] {
            let (http, url) = client_with_check_mode(true, Some(mode)).await;
            let args = http_args(json!([]));
            let first = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            let expected = if mode == "transient" {
                "REVIEW_PUBLISHED_CHECK_FAILED"
            } else {
                "CHECK_VERIFICATION_FAILED"
            };
            assert_eq!(
                first.pointer("/result/content/0/text"),
                Some(&json!(expected))
            );
            let second = rpc(
                &http,
                &url,
                2,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(
                second.pointer("/result/content/0/text"),
                Some(&json!("CHECK_RECOVERED"))
            );
        }
    }

    #[tokio::test]
    async fn check_recovery_rejects_a_check_from_the_wrong_github_app() {
        let (http, url) = client_with_check_mode(true, Some("wrong-app")).await;
        let args = http_args(json!([]));
        let response = rpc(
            &http,
            &url,
            1,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(
            response.pointer("/result/content/0/text"),
            Some(&json!("CHECK_VERIFICATION_FAILED"))
        );
    }
}
