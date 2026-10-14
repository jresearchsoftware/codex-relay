use axum::{
    body::Bytes,
    extract::State,
    http::{HeaderMap, Method, StatusCode, Uri},
    response::{IntoResponse, Response},
    routing::any,
    Json, Router,
};
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};

const REPOSITORY: &str = "example-org/sample-project";
const SHA: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const OTHER_SHA: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const WRITER: &str = "example-writer[bot]";

#[derive(Clone)]
struct MockEvidence {
    mode: &'static str,
    calls: Arc<Mutex<Vec<Value>>>,
    outcome_warnings: Option<Vec<Value>>,
    annotations: Option<Vec<Value>>,
    metadata_text: Option<String>,
}

fn pr(sha: &str, issue: u64) -> Value {
    json!({"number": 25, "body": format!("Related to #{issue}"), "state": "open", "draft": false, "merged": false,
        "head": {"sha": sha}, "base": {"repo": {"full_name": REPOSITORY}}})
}

fn check(id: u64, sha: &str) -> Value {
    json!({"id": id, "head_sha": sha, "name": "test", "status": "completed", "conclusion": "success",
        "check_suite": {"id": 11}, "app": {"id": 101, "slug": "github-actions"},
        "details_url": "https://unrelated.example/never-follow", "output": {"text": "do-not-return-output"}})
}

fn annotation(message: &str) -> Value {
    json!({"path": "src/index.js", "start_line": 1, "end_line": 1, "annotation_level": "warning",
        "title": "Runtime warning", "message": message, "raw_details": "do-not-return-raw-details",
        "blob_href": "https://unrelated.example/never-follow"})
}

fn comment(id: u64, actor: &str, body: &str) -> Value {
    json!({"id": id, "user": {"login": actor}, "body": body, "html_url": "https://unrelated.example/never-follow"})
}

