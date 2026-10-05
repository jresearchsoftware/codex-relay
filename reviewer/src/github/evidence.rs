//! Fixed, read-only GitHub evidence acquisition. Response URLs, cursors and
//! caller-selected endpoints are never followed. This is observation, not review.
use super::{Github, USER_AGENT};
use reqwest::{redirect::Policy, Client, Response};
use serde_json::{json, Value};
use std::time::{Duration, Instant};

const RESPONSE_BYTES: usize = 256 * 1024;
const TOTAL_BYTES: usize = 2 * 1024 * 1024;
const REQUESTS: usize = 40;
const PAGE_SIZE: usize = 25;
const PAGES: usize = 3;
const ITEMS: usize = PAGE_SIZE * PAGES;
const ANNOTATIONS: usize = 250;
const TIMEOUT: Duration = Duration::from_secs(30);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(5);

pub fn output_schema() -> Value {
    let nullable_text = |limit| json!({"type": ["string", "null"], "maxLength": limit});
    let id = json!({"type": ["integer", "null"], "minimum": 1});
    let sha = json!({"type": "string", "pattern": "^[0-9a-f]{40}$"});
    let availability = json!({"type": "string", "enum": ["available", "absent", "unavailable", "permission_denied", "truncated"]});
    let annotation = json!({"type": "object", "additionalProperties": false,
        "required": ["level", "path", "start_line", "end_line", "title", "message", "text_redacted_or_truncated"],
        "properties": {"level": {"enum": ["notice", "warning", "failure"]}, "path": nullable_text(256),
            "start_line": id, "end_line": id, "title": nullable_text(256), "message": nullable_text(2048),
            "text_redacted_or_truncated": {"type": "boolean"}}});
    let annotations = json!({"type": "object", "additionalProperties": false,
        "required": ["source", "api_path", "availability", "reason", "pages_observed", "items"],
        "properties": {"source": {"const": "github_check_run_annotations"}, "api_path": {"type": "string", "maxLength": 512},
            "availability": availability, "reason": nullable_text(100), "pages_observed": {"type": "integer", "minimum": 0, "maximum": PAGES},
            "items": {"type": "array", "maxItems": ITEMS, "items": annotation}}});
    let suite = json!({"type": "object", "additionalProperties": false,
        "required": ["check_suite_id", "head_sha", "status", "conclusion", "app_id"],
        "properties": {"check_suite_id": id, "head_sha": sha, "status": nullable_text(32), "conclusion": nullable_text(32), "app_id": id}});
    let run = json!({"type": "object", "additionalProperties": false,
        "required": ["run_id", "check_suite_id", "head_sha", "reviewed_head_sha", "association", "outcome_comment_id", "issue_number", "api_path", "run_attempt", "workflow_id", "name", "event", "status", "conclusion", "native_url", "text_redacted_or_truncated"],
        "properties": {"run_id": id, "check_suite_id": id, "head_sha": sha, "reviewed_head_sha": sha,
            "association": {"enum": ["exact_head", "writer_exact_head_outcome"]}, "outcome_comment_id": id, "issue_number": id,
            "api_path": {"type": "string", "maxLength": 512}, "run_attempt": id, "workflow_id": id,
            "name": nullable_text(256), "event": nullable_text(32), "status": nullable_text(32), "conclusion": nullable_text(32),
            "native_url": {"type": "string", "maxLength": 256}, "text_redacted_or_truncated": {"type": "boolean"}}});
    let check = json!({"type": "object", "additionalProperties": false,
        "required": ["check_run_id", "check_suite_id", "workflow_run_ids", "head_sha", "reviewed_head_sha", "association", "outcome_comment_id", "name", "app_id", "app_slug", "status", "conclusion", "native_url", "text_redacted_or_truncated", "annotations"],
        "properties": {"check_run_id": id, "check_suite_id": id, "workflow_run_ids": {"type": "array", "maxItems": ITEMS, "items": id},
            "head_sha": sha, "reviewed_head_sha": sha, "association": {"enum": ["exact_head", "writer_exact_head_outcome"]}, "outcome_comment_id": id,
            "name": nullable_text(256), "app_id": id, "app_slug": nullable_text(100), "status": nullable_text(32), "conclusion": nullable_text(32),
            "native_url": {"type": "string", "maxLength": 256}, "text_redacted_or_truncated": {"type": "boolean"}, "annotations": annotations}});
    let outcome = json!({"type": "object", "additionalProperties": false,
        "required": ["comment_id", "issue_number", "head_sha", "actor", "native_url", "workflow_run_id", "warning_summaries", "text_redacted_or_truncated"],
        "properties": {"comment_id": id, "issue_number": id, "head_sha": sha, "actor": {"type": "string", "maxLength": 100},
            "native_url": {"type": "string", "maxLength": 256}, "workflow_run_id": id,
            "warning_summaries": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 2048}},
            "text_redacted_or_truncated": {"type": "boolean"}}});
    let binding = json!({"type": "object", "additionalProperties": false,
        "required": ["availability", "binding_verified"],
        "properties": {"availability": availability, "reason": {"type": "string", "maxLength": 100}, "binding_verified": {"type": "boolean"}}});
    json!({"type": "object", "additionalProperties": false,
        "required": ["repository", "pr_number", "expected_head_sha", "required_surfaces_complete", "warning_observation", "surfaces", "limits", "target"],
        "properties": {"repository": {"type": "string", "maxLength": 140}, "pr_number": {"type": "integer", "minimum": 1}, "expected_head_sha": sha,
            "required_surfaces_complete": {"type": "boolean"}, "warning_observation": {"enum": ["observed", "none_observed", "unknown"]},
            "observed_check_annotation_warnings": {"type": "integer", "minimum": 0, "maximum": ANNOTATIONS},
            "requests_observed": {"type": "integer", "minimum": 0, "maximum": REQUESTS},
            "response_byte_budget_used": {"type": "integer", "minimum": 0, "maximum": TOTAL_BYTES},
            "target": {"type": "object", "additionalProperties": false, "properties": {"source": {"const": "github_pull_request"},
                "api_path": {"type": "string", "maxLength": 512}, "availability": availability, "reason": {"type": "string", "maxLength": 100},
                "binding_verified": {"type": "boolean"}, "head_sha": sha, "initial_binding_verified": {"type": "boolean"}, "final_binding": binding}},
            "limits": {"type": "object", "additionalProperties": false, "required": ["response_bytes", "total_bytes", "requests", "pages_per_surface", "items_per_surface", "annotations_total", "timeout_seconds"],
                "properties": {"response_bytes": {"const": RESPONSE_BYTES}, "total_bytes": {"const": TOTAL_BYTES}, "requests": {"const": REQUESTS},
                    "pages_per_surface": {"const": PAGES}, "items_per_surface": {"const": ITEMS}, "annotations_total": {"const": ANNOTATIONS}, "timeout_seconds": {"const": TIMEOUT.as_secs()}}},
            "surfaces": {"type": "array", "maxItems": 6, "items": {"type": "object", "additionalProperties": false,
                "required": ["source", "availability", "items"], "properties": {
                    "source": {"enum": ["github_check_suites", "github_actions_workflow_runs", "github_check_runs", "github_workflow_run_platform_annotations", "github_relay_execution_outcomes", "github_relay_execution_workflow_runs"]},
                    "api_path": {"type": "string", "maxLength": 512}, "availability": availability, "reason": nullable_text(100),
                    "pages_observed": {"type": "integer", "minimum": 0, "maximum": PAGES},
                    "items": {"type": "array", "maxItems": ITEMS, "items": {"anyOf": [suite, run, check, outcome]}},
                    "native_urls": {"type": "array", "maxItems": ITEMS * 2, "items": {"type": "string", "maxLength": 256}},
                    "additional_api_paths": {"type": "array", "maxItems": ITEMS, "items": {"type": "string", "maxLength": 512}},
                    "required_for_completeness": {"type": "boolean"},
                    "explanation": {"type": "string", "maxLength": 512}}}}}})
}