async fn handler(
    State(mock): State<MockEvidence>,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let request = json!({"method": method.as_str(), "path": uri.path(), "query": uri.query(),
        "authorization": headers.get("authorization").and_then(|v| v.to_str().ok()),
        "user_agent": headers.get("user-agent").and_then(|v| v.to_str().ok()),
        "body": serde_json::from_slice::<Value>(&body).unwrap_or(Value::Null)});
    mock.calls.lock().unwrap().push(request);
    if uri.path() == "/app/installations/1/access_tokens" {
        assert_eq!(method, Method::POST);
        if mock.mode == "authdenied" {
            return StatusCode::FORBIDDEN.into_response();
        }
        return Json(
            json!({"token": "synthetic-evidence-token", "expires_at": "2030-01-01T00:00:00Z"}),
        )
        .into_response();
    }
    assert_eq!(method, Method::GET, "repository evidence must be GET-only");
    assert_eq!(
        headers.get("authorization").unwrap(),
        "Bearer synthetic-evidence-token"
    );
    assert_eq!(
        headers.get("accept").unwrap(),
        "application/vnd.github+json"
    );
    assert_eq!(headers.get("x-github-api-version").unwrap(), "2022-11-28");
    assert!(
        uri.path().starts_with(&format!("/repos/{REPOSITORY}/")),
        "unexpected repository path"
    );
    if uri.path() == format!("/repos/{REPOSITORY}/pulls/25") {
        let reads = mock
            .calls
            .lock()
            .unwrap()
            .iter()
            .filter(|call| call["path"] == uri.path())
            .count();
        if mock.mode == "missingpr" {
            return StatusCode::NOT_FOUND.into_response();
        }
        if reads > 1 && mock.mode == "finaldenied" {
            return StatusCode::FORBIDDEN.into_response();
        }
        let sha = if mock.mode == "stale" && reads > 1 {
            OTHER_SHA
        } else {
            SHA
        };
        let issue = if mock.mode == "targetchanged" && reads > 1 {
            57
        } else {
            56
        };
        let mut result = pr(sha, issue);
        if mock.mode == "unknownissue" {
            result["body"] = json!("Unrelated text");
        }
        if mock.mode == "initialbadrepo" {
            result["base"]["repo"]["full_name"] = json!("foreign/repo");
        }
        return Json(result).into_response();
    }
    if uri.path() == format!("/repos/{REPOSITORY}/actions/runs/41") {
        let repository = if mock.mode == "executionforeign" {
            "foreign/repo"
        } else {
            REPOSITORY
        };
        let id = if mock.mode == "executionwrongid" {
            999
        } else {
            41
        };
        return Json(json!({"id": id, "head_sha": OTHER_SHA, "check_suite_id": 41, "run_attempt": 1, "workflow_id": 31,
            "name": mock.metadata_text.as_deref().unwrap_or("Relay routing"), "event": "issues", "status": "completed", "conclusion": "success",
            "repository": {"full_name": repository}})).into_response();
    }
    if uri.path().ends_with("/check-suites") {
        if mock.mode == "redirect" {
            return (
                StatusCode::TEMPORARY_REDIRECT,
                [("location", "https://unrelated.example/credentials")],
            )
                .into_response();
        }
        return Json(
            json!({"total_count": 1, "check_suites": [{"id": 11, "head_sha": SHA,
            "status": "completed", "conclusion": "success", "app": {"id": 101}}]}),
        )
        .into_response();
    }
    if uri.path().ends_with("/actions/runs") {
        assert!(uri.query().unwrap().contains(&format!("head_sha={SHA}")));
        if mock.mode == "actions404" {
            return StatusCode::NOT_FOUND.into_response();
        }
        let repository = if mock.mode == "badrunrepo" {
            "foreign/repo"
        } else {
            REPOSITORY
        };
        return Json(json!({"total_count": 1, "workflow_runs": [{"id": 21, "name": mock.metadata_text.as_deref().unwrap_or("CI"), "head_sha": SHA,
            "repository": {"full_name": repository}, "check_suite_id": 11, "run_attempt": 2, "workflow_id": 31,
            "event": "pull_request", "status": "completed", "conclusion": if mock.mode == "preexecution" { "skipped" } else { "success" }}]})).into_response();
    }
    if uri.path().ends_with("/check-runs") {
        assert!(uri.query().unwrap().contains("filter=all"));
        if uri.path() == format!("/repos/{REPOSITORY}/check-suites/41/check-runs") {
            let sha = if mock.mode == "executioncheckbad" {
                SHA
            } else {
                OTHER_SHA
            };
            let mut run_check = check(42, sha);
            run_check["check_suite"]["id"] = json!(41);
            return Json(json!({"total_count": 1, "check_runs": [run_check]})).into_response();
        }
        if mock.mode == "permission" {
            return StatusCode::FORBIDDEN.into_response();
        }
        if mock.mode == "oversized" {
            return Json(json!({"unrelated": "x".repeat(300 * 1024)})).into_response();
        }
        if mock.mode == "malformed" {
            return (StatusCode::OK, "not-json").into_response();
        }
        if mock.mode == "empty" {
            return Json(json!({"total_count": 0, "check_runs": []})).into_response();
        }
        if mock.mode == "globallimit" {
            let page = query_page(&uri);
            let checks: Vec<_> = (0..25)
                .map(|index| check(100 + (page - 1) * 25 + index, SHA))
                .collect();
            return Json(json!({"total_count": 75, "check_runs": checks})).into_response();
        }
        let sha = if mock.mode == "badhead" {
            OTHER_SHA
        } else {
            SHA
        };
        if mock.mode == "preexecution" {
            let mut skipped = check(12, sha);
            skipped["conclusion"] = json!("skipped");
            skipped["started_at"] = Value::Null;
            return Json(json!({"total_count": 1, "check_runs": [skipped]})).into_response();
        }
        let mut native_check = check(12, sha);
        if let Some(text) = &mock.metadata_text {
            native_check["name"] = json!(text);
            native_check["app"]["slug"] = json!(text);
        }
        return Json(json!({"total_count": 1, "check_runs": [native_check]})).into_response();
    }
    if uri.path().ends_with("/annotations") {
        if let Some(items) = &mock.annotations {
            return Json(json!(items)).into_response();
        }
        if matches!(
            mock.mode,
            "clean" | "executiononlyruntimewarning" | "preexecution"
        ) {
            return Json(json!([])).into_response();
        }
        if mock.mode == "rawcredential" {
            return Json(json!([
                annotation("synthetic-evidence-token"),
                annotation("test-jwt")
            ]))
            .into_response();
        }
        if mock.mode == "annotation404" {
            return StatusCode::NOT_FOUND.into_response();
        }
        if mock.mode == "annotationbad" {
            return Json(json!([{ "message": "missing level" }])).into_response();
        }
        if mock.mode == "pagination" {
            // The hostile Link URL is only a continuation signal. It is never followed.
            return (
                [(
                    "link",
                    "<https://unrelated.example/never-follow>; rel=\"next\"",
                )],
                Json(json!((0..25)
                    .map(|_| annotation("Paged warning"))
                    .collect::<Vec<_>>())),
            )
                .into_response();
        }
        if mock.mode == "redact" {
            let credential = format!("{}{}", concat!("github", "_pat_"), "synthetic-secret");
            return Json(json!([
                annotation(&credential),
                annotation("See /etc/relay-example/protected diagnostics"),
                annotation("normal warning")
            ]))
            .into_response();
        }
        if mock.mode == "longtext" {
            return Json(json!([annotation(&"é".repeat(2049))])).into_response();
        }
        return Json(json!([annotation(
            "UNCOMMITTED_WORK_REMAINS: reconcile retained work"
        )]))
        .into_response();
    }
    if uri.path() == format!("/repos/{REPOSITORY}/issues/25/comments") {
        if mock.mode == "runtimepr403" {
            return StatusCode::FORBIDDEN.into_response();
        }
        if matches!(mock.mode, "executionpr" | "executionpartial") {
            return Json(json!([comment(71, WRITER, &format!("## Codex Outcome\nAttempt: run-41\nDurable/published head: {SHA}\nWarning summary: PR execution warning"))])).into_response();
        }
        return Json(json!([])).into_response();
    }
    if uri.path() == format!("/repos/{REPOSITORY}/issues/56/comments") {
        if mock.mode == "runtime403" {
            return StatusCode::FORBIDDEN.into_response();
        }
        if mock.mode.starts_with("typedoutcome") {
            let mut authority = json!({"charter":{"kind":"issue-body","id":560,"parent":{"kind":"issue","number":56},"sha256":"c".repeat(64)},"decisions":[],"change_request":null,"compatibility_request":null});
            authority["sha256"] = json!(crate::task_authority::hash(
                &serde_json::to_string_pretty(&authority).unwrap()
            ));
            let mut record = json!({"schema_version":"4.0","kind":"outcome","repository":REPOSITORY,"task":56,"parent":{"kind":"issue","number":56},"charter_sha256":"c".repeat(64),
                "authority":authority,"admission":{"attempt":"run-41","step":1,"sha256":"d".repeat(64)},"step":1,"attempt":"run-41","status":"implemented",
                "result":{"kind":"git","revision":SHA,"identities":[]},"summary":"The source candidate awaits independent review.","limitations":["Installed behavior unverified."],
                "warnings":[{"source":"runtime-check","impact":"Qualification remains pending.","resolution":"Deferred to owner-authorized qualification.","next_action":"Inspect the retained limitation.","evidence_gaps":["No ingress probe was authorized."]}]});
            if let Some(warnings) = &mock.outcome_warnings {
                record["warnings"] = json!(warnings);
            }
            let mut native = comment(61, WRITER, &crate::task_authority::render(&record));
            native["user"]["type"] = json!(if mock.mode == "typedoutcomeowner" {
                "User"
            } else {
                "Bot"
            });
            native["user"]["id"] = json!(3);
            if mock.mode == "typedoutcomeinvalid" {
                native["body"] = json!(format!(
                    "{}\n```relay-authority\n{{}}\n```",
                    native["body"].as_str().unwrap()
                ));
            }
            return Json(json!([native])).into_response();
        }
        let attempt = if mock.mode.starts_with("execution") && mock.mode != "executionpartial" {
            "Attempt: run-41\n"
        } else {
            ""
        };
        let summary = mock
            .outcome_warnings
            .as_ref()
            .and_then(|warnings| warnings.first())
            .and_then(|warning| warning["impact"].as_str())
            .unwrap_or("UNCOMMITTED_WORK_REMAINS: retained work");
        let accepted = comment(61, WRITER, &format!("## Codex Outcome\n\n{attempt}Latest durable and ready head: {SHA}\nWarning summary: {summary}\nPrimary diagnostics: do-not-return-protected-diagnostics"));
        let foreign_actor = comment(62, "unrelated-author", &format!("## Codex Outcome\nAttempt: run-666\nDurable/published head: {SHA}\nWarning summary: do-not-return-untrusted-warning"));
        let stale = comment(63, WRITER, &format!("## Codex Outcome\nDurable/published head: {OTHER_SHA}\nWarning summary: do-not-return-stale-warning"));
        let wrong_marker = comment(64, WRITER, &format!("Quoted ## Codex Outcome\nDurable/published head: {SHA}\nWarning summary: do-not-return-quoted-warning"));
        let double_head = comment(65, WRITER, &format!("## Codex Outcome\nDurable/published head: {SHA}\nLatest durable and ready head: {OTHER_SHA}\nWarning summary: do-not-return-ambiguous-warning"));
        if matches!(mock.mode, "clean" | "preexecution" | "executionpr") {
            return Json(json!([])).into_response();
        }
        if mock.mode == "runtimesummarymissing" {
            return Json(json!([comment(61, WRITER, &format!("## Codex Outcome\nAttempt: run-41\nDurable/published head: {SHA}\nCompletion: COMPLETED_WITH_WARNINGS"))])).into_response();
        }
        if mock.mode == "runtimeabsent" {
            return Json(json!([foreign_actor, stale, wrong_marker, double_head])).into_response();
        }
        if mock.mode == "runtimelimit" {
            return Json(json!((0..25).map(|_| stale.clone()).collect::<Vec<_>>())).into_response();
        }
        if mock.mode == "redact" {
            return Json(json!([comment(61, WRITER, &format!("## Codex Outcome\nDurable/published head: {SHA}\nWarning summary: token=synthetic-secret"))])).into_response();
        }
        return Json(json!([
            accepted,
            foreign_actor,
            stale,
            wrong_marker,
            double_head
        ]))
        .into_response();
    }
    panic!("unexpected endpoint: {uri}");
}