#[derive(Clone, Copy)]
struct Failure {
    availability: &'static str,
    reason: &'static str,
}
impl Failure {
    fn unavailable(reason: &'static str) -> Self {
        Self {
            availability: "unavailable",
            reason,
        }
    }
    fn truncated(reason: &'static str) -> Self {
        Self {
            availability: "truncated",
            reason,
        }
    }
}

fn http_failure(status: u16) -> Failure {
    match status {
        401 | 403 => Failure {
            availability: "permission_denied",
            reason: "GITHUB_PERMISSION_DENIED",
        },
        // GitHub also uses 404 for hidden resources; it is never absence proof.
        404 => Failure::unavailable("GITHUB_NOT_FOUND_OR_NOT_VISIBLE"),
        429 => Failure::unavailable("GITHUB_RATE_LIMITED"),
        300..=399 => Failure::unavailable("GITHUB_REDIRECT_REJECTED"),
        _ => Failure::unavailable("GITHUB_REQUEST_FAILED"),
    }
}

async fn bounded_body(mut response: Response, limit: usize) -> Result<Vec<u8>, Failure> {
    if response
        .content_length()
        .is_some_and(|size| size > limit as u64)
    {
        return Err(Failure::truncated("GITHUB_RESPONSE_BYTE_LIMIT"));
    }
    let mut body = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| Failure::unavailable("GITHUB_RESPONSE_READ_FAILED"))?
    {
        if chunk.len() > limit.saturating_sub(body.len()) {
            return Err(Failure::truncated("GITHUB_RESPONSE_BYTE_LIMIT"));
        }
        body.extend_from_slice(&chunk);
    }
    Ok(body)
}

struct ReadSession<'a> {
    client: Client,
    api: &'a str,
    token: String,
    jwt: String,
    requests: usize,
    bytes: usize,
    started: Instant,
}
impl ReadSession<'_> {
    async fn get(&mut self, path: &str, final_binding: bool) -> Result<(Value, bool), Failure> {
        // Reserve one response/request for the live target recheck.
        let request_limit = REQUESTS - usize::from(!final_binding);
        let byte_limit = TOTAL_BYTES - if final_binding { 0 } else { RESPONSE_BYTES };
        if self.requests >= request_limit {
            return Err(Failure::truncated("GITHUB_REQUEST_LIMIT"));
        }
        if self.bytes >= byte_limit {
            return Err(Failure::truncated("GITHUB_TOTAL_BYTE_LIMIT"));
        }
        let remaining = TIMEOUT.saturating_sub(self.started.elapsed());
        if remaining.is_zero() {
            return Err(Failure::unavailable("GITHUB_EVIDENCE_TIMEOUT"));
        }
        self.requests += 1;
        let response = self
            .client
            .get(format!("{}{path}", self.api))
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .bearer_auth(&self.token)
            .timeout(remaining.min(REQUEST_TIMEOUT))
            .send()
            .await
            .map_err(|_| Failure::unavailable("GITHUB_REQUEST_FAILED"))?;
        if !response.status().is_success() {
            return Err(http_failure(response.status().as_u16()));
        }
        let next = response
            .headers()
            .get("link")
            .and_then(|value| value.to_str().ok())
            .is_some_and(|value| value.contains("rel=\"next\""));
        let allowance = RESPONSE_BYTES.min(byte_limit - self.bytes);
        let body = match bounded_body(response, allowance).await {
            Ok(body) => body,
            Err(failure) => {
                // Conservatively charge the complete allowance on a failed
                // bounded read; repeated oversized/partial bodies cannot evade
                // the aggregate transfer budget.
                self.bytes += allowance;
                return Err(failure);
            }
        };
        self.bytes += body.len();
        let value = serde_json::from_slice(&body)
            .map_err(|_| Failure::unavailable("GITHUB_RESPONSE_INVALID"))?;
        Ok((value, next))
    }

    async fn list(&mut self, path: &str, key: Option<&str>, max_items: usize) -> Listing {
        self.list_pages(path, key, max_items, PAGES).await
    }

    async fn list_pages(
        &mut self,
        path: &str,
        key: Option<&str>,
        max_items: usize,
        pages: usize,
    ) -> Listing {
        let mut listing = Listing::new(path);
        if pages == 0 || max_items == 0 {
            listing.fail(Failure::truncated("GITHUB_ITEM_LIMIT"));
            return listing;
        }
        for page in 1..=pages {
            let separator = if path.contains('?') { '&' } else { '?' };
            let page_path = format!("{path}{separator}per_page={PAGE_SIZE}&page={page}");
            let (payload, next) = match self.get(&page_path, false).await {
                Ok(response) => response,
                Err(failure) => {
                    listing.fail(failure);
                    return listing;
                }
            };
            listing.pages += 1;
            let items = match key {
                Some(key) => payload.get(key).and_then(Value::as_array),
                None => payload.as_array(),
            };
            let Some(items) = items else {
                listing.fail(Failure::unavailable("GITHUB_RESPONSE_INVALID"));
                return listing;
            };
            let total = if key.is_some() {
                payload.get("total_count").and_then(Value::as_u64)
            } else {
                None
            };
            if key.is_some() && total.is_none() {
                listing.fail(Failure::unavailable("GITHUB_RESPONSE_INVALID"));
                return listing;
            }
            let count = items.len();
            let remaining = max_items.saturating_sub(listing.items.len());
            listing.items.extend(items.iter().take(remaining).cloned());
            if count > remaining || count > PAGE_SIZE {
                listing.fail(Failure::truncated("GITHUB_ITEM_LIMIT"));
                return listing;
            }
            let observed = listing.items.len() as u64;
            if total.is_some_and(|total| total < observed) {
                listing.fail(Failure::unavailable("GITHUB_RESPONSE_INVALID"));
                return listing;
            }
            let more = next
                || total.is_some_and(|total| total > observed)
                || (total.is_none() && count == PAGE_SIZE);
            if !more {
                listing.availability = if listing.items.is_empty() {
                    "absent"
                } else {
                    "available"
                };
                return listing;
            }
            if count == 0 {
                listing.fail(Failure::unavailable("GITHUB_PAGINATION_INCONSISTENT"));
                return listing;
            }
            if page == pages || listing.items.len() == max_items {
                listing.fail(Failure::truncated("GITHUB_PAGINATION_LIMIT"));
                return listing;
            }
        }
        listing
    }
}

struct Listing {
    path: String,
    availability: &'static str,
    reason: Option<&'static str>,
    pages: usize,
    items: Vec<Value>,
}
impl Listing {
    fn new(path: &str) -> Self {
        Self {
            path: path.into(),
            availability: "unavailable",
            reason: None,
            pages: 0,
            items: vec![],
        }
    }
    fn fail(&mut self, failure: Failure) {
        self.availability = failure.availability;
        self.reason = Some(failure.reason);
    }
    fn rendered(&self, source: &str, items: &[Value]) -> Value {
        json!({"source": source, "api_path": self.path, "availability": self.availability,
            "reason": self.reason, "pages_observed": self.pages, "items": items})
    }
}