fn query_page(uri: &Uri) -> u64 {
    uri.query()
        .unwrap()
        .split('&')
        .find_map(|item| item.strip_prefix("page="))
        .unwrap()
        .parse()
        .unwrap()
}

async fn server(
    mode: &'static str,
) -> (
    crate::github::Github,
    MockEvidence,
    tokio::task::JoinHandle<()>,
) {
    server_with_text(mode, None, None, None).await
}

async fn server_with_text(
    mode: &'static str,
    outcome_warnings: Option<Vec<Value>>,
    annotations: Option<Vec<Value>>,
    metadata_text: Option<String>,
) -> (
    crate::github::Github,
    MockEvidence,
    tokio::task::JoinHandle<()>,
) {
    let state = MockEvidence {
        mode,
        calls: Arc::new(Mutex::new(vec![])),
        outcome_warnings,
        annotations,
        metadata_text,
    };
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let router = Router::new()
        .fallback(any(handler))
        .with_state(state.clone());
    let task = tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    (
        crate::github::Github::mock_api(format!("http://{address}")),
        state,
        task,
    )
}

async fn acquire(mode: &'static str) -> (Result<Value, &'static str>, Vec<Value>) {
    let (github, mock, task) = server(mode).await;
    let result = github
        .review_evidence(REPOSITORY, REPOSITORY, 25, SHA, WRITER)
        .await;
    task.abort();
    let calls = mock.calls.lock().unwrap().clone();
    (result, calls)
}

fn warning(source: &str, impact: &str) -> Value {
    json!({"source": source, "impact": impact, "resolution": "Retained for independent review.",
        "next_action": "Review this warning.", "evidence_gaps": []})
}

async fn acquire_text(
    warnings: Vec<Value>,
    annotations: Vec<Value>,
    metadata: Option<String>,
) -> Value {
    let (github, _, task) =
        server_with_text("typedoutcome", Some(warnings), Some(annotations), metadata).await;
    let result = github
        .review_evidence(REPOSITORY, REPOSITORY, 25, SHA, WRITER)
        .await
        .unwrap();
    task.abort();
    result
}

fn surface<'a>(evidence: &'a Value, name: &str) -> &'a Value {
    evidence["surfaces"]
        .as_array()
        .unwrap()
        .iter()
        .find(|surface| surface["source"] == name)
        .unwrap()
}

#[tokio::test]
async fn supported_evidence_is_exact_head_scoped_read_only_and_honest_about_primary_gaps() {
    let (result, calls) = acquire("normal").await;
    let evidence = result.unwrap();
    let token = &calls[0];
    assert_eq!(
        token["body"],
        json!({"repositories": ["sample-project"], "permissions": {
        "metadata": "read", "pull_requests": "read", "checks": "read", "actions": "read", "issues": "read"}})
    );
    assert_eq!(token["authorization"], "Bearer test-jwt");
    assert!(calls
        .iter()
        .all(|call| call["user_agent"] == crate::github::USER_AGENT));
    assert!(calls
        .iter()
        .skip(1)
        .all(|call| call["method"] == "GET" && call["body"].is_null()));
    assert_eq!(evidence["target"]["initial_binding_verified"], true);
    assert_eq!(
        evidence["target"]["final_binding"]["binding_verified"],
        true
    );
    assert_eq!(
        calls.first().unwrap()["path"],
        "/app/installations/1/access_tokens"
    );
    assert_eq!(
        calls.last().unwrap()["path"],
        format!("/repos/{REPOSITORY}/pulls/25")
    );
    let checks = surface(&evidence, "github_check_runs");
    assert_eq!(checks["availability"], "available");
    assert_eq!(checks["items"][0]["workflow_run_ids"], json!([21]));
    assert_eq!(checks["items"][0]["head_sha"], SHA);
    assert_eq!(
        checks["items"][0]["annotations"]["items"][0]["level"],
        "warning"
    );
    let runtime = surface(&evidence, "github_relay_execution_outcomes");
    assert_eq!(runtime["items"].as_array().unwrap().len(), 1);
    assert_eq!(runtime["items"][0]["comment_id"], 61);
    assert_eq!(
        runtime["items"][0]["warning_summaries"],
        json!(["UNCOMMITTED_WORK_REMAINS: retained work"])
    );
    let primary = surface(&evidence, "github_workflow_run_platform_annotations");
    assert_eq!(primary["availability"], "unavailable");
    assert_eq!(primary["required_for_completeness"], false);
    assert_eq!(
        primary["reason"],
        "GITHUB_UI_ONLY_SERVICE_ANNOTATIONS_OUT_OF_SCOPE"
    );
    assert_eq!(
        primary["native_urls"],
        json!([format!("https://github.com/{REPOSITORY}/actions/runs/21")])
    );
    assert_eq!(evidence["required_surfaces_complete"], false);
    assert_eq!(evidence["warning_observation"], "unknown");
    let serialized = evidence.to_string();
    for excluded in [
        "synthetic-evidence-token",
        "test-jwt",
        "do-not-return",
        "unrelated.example",
        "raw_details",
        "details_url",
    ] {
        assert!(
            !serialized.contains(excluded),
            "leaked disallowed field {excluded}"
        );
    }
}