// Fields are allowlisted. Credentials, raw_details, logs, artifacts, arbitrary
// response URLs and protected diagnostic content are never returned.
fn text(value: Option<&Value>, limit: usize, altered: &mut bool) -> Value {
    let Some(value) = value.and_then(Value::as_str) else {
        return Value::Null;
    };
    let lower = value.to_ascii_lowercase();
    let sensitive = [
        concat!("gh", "p_"),
        concat!("gh", "o_"),
        concat!("gh", "u_"),
        concat!("gh", "s_"),
        concat!("gh", "r_"),
        concat!("github", "_pat_"),
        concat!("sk", "-"),
        concat!("AK", "IA"),
        "private key",
        "private_key",
        "authorization:",
        "bearer ",
        "password=",
        "token=",
        "secret=",
        "credential=",
        "/etc/",
        "/var/lib/",
        "/run/",
        "/home/",
        "protected diagnostic",
    ]
    .iter()
    .any(|marker| lower.contains(&marker.to_ascii_lowercase()));
    if sensitive {
        *altered = true;
        return json!("[REDACTED_PROTECTED_CONTENT]");
    }
    let mut result = String::new();
    for character in value.chars() {
        if character.is_control() && !matches!(character, '\n' | '\t') {
            *altered = true;
            continue;
        }
        if result.len() + character.len_utf8() > limit {
            *altered = true;
            break;
        }
        result.push(character);
    }
    json!(result)
}

fn identifier(value: Option<&Value>) -> Option<u64> {
    value.and_then(Value::as_u64).filter(|id| *id > 0)
}

fn redact_exact_credentials(value: &mut Value, secrets: &[&str]) -> bool {
    match value {
        Value::String(text)
            if secrets
                .iter()
                .any(|secret| !secret.is_empty() && text.contains(secret)) =>
        {
            *text = "[REDACTED_PROTECTED_CONTENT]".into();
            true
        }
        Value::Array(items) => items.iter_mut().fold(false, |changed, item| {
            redact_exact_credentials(item, secrets) || changed
        }),
        Value::Object(fields) => {
            let changed = fields.values_mut().fold(false, |changed, item| {
                redact_exact_credentials(item, secrets) || changed
            });
            if changed && fields.contains_key("text_redacted_or_truncated") {
                fields.insert("text_redacted_or_truncated".into(), json!(true));
            }
            changed
        }
        _ => false,
    }
}

fn state(value: Option<&Value>) -> Value {
    value
        .and_then(Value::as_str)
        .filter(|value| {
            value.len() <= 32 && value.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
        })
        .map_or(Value::Null, |value| json!(value))
}

fn complete_source(source: &Value) -> bool {
    matches!(
        source["availability"].as_str(),
        Some("available" | "absent")
    ) && source["items"].as_array().is_some_and(|items| {
        items.iter().all(|item| {
            item["text_redacted_or_truncated"] != true
                && (item.get("annotations").is_none() || complete_source(&item["annotations"]))
        })
    })
}

fn exact_sha(sha: &str) -> bool {
    sha.len() == 40
        && sha
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn project_run(
    run: &Value,
    repository: &str,
    reviewed_sha: &str,
    outcome: Option<(u64, u64, u64)>,
) -> Option<Value> {
    let actual_sha = run.get("head_sha").and_then(Value::as_str)?;
    let id = identifier(run.get("id"))?;
    let suite = identifier(run.get("check_suite_id"))?;
    if !exact_sha(actual_sha)
        || run.pointer("/repository/full_name").and_then(Value::as_str) != Some(repository)
        || outcome.map_or(actual_sha != reviewed_sha, |(_, _, expected_id)| {
            expected_id != id
        })
    {
        return None;
    }
    let mut altered = false;
    Some(
        json!({"run_id": id, "check_suite_id": suite, "head_sha": actual_sha, "reviewed_head_sha": reviewed_sha,
        "association": if outcome.is_some() { "writer_exact_head_outcome" } else { "exact_head" },
        "outcome_comment_id": outcome.map(|(_, comment, _)| comment), "issue_number": outcome.map(|(issue, _, _)| issue),
        "api_path": format!("/repos/{repository}/actions/runs/{id}"),
        "run_attempt": identifier(run.get("run_attempt")), "workflow_id": identifier(run.get("workflow_id")),
        "name": text(run.get("name"), 256, &mut altered), "event": state(run.get("event")),
        "status": state(run.get("status")), "conclusion": state(run.get("conclusion")),
        "native_url": format!("https://github.com/{repository}/actions/runs/{id}"), "text_redacted_or_truncated": altered}),
    )
}

fn verify_pr(pr: &Value, repository: &str, number: i64, sha: &str) -> Result<(), &'static str> {
    if pr.get("number").and_then(Value::as_i64) != Some(number)
        || pr.pointer("/base/repo/full_name").and_then(Value::as_str) != Some(repository)
    {
        return Err("GITHUB_EVIDENCE_TARGET_UNVERIFIED");
    }
    match pr.pointer("/head/sha").and_then(Value::as_str) {
        Some(actual) if actual == sha => Ok(()),
        Some(_) => Err("STALE_HEAD"),
        None => Err("GITHUB_EVIDENCE_TARGET_UNVERIFIED"),
    }
}