#[tokio::test]
async fn different_repositories_and_invalid_targets_fail_before_authentication() {
    let (github, mock, task) = server("normal").await;
    for (repository, number, sha, writer, code) in [
        ("foreign/repo", 25, SHA, WRITER, "REPOSITORY_NOT_ALLOWED"),
        (REPOSITORY, 0, SHA, WRITER, "INVALID_PR_NUMBER"),
        (REPOSITORY, 25, "../refs/main", WRITER, "INVALID_HEAD_SHA"),
        (
            REPOSITORY,
            25,
            SHA,
            "../writer",
            "GITHUB_WRITER_IDENTITY_UNAVAILABLE",
        ),
    ] {
        assert_eq!(
            github
                .review_evidence(REPOSITORY, repository, number, sha, writer)
                .await,
            Err(code)
        );
    }
    assert!(mock.calls.lock().unwrap().is_empty());
    task.abort();
}

#[tokio::test]
async fn supported_completeness_excludes_ui_only_service_annotations() {
    for (mode, observation) in [
        ("execution", "observed"),
        ("executiononlyruntimewarning", "observed"),
        ("clean", "none_observed"),
        ("preexecution", "none_observed"),
    ] {
        let (result, calls) = acquire(mode).await;
        let evidence = result.unwrap();
        assert_eq!(evidence["required_surfaces_complete"], true, "{mode}");
        assert_eq!(evidence["warning_observation"], observation, "{mode}");
        let excluded = surface(&evidence, "github_workflow_run_platform_annotations");
        assert_eq!(excluded["availability"], "unavailable");
        assert_eq!(excluded["required_for_completeness"], false);
        assert!(calls.iter().skip(1).all(|call| {
            call["path"]
                .as_str()
                .unwrap()
                .starts_with(&format!("/repos/{REPOSITORY}/"))
        }));
    }
}

#[tokio::test]
async fn pr_writer_outcomes_bind_runtime_runs_and_collection_failures_preclude_absence() {
    let (result, calls) = acquire("executionpr").await;
    let evidence = result.unwrap();
    let outcomes = surface(&evidence, "github_relay_execution_outcomes");
    assert_eq!(outcomes["items"][0]["comment_id"], 71);
    assert_eq!(outcomes["items"][0]["issue_number"], 25);
    let run = &surface(&evidence, "github_relay_execution_workflow_runs")["items"][0];
    assert_eq!(run["outcome_comment_id"], 71);
    assert_eq!(run["issue_number"], 25);
    assert_eq!(run["head_sha"], OTHER_SHA);
    assert_eq!(run["reviewed_head_sha"], SHA);
    assert_eq!(evidence["required_surfaces_complete"], true);
    assert_eq!(evidence["warning_observation"], "observed");
    assert!(calls
        .iter()
        .any(|call| call["path"] == format!("/repos/{REPOSITORY}/issues/25/comments")));
    for mode in [
        "runtimepr403",
        "executionpartial",
        "runtimesummarymissing",
        "annotation404",
        "longtext",
        "finaldenied",
    ] {
        let evidence = acquire(mode).await.0.unwrap();
        assert_eq!(evidence["required_surfaces_complete"], false, "{mode}");
        assert_eq!(evidence["warning_observation"], "unknown", "{mode}");
    }
}

#[tokio::test]
async fn routing_execution_runs_preserve_their_base_head_and_exact_outcome_provenance() {
    let (result, calls) = acquire("execution").await;
    let evidence = result.unwrap();
    let execution = surface(&evidence, "github_relay_execution_workflow_runs");
    assert_eq!(execution["availability"], "available");
    let run = &execution["items"][0];
    assert_eq!(run["run_id"], 41);
    assert_eq!(run["head_sha"], OTHER_SHA);
    assert_eq!(run["reviewed_head_sha"], SHA);
    assert_eq!(run["outcome_comment_id"], 61);
    assert_eq!(run["issue_number"], 56);
    assert_eq!(run["association"], "writer_exact_head_outcome");
    let check = surface(&evidence, "github_check_runs")["items"]
        .as_array()
        .unwrap()
        .iter()
        .find(|check| check["check_run_id"] == 42)
        .unwrap();
    assert_eq!(check["head_sha"], OTHER_SHA);
    assert_eq!(check["reviewed_head_sha"], SHA);
    assert_eq!(check["workflow_run_ids"], json!([41]));
    assert_eq!(check["outcome_comment_id"], 61);
    assert_eq!(check["annotations"]["availability"], "available");
    assert!(!calls
        .iter()
        .any(|call| call["path"].as_str().unwrap().contains("666")));
    assert!(
        surface(&evidence, "github_workflow_run_platform_annotations")["native_urls"]
            .as_array()
            .unwrap()
            .contains(&json!(format!(
                "https://github.com/{REPOSITORY}/actions/runs/41"
            )))
    );
    for mode in ["executionforeign", "executionwrongid"] {
        let (result, calls) = acquire(mode).await;
        let evidence = result.unwrap();
        assert_eq!(
            surface(&evidence, "github_relay_execution_workflow_runs")["availability"],
            "unavailable"
        );
        assert!(
            surface(&evidence, "github_relay_execution_workflow_runs")["items"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        assert!(!calls.iter().any(|call| call["path"]
            .as_str()
            .unwrap()
            .contains("check-suites/41/check-runs")));
    }
    let (result, calls) = acquire("executioncheckbad").await;
    let evidence = result.unwrap();
    assert_eq!(
        surface(&evidence, "github_check_runs")["availability"],
        "unavailable"
    );
    assert!(!calls.iter().any(|call| call["path"]
        .as_str()
        .unwrap()
        .contains("check-runs/42/annotations")));
    let evidence = acquire("normal").await.0.unwrap();
    assert_eq!(
        surface(&evidence, "github_relay_execution_workflow_runs")["reason"],
        "GITHUB_EXECUTION_RUN_POINTER_UNAVAILABLE"
    );
}

#[tokio::test]
async fn denied_hidden_absent_and_malformed_sources_remain_distinct() {
    for (mode, source, expected) in [
        ("permission", "github_check_runs", "permission_denied"),
        ("actions404", "github_actions_workflow_runs", "unavailable"),
        ("empty", "github_check_runs", "absent"),
        ("malformed", "github_check_runs", "unavailable"),
        (
            "runtime403",
            "github_relay_execution_outcomes",
            "permission_denied",
        ),
        ("runtimeabsent", "github_relay_execution_outcomes", "absent"),
        (
            "unknownissue",
            "github_relay_execution_outcomes",
            "unavailable",
        ),
    ] {
        let evidence = acquire(mode).await.0.unwrap();
        assert_eq!(
            surface(&evidence, source)["availability"],
            expected,
            "{mode}"
        );
        assert_eq!(
            evidence["warning_observation"],
            if mode == "runtimeabsent" {
                "observed"
            } else {
                "unknown"
            }
        );
    }
    for mode in ["annotation404", "annotationbad"] {
        let evidence = acquire(mode).await.0.unwrap();
        assert_eq!(
            surface(&evidence, "github_check_runs")["items"][0]["annotations"]["availability"],
            "unavailable"
        );
    }
    let (result, calls) = acquire("authdenied").await;
    assert_eq!(
        result.unwrap()["target"]["availability"],
        "permission_denied"
    );
    assert_eq!(calls.len(), 1);
    let (result, calls) = acquire("missingpr").await;
    assert_eq!(result.unwrap()["target"]["availability"], "unavailable");
    assert_eq!(calls.len(), 2);
}

#[tokio::test]
async fn response_pagination_item_and_request_limits_return_partial_evidence() {
    let oversized = acquire("oversized").await.0.unwrap();
    assert_eq!(
        surface(&oversized, "github_check_runs")["availability"],
        "truncated"
    );
    let (result, calls) = acquire("pagination").await;
    let evidence = result.unwrap();
    let annotations = &surface(&evidence, "github_check_runs")["items"][0]["annotations"];
    assert_eq!(annotations["availability"], "truncated");
    assert_eq!(annotations["items"].as_array().unwrap().len(), 75);
    assert_eq!(annotations["pages_observed"], 3);
    assert_eq!(
        calls
            .iter()
            .filter(|call| call["path"].as_str().unwrap().ends_with("/annotations"))
            .count(),
        3
    );
    assert!(calls
        .iter()
        .all(|call| !call["path"].as_str().unwrap().contains("never-follow")));
    let runtime = acquire("runtimelimit").await.0.unwrap();
    assert_eq!(
        surface(&runtime, "github_relay_execution_outcomes")["availability"],
        "truncated"
    );
    let (result, calls) = acquire("globallimit").await;
    let evidence = result.unwrap();
    assert!(calls.len() <= 40);
    assert_eq!(
        evidence["target"]["final_binding"]["binding_verified"],
        true
    );
    assert!(surface(&evidence, "github_check_runs")["items"]
        .as_array()
        .unwrap()
        .iter()
        .any(|check| check["annotations"]["reason"] == "GITHUB_REQUEST_LIMIT"));
    assert!(evidence["response_byte_budget_used"].as_u64().unwrap() <= 2 * 1024 * 1024);
}

#[tokio::test]
async fn response_links_cross_repository_heads_and_changed_targets_are_rejected() {
    let redirected = acquire("redirect").await.0.unwrap();
    assert_eq!(
        surface(&redirected, "github_check_suites")["reason"],
        "GITHUB_REDIRECT_REJECTED"
    );
    for (mode, source) in [
        ("badhead", "github_check_runs"),
        ("badrunrepo", "github_actions_workflow_runs"),
    ] {
        let (result, calls) = acquire(mode).await;
        let evidence = result.unwrap();
        assert_eq!(surface(&evidence, source)["availability"], "unavailable");
        assert!(surface(&evidence, source)["items"]
            .as_array()
            .unwrap()
            .is_empty());
        if mode == "badhead" {
            assert!(!calls
                .iter()
                .any(|call| call["path"].as_str().unwrap().ends_with("/annotations")));
        }
    }
    assert_eq!(acquire("stale").await.0, Err("STALE_HEAD"));
    assert_eq!(
        acquire("targetchanged").await.0,
        Err("GITHUB_EVIDENCE_TARGET_CHANGED")
    );
    let (result, calls) = acquire("initialbadrepo").await;
    assert_eq!(result, Err("GITHUB_EVIDENCE_TARGET_UNVERIFIED"));
    assert_eq!(calls.len(), 2);
    let final_denied = acquire("finaldenied").await.0.unwrap();
    assert_eq!(
        final_denied["target"]["final_binding"]["availability"],
        "permission_denied"
    );
    assert_eq!(
        final_denied["target"]["final_binding"]["binding_verified"],
        false
    );
    assert_eq!(final_denied["warning_observation"], "unknown");
}

#[tokio::test]
async fn protected_content_is_redacted_and_multibyte_text_is_bounded() {
    let raw = acquire("rawcredential").await.0.unwrap();
    assert!(!raw.to_string().contains("synthetic-evidence-token"));
    assert!(!raw.to_string().contains("test-jwt"));
    for annotation in surface(&raw, "github_check_runs")["items"][0]["annotations"]["items"]
        .as_array()
        .unwrap()
    {
        assert_eq!(annotation["message"], "[REDACTED_PROTECTED_CONTENT]");
        assert_eq!(annotation["text_redacted_or_truncated"], true);
    }
    let evidence = acquire("redact").await.0.unwrap();
    let annotations = &surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"];
    assert_eq!(annotations[0]["message"], "[REDACTED_PROTECTED_CONTENT]");
    assert_eq!(annotations[1]["message"], "[REDACTED_PROTECTED_CONTENT]");
    assert_eq!(annotations[2]["message"], "normal warning");
    assert!(!evidence.to_string().contains("synthetic-secret"));
    assert!(!evidence.to_string().contains("/etc/relay"));
    let evidence = acquire("longtext").await.0.unwrap();
    let annotation =
        &surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0];
    assert!(annotation["message"].as_str().unwrap().len() <= 2048);
    assert_eq!(annotation["text_redacted_or_truncated"], true);
}

#[tokio::test]
async fn folded_typed_outcomes_preserve_exact_head_execution_warning_and_bot_provenance() {
    let evidence = acquire("typedoutcome").await.0.unwrap();
    let outcomes = surface(&evidence, "github_relay_execution_outcomes");
    assert_eq!(outcomes["availability"], "available");
    assert_eq!(outcomes["items"][0]["workflow_run_id"], 41);
    assert!(outcomes["items"][0]["warning_summaries"][0]
        .as_str()
        .unwrap()
        .contains("No ingress probe was authorized."));
    assert_eq!(
        surface(&evidence, "github_relay_execution_workflow_runs")["items"][0]["head_sha"],
        OTHER_SHA
    );
    for mode in ["typedoutcomeowner", "typedoutcomeinvalid"] {
        let evidence = acquire(mode).await.0.unwrap();
        assert_eq!(
            surface(&evidence, "github_relay_execution_outcomes")["availability"],
            "unavailable",
            "{mode}"
        );
        assert_eq!(evidence["required_surfaces_complete"], false);
        assert_eq!(evidence["warning_observation"], "unknown");
    }
}

#[tokio::test]
async fn task_wording_and_test_service_warning_patterns_remain_complete() {
    // Synthetic schema-v4 equivalents of the two Task 127 / PR 126 patterns.
    // These are operational summaries, not private host data or live fixtures.
    let warnings = vec![
        json!({"source": "disposable-test", "impact": "Task-authorized qualification used task-local instrumentation.",
            "resolution": "The isolated TEST sandbox was restored.", "next_action": "Review source acceptance separately.",
            "evidence_gaps": ["This does not establish installed Reviewer adoption."]}),
        json!({"source": "node22-test-service", "impact": "The isolated TEST Node 22 service used /etc/systemd/system/example-test.service.d/node22.conf.",
            "resolution": "Temporary service instrumentation was removed.", "next_action": "Owner disposition of later adoption remains pending.",
            "evidence_gaps": []}),
    ];
    let evidence = acquire_text(warnings, vec![], None).await;
    let outcome = &surface(&evidence, "github_relay_execution_outcomes")["items"][0];
    assert_eq!(outcome["warning_summaries"], json!([
        "disposable-test: Task-authorized qualification used task-local instrumentation.; disposition: The isolated TEST sandbox was restored.; next action: Review source acceptance separately.; evidence gaps: This does not establish installed Reviewer adoption.",
        "node22-test-service: The isolated TEST Node 22 service used /etc/systemd/system/example-test.service.d/node22.conf.; disposition: Temporary service instrumentation was removed.; next action: Owner disposition of later adoption remains pending.; evidence gaps: "
    ]));
    assert_eq!(outcome["text_redacted_or_truncated"], false);
    assert_eq!(outcome["head_sha"], SHA);
    assert_eq!(outcome["actor"], WRITER);
    assert_eq!(outcome["workflow_run_id"], 41);
    assert_eq!(evidence["required_surfaces_complete"], true);
    assert_eq!(evidence["warning_observation"], "observed");
}

#[tokio::test]
async fn ordinary_annotations_and_legacy_warning_summaries_remain_readable() {
    for message in [
        "Task-authorized task-local risk-based checks in Slovakia.",
        "Service instrumentation under /etc/systemd/system/ was removed.",
        "Service /etc/systemd/system/example-test.service; environment: TEST.",
        "Inspect `/etc/systemd/system/example-test.service` after qualification.",
        "Inspect /etc/systemd/system/example-test@one.service.d/22-node.conf.",
        "A normal warning\nwith a tab\tand Unicode: é.",
    ] {
        let mut native = annotation(message);
        native["path"] = json!("/etc/systemd/system/example-test.service.d/node22.conf");
        native["title"] = json!("Task-authorized task-local check");
        let evidence = acquire_text(vec![], vec![native], None).await;
        let item = &surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0];
        assert_eq!(item["message"], message);
        assert_eq!(
            item["path"],
            "/etc/systemd/system/example-test.service.d/node22.conf"
        );
        assert_eq!(item["title"], "Task-authorized task-local check");
        assert_eq!(item["text_redacted_or_truncated"], false);
        assert_eq!(evidence["required_surfaces_complete"], true);
        assert_eq!(evidence["warning_observation"], "observed");
    }
    for (message, altered) in [
        (
            "Task-authorized task-local service /etc/systemd/system/example-test.service.",
            false,
        ),
        ("Task-authorized check: password = synthetic-value", true),
    ] {
        let (github, _, task) = server_with_text(
            "execution",
            Some(vec![warning("legacy", message)]),
            Some(vec![]),
            None,
        )
        .await;
        let evidence = github
            .review_evidence(REPOSITORY, REPOSITORY, 25, SHA, WRITER)
            .await
            .unwrap();
        task.abort();
        let item = &surface(&evidence, "github_relay_execution_outcomes")["items"][0];
        assert_eq!(
            item["warning_summaries"][0],
            if altered {
                "[REDACTED_PROTECTED_CONTENT]"
            } else {
                message
            }
        );
        assert_eq!(item["text_redacted_or_truncated"], altered);
        assert_eq!(evidence["required_surfaces_complete"], !altered);
        assert_eq!(
            evidence["warning_observation"],
            if altered { "unknown" } else { "observed" }
        );
    }
}