impl Github {
    async fn evidence_session(&self, repository: &str) -> Result<ReadSession<'_>, Failure> {
        let started = Instant::now();
        let client = Client::builder()
            .user_agent(USER_AGENT)
            .redirect(Policy::none())
            .timeout(REQUEST_TIMEOUT)
            .build()
            .map_err(|_| Failure::unavailable("GITHUB_CLIENT_UNAVAILABLE"))?;
        let jwt = self.app_jwt().await.map_err(Failure::unavailable)?;
        let installation = {
            #[cfg(test)]
            {
                self.test_installation_id
                    .clone()
                    .or_else(|| std::env::var("GITHUB_APP_INSTALLATION_ID").ok())
            }
            #[cfg(not(test))]
            {
                std::env::var("GITHUB_APP_INSTALLATION_ID").ok()
            }
        }
        .ok_or(Failure::unavailable("GITHUB_AUTH_FAILED"))?;
        // The installation selector is trusted configuration, never caller input.
        if installation.is_empty() || !installation.bytes().all(|b| b.is_ascii_digit()) {
            return Err(Failure::unavailable("GITHUB_AUTH_FAILED"));
        }
        let (_, name) = repository
            .split_once('/')
            .ok_or(Failure::unavailable("GITHUB_AUTH_FAILED"))?;
        let response = client.post(format!("{}/app/installations/{installation}/access_tokens", self.api))
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .bearer_auth(&jwt)
            .json(&json!({"repositories": [name], "permissions": {
                "metadata": "read", "pull_requests": "read", "checks": "read", "actions": "read", "issues": "read"
            }})).send().await.map_err(|_| Failure::unavailable("GITHUB_AUTH_FAILED"))?;
        if !response.status().is_success() {
            return Err(http_failure(response.status().as_u16()));
        }
        let body = bounded_body(response, RESPONSE_BYTES).await?;
        let payload: Value = serde_json::from_slice(&body)
            .map_err(|_| Failure::unavailable("GITHUB_AUTH_FAILED"))?;
        let token = payload
            .get("token")
            .and_then(Value::as_str)
            .filter(|token| !token.is_empty() && token.len() <= 4096)
            .ok_or(Failure::unavailable("GITHUB_AUTH_FAILED"))?
            .to_owned();
        if payload
            .get("expires_at")
            .and_then(Value::as_str)
            .is_none_or(str::is_empty)
        {
            return Err(Failure::unavailable("GITHUB_TOKEN_LIFETIME_UNAVAILABLE"));
        }
        Ok(ReadSession {
            client,
            api: &self.api,
            token,
            jwt,
            requests: 1,
            bytes: body.len(),
            started,
        })
    }

    /// Observe the configured repository's current PR head with explicit gaps.
    /// Passing a different repository fails before any authentication/API request.
    pub async fn review_evidence(
        &self,
        configured_repository: &str,
        repository: &str,
        pr_number: i64,
        sha: &str,
        writer_actor: &str,
    ) -> Result<Value, &'static str> {
        if repository != configured_repository || !crate::valid_repository(configured_repository) {
            return Err("REPOSITORY_NOT_ALLOWED");
        }
        if !(1..=9_007_199_254_740_991).contains(&pr_number) {
            return Err("INVALID_PR_NUMBER");
        }
        if sha.len() != 40
            || !sha
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err("INVALID_HEAD_SHA");
        }
        if writer_actor.is_empty()
            || writer_actor.len() > 100
            || !writer_actor
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-[]".contains(&b))
        {
            return Err("GITHUB_WRITER_IDENTITY_UNAVAILABLE");
        }
        let mut evidence = json!({"repository": repository, "pr_number": pr_number, "expected_head_sha": sha,
            "required_surfaces_complete": false, "warning_observation": "unknown", "surfaces": [],
            "limits": {"response_bytes": RESPONSE_BYTES, "total_bytes": TOTAL_BYTES, "requests": REQUESTS,
                "pages_per_surface": PAGES, "items_per_surface": ITEMS, "annotations_total": ANNOTATIONS, "timeout_seconds": TIMEOUT.as_secs()}});
        let mut session = match self.evidence_session(repository).await {
            Ok(session) => session,
            Err(failure) => {
                evidence["target"] = json!({"availability": failure.availability, "reason": failure.reason, "binding_verified": false});
                return Ok(evidence);
            }
        };
        let pr_path = format!("/repos/{repository}/pulls/{pr_number}");
        let (pr, _) = match session.get(&pr_path, false).await {
            Ok(response) => response,
            Err(failure) => {
                evidence["target"] = json!({"source": "github_pull_request", "api_path": pr_path,
                    "availability": failure.availability, "reason": failure.reason, "binding_verified": false});
                return Ok(evidence);
            }
        };
        verify_pr(&pr, repository, pr_number, sha)?;
        let linked_issue = crate::step_sync::linked_issue(&pr);
        let mut execution_pointers = vec![];
        let mut missing_execution_pointer = false;
        // Writer publishes on the current PR, or on the canonical Issue when
        // no PR exists yet. Inspect both bounded native comment collections.
        let runtime_path = format!("/repos/{repository}/issues/{pr_number}/comments");
        let mut outcomes = Listing::new(&runtime_path);
        let mut targets = vec![pr_number as u64];
        match linked_issue {
            Ok(issue) if issue != pr_number as u64 => targets.push(issue),
            Ok(_) => {}
            Err(reason) => outcomes.fail(Failure::unavailable(reason)),
        }
        let mut runtime_items = vec![];
        let mut additional_outcome_paths = vec![];
        let mut comments_observed = 0;
        for (index, target) in targets.iter().enumerate() {
            let path = format!("/repos/{repository}/issues/{target}/comments");
            if index > 0 {
                additional_outcome_paths.push(path.clone());
            }
            // Reserve a page for every remaining collection. The combined
            // source retains its three-page / 75-comment input/output bound.
            let pages = PAGES.saturating_sub(outcomes.pages + targets.len() - index - 1);
            let current = session
                .list_pages(&path, None, ITEMS - comments_observed, pages)
                .await;
            outcomes.pages += current.pages;
            comments_observed += current.items.len();
            if let Some(reason) = current.reason {
                outcomes.fail(Failure {
                    availability: current.availability,
                    reason,
                });
            }
            for comment in &current.items {
                if comment.pointer("/user/login").and_then(Value::as_str) != Some(writer_actor) {
                    continue;
                }
                let Some(body) = comment.get("body").and_then(Value::as_str) else {
                    continue;
                };
                if !body.starts_with("## Codex Outcome\n") {
                    continue;
                }
                let heads: Vec<_> = body
                    .lines()
                    .filter_map(|line| {
                        line.strip_prefix("Durable/published head: ")
                            .or_else(|| line.strip_prefix("Latest durable and ready head: "))
                    })
                    .collect();
                if heads.len() != 1 || heads[0] != sha {
                    continue;
                }
                let Some(id) = identifier(comment.get("id")) else {
                    outcomes.fail(Failure::unavailable("GITHUB_RESPONSE_INVALID"));
                    continue;
                };
                let attempts: Vec<_> = body
                    .lines()
                    .filter_map(|line| line.strip_prefix("Attempt: "))
                    .collect();
                let run_id = if attempts.len() == 1 {
                    attempts[0]
                        .strip_prefix("run-")
                        .filter(|id| !id.starts_with('0'))
                        .and_then(|id| id.parse::<u64>().ok())
                        .filter(|id| *id > 0 && *id <= 9_007_199_254_740_991)
                } else {
                    None
                };
                if let Some(run_id) = run_id {
                    execution_pointers.push((*target, id, run_id));
                } else {
                    missing_execution_pointer = true;
                }
                let mut altered = false;
                let warning_fields = body
                    .lines()
                    .filter_map(|line| line.strip_prefix("Warning summary: "))
                    .collect::<Vec<_>>();
                if warning_fields.len() > 10 {
                    altered = true;
                }
                let warning_summaries: Vec<Value> = warning_fields
                    .into_iter()
                    .take(10)
                    .map(|summary| text(Some(&json!(summary)), 2048, &mut altered))
                    .collect();
                if body.contains("COMPLETED_WITH_WARNINGS") && warning_summaries.is_empty() {
                    outcomes.fail(Failure::unavailable(
                        "GITHUB_OUTCOME_WARNING_SUMMARY_UNAVAILABLE",
                    ));
                }
                runtime_items.push(json!({"comment_id": id, "issue_number": target, "head_sha": sha, "actor": writer_actor,
                    "native_url": format!("https://github.com/{repository}/issues/{target}#issuecomment-{id}"),
                    "workflow_run_id": run_id, "warning_summaries": warning_summaries, "text_redacted_or_truncated": altered}));
            }
        }
        if outcomes.reason.is_none() {
            outcomes.availability = if runtime_items.is_empty() {
                "absent"
            } else {
                "available"
            };
        }
        let mut runtime = outcomes.rendered("github_relay_execution_outcomes", &runtime_items);
        runtime["additional_api_paths"] = json!(additional_outcome_paths);
        let mut execution = Listing::new(&format!("/repos/{repository}/actions/runs"));
        execution.reason = Some("GITHUB_EXECUTION_RUN_POINTER_UNAVAILABLE");
        if runtime_items.is_empty() && complete_source(&runtime) {
            execution.availability = "absent";
            execution.reason = None;
        }
        let mut execution_run_items = vec![];
        let mut seen_runs = std::collections::HashSet::new();
        for pointer @ (_, _, run_id) in execution_pointers {
            if !seen_runs.insert(run_id) {
                continue;
            }
            if !missing_execution_pointer
                && execution.reason == Some("GITHUB_EXECUTION_RUN_POINTER_UNAVAILABLE")
            {
                execution.availability = "available";
                execution.reason = None;
            }
            match session
                .get(&format!("/repos/{repository}/actions/runs/{run_id}"), false)
                .await
            {
                Ok((run, _)) => match project_run(&run, repository, sha, Some(pointer)) {
                    Some(run) => execution_run_items.push(run),
                    None => {
                        execution.fail(Failure::unavailable("GITHUB_EVIDENCE_BINDING_MISMATCH"))
                    }
                },
                Err(failure) => execution.fail(failure),
            }
        }
        let mut suites = session
            .list(
                &format!("/repos/{repository}/commits/{sha}/check-suites"),
                Some("check_suites"),
                ITEMS,
            )
            .await;
        let mut suite_items = vec![];
        for suite in &suites.items {
            if suite.get("head_sha").and_then(Value::as_str) != Some(sha)
                || identifier(suite.get("id")).is_none()
            {
                suites.availability = "unavailable";
                suites.reason = Some("GITHUB_EVIDENCE_BINDING_MISMATCH");
                continue;
            }
            suite_items.push(json!({"check_suite_id": suite["id"], "head_sha": sha,
                "status": state(suite.get("status")), "conclusion": state(suite.get("conclusion")),
                "app_id": identifier(suite.pointer("/app/id"))}));
        }
        let mut runs = session
            .list(
                &format!("/repos/{repository}/actions/runs?head_sha={sha}"),
                Some("workflow_runs"),
                ITEMS,
            )
            .await;
        let mut run_items = vec![];
        for run in &runs.items {
            match project_run(run, repository, sha, None) {
                Some(run) => run_items.push(run),
                None => {
                    runs.availability = "unavailable";
                    runs.reason = Some("GITHUB_EVIDENCE_BINDING_MISMATCH");
                }
            }
        }
        let mut checks = session
            .list(
                &format!("/repos/{repository}/commits/{sha}/check-runs?filter=all"),
                Some("check_runs"),
                ITEMS,
            )
            .await;
        // Routing executions run at a trusted base head. Their check suites are
        // included only through the exact-head Writer Outcome/run binding.
        let mut execution_check_bindings = std::collections::HashMap::new();
        let mut additional_check_paths = vec![];
        let mut seen_suites = std::collections::HashSet::new();
        for run in &execution_run_items {
            let suite_id = identifier(run.get("check_suite_id")).unwrap();
            if !seen_suites.insert(suite_id) {
                continue;
            }
            let path = format!("/repos/{repository}/check-suites/{suite_id}/check-runs?filter=all");
            additional_check_paths.push(path.clone());
            if checks.items.len() >= ITEMS {
                checks.fail(Failure::truncated("GITHUB_ITEM_LIMIT"));
                continue;
            }
            let current = session
                .list(&path, Some("check_runs"), ITEMS - checks.items.len())
                .await;
            if let Some(reason) = current.reason {
                checks.fail(Failure {
                    availability: current.availability,
                    reason,
                });
            }
            let actual_sha = run["head_sha"].as_str().unwrap();
            for check in current.items {
                if check.get("head_sha").and_then(Value::as_str) != Some(actual_sha)
                    || identifier(check.pointer("/check_suite/id")) != Some(suite_id)
                    || identifier(check.get("id")).is_none()
                {
                    checks.fail(Failure::unavailable("GITHUB_EVIDENCE_BINDING_MISMATCH"));
                    continue;
                }
                let id = identifier(check.get("id")).unwrap();
                execution_check_bindings.insert(
                    id,
                    (
                        actual_sha.to_owned(),
                        identifier(run.get("outcome_comment_id")),
                    ),
                );
                if !checks
                    .items
                    .iter()
                    .any(|known| identifier(known.get("id")) == Some(id))
                {
                    checks.items.push(check);
                }
                if checks.reason.is_none() {
                    checks.availability = "available";
                }
            }
        }
        let mut check_items = vec![];
        let mut annotation_count = 0;
        let mut warning_count = 0;
        for check in &checks.items {
            let execution_binding =
                identifier(check.get("id")).and_then(|id| execution_check_bindings.get(&id));
            let actual_sha = execution_binding.map_or(sha, |(head, _)| head.as_str());
            if check.get("head_sha").and_then(Value::as_str) != Some(actual_sha)
                || identifier(check.get("id")).is_none()
                || identifier(check.pointer("/check_suite/id")).is_none()
            {
                checks.availability = "unavailable";
                checks.reason = Some("GITHUB_EVIDENCE_BINDING_MISMATCH");
                continue;
            }
            let id = identifier(check.get("id")).unwrap();
            let suite_id = identifier(check.pointer("/check_suite/id")).unwrap();
            let annotation_path = format!("/repos/{repository}/check-runs/{id}/annotations");
            let mut annotations = if annotation_count < ANNOTATIONS {
                session
                    .list(
                        &annotation_path,
                        None,
                        ITEMS.min(ANNOTATIONS - annotation_count),
                    )
                    .await
            } else {
                let mut listing = Listing::new(&annotation_path);
                listing.fail(Failure::truncated("GITHUB_ANNOTATION_LIMIT"));
                listing
            };
            annotation_count += annotations.items.len();
            let mut annotation_items = vec![];
            for annotation in &annotations.items {
                let Some(level @ ("notice" | "warning" | "failure")) =
                    annotation.get("annotation_level").and_then(Value::as_str)
                else {
                    annotations.availability = "unavailable";
                    annotations.reason = Some("GITHUB_RESPONSE_INVALID");
                    continue;
                };
                if annotation.get("message").and_then(Value::as_str).is_none() {
                    annotations.availability = "unavailable";
                    annotations.reason = Some("GITHUB_RESPONSE_INVALID");
                    continue;
                }
                let mut altered = false;
                annotation_items.push(json!({"level": level,
                    "path": text(annotation.get("path"), 256, &mut altered),
                    "start_line": identifier(annotation.get("start_line")), "end_line": identifier(annotation.get("end_line")),
                    "title": text(annotation.get("title"), 256, &mut altered),
                    "message": text(annotation.get("message"), 2048, &mut altered),
                    "text_redacted_or_truncated": altered}));
                warning_count += usize::from(level == "warning");
            }
            let associated_runs: Vec<u64> = run_items
                .iter()
                .chain(execution_run_items.iter())
                .filter(|run| run["check_suite_id"] == json!(suite_id))
                .filter_map(|run| identifier(run.get("run_id")))
                .take(ITEMS)
                .collect();
            let mut altered = false;
            check_items.push(json!({"check_run_id": id, "check_suite_id": suite_id, "workflow_run_ids": associated_runs,
                "head_sha": actual_sha, "reviewed_head_sha": sha,
                "association": if execution_binding.is_some() { "writer_exact_head_outcome" } else { "exact_head" },
                "outcome_comment_id": execution_binding.and_then(|(_, comment)| *comment),
                "name": text(check.get("name"), 256, &mut altered),
                "app_id": identifier(check.pointer("/app/id")), "app_slug": text(check.pointer("/app/slug"), 100, &mut altered),
                "status": state(check.get("status")), "conclusion": state(check.get("conclusion")),
                "native_url": format!("https://github.com/{repository}/runs/{id}"),
                "text_redacted_or_truncated": altered,
                "annotations": annotations.rendered("github_check_run_annotations", &annotation_items)}));
        }
        let primary = json!({"source": "github_workflow_run_platform_annotations", "availability": "unavailable",
            "reason": "GITHUB_UI_ONLY_SERVICE_ANNOTATIONS_OUT_OF_SCOPE", "required_for_completeness": false, "items": [],
            "native_urls": run_items.iter().chain(execution_run_items.iter()).map(|run| run["native_url"].clone()).take(ITEMS * 2).collect::<Vec<_>>(),
            "explanation": "UI-only GitHub service-level/pre-execution annotations are outside mandatory automated evidence acquisition. No HTML or browser-session fallback is used. Complete in-scope API evidence does not prove absence of GitHub UI warnings."});
        let mut check_surface = checks.rendered("github_check_runs", &check_items);
        check_surface["additional_api_paths"] = json!(additional_check_paths);
        evidence["surfaces"] = json!([
            suites.rendered("github_check_suites", &suite_items),
            runs.rendered("github_actions_workflow_runs", &run_items),
            check_surface,
            primary,
            runtime,
            execution.rendered("github_relay_execution_workflow_runs", &execution_run_items)
        ]);
        evidence["observed_check_annotation_warnings"] = json!(warning_count);
        let final_binding = match session.get(&pr_path, true).await {
            Ok((pr, _)) => {
                verify_pr(&pr, repository, pr_number, sha)?;
                if crate::step_sync::linked_issue(&pr) != linked_issue {
                    return Err("GITHUB_EVIDENCE_TARGET_CHANGED");
                }
                json!({"availability": "available", "binding_verified": true})
            }
            Err(failure) => {
                json!({"availability": failure.availability, "reason": failure.reason, "binding_verified": false})
            }
        };
        evidence["target"] = json!({"source": "github_pull_request", "api_path": pr_path,
            "head_sha": sha, "initial_binding_verified": true, "final_binding": final_binding});
        evidence["requests_observed"] = json!(session.requests);
        evidence["response_byte_budget_used"] = json!(session.bytes);
        redact_exact_credentials(&mut evidence, &[&session.token, &session.jwt]);
        let complete = final_binding["binding_verified"] == true
            && evidence["surfaces"]
                .as_array()
                .unwrap()
                .iter()
                .all(|surface| {
                    surface["required_for_completeness"] == false || complete_source(surface)
                });
        evidence["required_surfaces_complete"] = json!(complete);
        let runtime_warnings = runtime_items.iter().any(|item| {
            item["warning_summaries"]
                .as_array()
                .is_some_and(|warnings| !warnings.is_empty())
        });
        evidence["warning_observation"] = json!(if !complete {
            "unknown"
        } else if warning_count > 0 || runtime_warnings {
            "observed"
        } else {
            "none_observed"
        });
        Ok(evidence)
    }
}