fn synthetic_secrets() -> Vec<String> {
    let mut values: Vec<String> = [
        concat!("gh", "p_"),
        concat!("gh", "o_"),
        concat!("gh", "u_"),
        concat!("gh", "s_"),
        concat!("gh", "r_"),
        concat!("github", "_pat_"),
        concat!("sk", "-"),
        concat!("sk", "-proj-"),
        concat!("sk", "-svcacct-"),
    ]
    .iter()
    .map(|prefix| {
        let length = if prefix.starts_with("github") {
            82
        } else if prefix.starts_with("sk") {
            48
        } else {
            36
        };
        format!(
            "{prefix}{}",
            "aB9x".repeat(21).chars().take(length).collect::<String>()
        )
    })
    .collect();
    for prefix in [concat!("AK", "IA"), concat!("AS", "IA")] {
        values.push(format!("{prefix}{}", "A1B2".repeat(4)));
    }
    for value in values.clone() {
        values.push(format!("embedded{value}suffix"));
    }
    values.extend(
        [
            "Authorization: Basic c3ludGhldGljOm9ubHk=",
            "AUTHORIZATION \t: Bearer synthetic-value",
            "Bearer\tsynthetic-value",
            "bearer\nsynthetic-value",
            "password=synthetic-value",
            "PASSWORD = 'synthetic-value'",
            "\"password\" : \"synthetic-value\"",
            "'credential' : 'synthetic-value'",
            "credentials=synthetic-value",
            "token = synthetic-value",
            "secret : synthetic-value",
            "AWS_SECRET_ACCESS_KEY = synthetic-value",
            "api_key=synthetic-value",
            "apikey: synthetic-value",
            "private_key: synthetic-value",
            "protected diagnostics: synthetic-private-data",
            "protected_diagnostic: synthetic-private-data",
            "protected-diagnostic: synthetic-private-data",
            "synthetic-evidence-token",
            "test-jwt",
        ]
        .into_iter()
        .map(String::from),
    );
    values.push(format!(
        "{} PRIVATE KEY-----\nsynthetic-key-data",
        "-----BEGIN"
    ));
    values.push(format!("{}short-key", concat!("sk", "-")));
    values
}

#[tokio::test]
async fn plausible_credentials_and_mixed_protected_content_never_escape_in_warning_text() {
    for (index, secret) in synthetic_secrets().iter().enumerate() {
        for context in [
            "Task-authorized check",
            "Task-authorized check of /etc/systemd/system/example-test.service",
        ] {
            let message = format!("{context}: ({secret}); task-local follow-up.");
            // Typed authority rejects controls before projection; exercise header
            // whitespace in annotations and its single-line Outcome equivalent.
            let outcome_message = message.replace(['\n', '\t'], " ");
            let evidence = acquire_text(
                vec![
                    warning("sensitive", &outcome_message),
                    warning("benign", "Safe warning retained."),
                ],
                vec![annotation(&message)],
                None,
            )
            .await;
            let outcome = &surface(&evidence, "github_relay_execution_outcomes")["items"][0];
            assert_eq!(
                outcome["warning_summaries"][0], "[REDACTED_PROTECTED_CONTENT]",
                "case {index}"
            );
            assert!(outcome["warning_summaries"][1]
                .as_str()
                .unwrap()
                .contains("Safe warning retained."));
            assert_eq!(outcome["text_redacted_or_truncated"], true);
            let item =
                &surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0];
            assert_eq!(
                item["message"], "[REDACTED_PROTECTED_CONTENT]",
                "case {index}"
            );
            assert_eq!(item["text_redacted_or_truncated"], true);
            assert!(!evidence.to_string().contains(secret), "case {index}");
            assert_eq!(evidence["required_surfaces_complete"], false);
            assert_eq!(evidence["warning_observation"], "unknown");
        }
    }
}

#[tokio::test]
async fn protected_paths_and_unit_contents_are_not_declassified_by_a_safe_reference() {
    for protected in [
        "/etc/relay-example/consumer.json",
        "/etc/shadow",
        "/var/lib/relay-example/diagnostics/run.json",
        "/run/credentials/example/token",
        "/home/example/.aws/credentials",
        "/etc/systemd/system/../shadow",
        "/etc/systemd/system/example.service.d/../../shadow",
        "/etc/systemd/system/example.service/extra",
        "/etc/systemd/system/example.service.d/extra/file.conf",
        "/etc/systemd/system/example.service.d/secret.env",
        "/etc/systemd/system/example.service.d/.private.conf",
        "/etc/systemd/system/example.service.d/%2e%2e.conf",
        "/etc/systemd/system/example.service\\private",
        "/etc/systemd/system/example.service..",
        "/etc/systemd/system/example.service.d/node.conf/",
        "[Service]\nOpaqueSetting=synthetic-private-data",
        "[Unit]\nDescription=synthetic-private-data",
        "[Install]\nWantedBy=synthetic-private-data",
        "Environment=OPAQUE=synthetic-private-data",
        "EnvironmentFile=synthetic-private-data",
        "ExecStart=/opt/private-command synthetic-private-data",
        "ExecStartPre=synthetic-private-data",
        "ExecStartPost=synthetic-private-data",
        "LoadCredential=synthetic-private-data",
        "SetCredential=synthetic-private-data",
        "ImportCredential=synthetic-private-data",
        "WorkingDirectory=/opt/synthetic-private-data",
        "UnrecognizedDirective=synthetic-private-data",
    ] {
        let message = format!(
            "Task-authorized /etc/systemd/system/example-test.service.d/node22.conf; {protected}"
        );
        let evidence = acquire_text(
            vec![warning("protected", &message.replace('\n', " "))],
            vec![annotation(&message)],
            None,
        )
        .await;
        assert_eq!(
            surface(&evidence, "github_relay_execution_outcomes")["items"][0]["warning_summaries"]
                [0],
            "[REDACTED_PROTECTED_CONTENT]",
            "{protected}"
        );
        assert_eq!(
            surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0]
                ["message"],
            "[REDACTED_PROTECTED_CONTENT]",
            "{protected}"
        );
        assert_eq!(evidence["required_surfaces_complete"], false);
        assert_eq!(evidence["warning_observation"], "unknown");
    }
}

#[tokio::test]
async fn credentials_are_checked_before_truncation_and_after_control_removal() {
    let key = format!("{}{}", concat!("sk", "-proj-"), "aB9x".repeat(20));
    for secret in ["synthetic-evidence-token", "test-jwt", &key] {
        for offset in [2030, 2040, 2050] {
            let message = format!("{}{secret}embedded-tail", "x".repeat(offset));
            let evidence = acquire_text(
                vec![warning("boundary", &message)],
                vec![annotation(&message)],
                None,
            )
            .await;
            assert_eq!(
                surface(&evidence, "github_relay_execution_outcomes")["items"][0]
                    ["warning_summaries"][0],
                "[REDACTED_PROTECTED_CONTENT]"
            );
            assert_eq!(
                surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0]
                    ["message"],
                "[REDACTED_PROTECTED_CONTENT]"
            );
            assert_eq!(evidence["required_surfaces_complete"], false);
            assert_eq!(evidence["warning_observation"], "unknown");
        }
        for offset in [95, 250, 260] {
            let message = format!("{}{secret}", "x".repeat(offset));
            let mut native = annotation("Safe message retained.");
            native["title"] = json!(message);
            native["path"] = json!(message);
            let evidence = acquire_text(vec![], vec![native], Some(message)).await;
            for source in [
                "github_actions_workflow_runs",
                "github_relay_execution_workflow_runs",
                "github_check_runs",
            ] {
                let item = &surface(&evidence, source)["items"][0];
                assert_eq!(item["name"], "[REDACTED_PROTECTED_CONTENT]");
                assert_eq!(item["text_redacted_or_truncated"], true);
            }
            let check = &surface(&evidence, "github_check_runs")["items"][0];
            assert_eq!(check["app_slug"], "[REDACTED_PROTECTED_CONTENT]");
            assert_eq!(
                check["annotations"]["items"][0]["title"],
                "[REDACTED_PROTECTED_CONTENT]"
            );
            assert_eq!(
                check["annotations"]["items"][0]["path"],
                "[REDACTED_PROTECTED_CONTENT]"
            );
            assert_eq!(
                check["annotations"]["items"][0]["message"],
                "Safe message retained."
            );
            assert_eq!(evidence["required_surfaces_complete"], false);
            assert_eq!(evidence["warning_observation"], "unknown");
        }
    }
    for message in [
        "synthetic-evi\0dence-token".to_owned(),
        "test-\rjwt".to_owned(),
        format!("g\0{}{}", "hp_", "aB9x".repeat(20)),
        format!("s\0{}{}", "k-proj-", "aB9x".repeat(20)),
        "pass\0word = synthetic-value".to_owned(),
    ] {
        let evidence = acquire_text(vec![], vec![annotation(&message)], None).await;
        assert_eq!(
            surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0]
                ["message"],
            "[REDACTED_PROTECTED_CONTENT]"
        );
        assert_eq!(evidence["required_surfaces_complete"], false);
        assert_eq!(evidence["warning_observation"], "unknown");
    }
}

#[tokio::test]
async fn every_warning_field_is_sanitized_and_genuine_loss_remains_unknown() {
    for field in [
        "source",
        "impact",
        "resolution",
        "next_action",
        "evidence_gaps",
    ] {
        let mut native = warning("field-check", "Safe warning.");
        native[field] = if field == "evidence_gaps" {
            json!(["synthetic-evidence-token"])
        } else {
            json!("synthetic-evidence-token")
        };
        let evidence = acquire_text(vec![native], vec![], None).await;
        let outcome = &surface(&evidence, "github_relay_execution_outcomes")["items"][0];
        assert_eq!(
            outcome["warning_summaries"][0], "[REDACTED_PROTECTED_CONTENT]",
            "{field}"
        );
        assert_eq!(outcome["text_redacted_or_truncated"], true);
        assert_eq!(evidence["required_surfaces_complete"], false);
        assert_eq!(evidence["warning_observation"], "unknown");
    }
    let message = "é".repeat(1200);
    let evidence = acquire_text(
        vec![warning("loss", &message)],
        vec![annotation(&message)],
        None,
    )
    .await;
    let outcome = &surface(&evidence, "github_relay_execution_outcomes")["items"][0];
    let item = &surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0];
    assert!(outcome["warning_summaries"][0].as_str().unwrap().len() <= 2048);
    assert_eq!(item["message"], "é".repeat(1024));
    assert_eq!(outcome["text_redacted_or_truncated"], true);
    assert_eq!(item["text_redacted_or_truncated"], true);
    assert_eq!(evidence["required_surfaces_complete"], false);
    assert_eq!(evidence["warning_observation"], "unknown");

    let message = "Safe\0warning\r retained.";
    let evidence = acquire_text(
        vec![warning("invalid-authority", message)],
        vec![annotation(message)],
        None,
    )
    .await;
    let outcomes = surface(&evidence, "github_relay_execution_outcomes");
    assert!(outcomes["items"].as_array().unwrap().is_empty());
    assert_eq!(outcomes["reason"], "GITHUB_RESPONSE_INVALID");
    let item = &surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0];
    assert_eq!(item["message"], "Safewarning retained.");
    assert_eq!(item["text_redacted_or_truncated"], true);
    assert_eq!(evidence["required_surfaces_complete"], false);
    assert_eq!(evidence["warning_observation"], "unknown");
    let warnings = (0..11)
        .map(|index| warning(&format!("warning-{index}"), "Safe warning."))
        .collect();
    let evidence = acquire_text(warnings, vec![], None).await;
    let outcome = &surface(&evidence, "github_relay_execution_outcomes")["items"][0];
    assert_eq!(outcome["warning_summaries"].as_array().unwrap().len(), 10);
    assert_eq!(outcome["text_redacted_or_truncated"], true);
    assert_eq!(evidence["required_surfaces_complete"], false);
    assert_eq!(evidence["warning_observation"], "unknown");

    // A large repeated path cannot turn reference recognition into unbounded
    // suffix scans; it remains one protected annotation within the byte budget.
    let evidence = acquire_text(
        vec![],
        vec![annotation(&"/etc/systemd/system/".repeat(4000))],
        None,
    )
    .await;
    let item = &surface(&evidence, "github_check_runs")["items"][0]["annotations"]["items"][0];
    assert_eq!(item["message"], "[REDACTED_PROTECTED_CONTENT]");
    assert_eq!(item["text_redacted_or_truncated"], true);
    assert_eq!(evidence["required_surfaces_complete"], false);
    assert_eq!(evidence["warning_observation"], "unknown");

    let mut notice = annotation("synthetic-evidence-token");
    notice["annotation_level"] = json!("notice");
    let evidence = acquire_text(vec![], vec![notice], None).await;
    assert_eq!(evidence["observed_check_annotation_warnings"], 0);
    assert_eq!(evidence["required_surfaces_complete"], false);
    assert_eq!(evidence["warning_observation"], "unknown");
}
