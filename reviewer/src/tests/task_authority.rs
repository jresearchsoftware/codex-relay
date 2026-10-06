//! Real MCP publication calls against bounded synthetic native GitHub records.
use super::*;

const CHARTER: &str = "Task 24: verify a bounded result.\nAuthority model: github-native-v1\nIssue closure policy: keep-open\nNo production mutation.";

fn admitted() -> MockState {
    let mut state = MockState::default();
    state.policy.github_native_authority_enabled = true;
    *state.issue.lock().unwrap() = Some(json!({"id":240,"number":24,"state":"open","body":CHARTER,
        "repository_url":format!("https://api.github.com/repos/{TEST_REPOSITORY}"),
        "user":{"login":"example-owner","id":1,"type":"User"},
        "labels":[{"name":"step-1"},{"name":"task"}]}));
    state
}

fn request() -> Value {
    json!({"schema_version":"3.0","kind":"task-request","repository":TEST_REPOSITORY,"task":24,
        "parent":{"kind":"issue","number":24},"charter_sha256":crate::task_authority::hash(CHARTER),
        "step":1,"route":"manual","purpose":"Qualify the admitted result","scope":["Verify the bounded evidence."],
        "model":"gpt-6.1-sol","effort":"xhigh","subagents":true,"validation":["diff-check"],
        "boundaries":["No production mutation."],"decisions":[],"context":[],"supersedes":null,
        "branch":null,"base_sha":null,"starting_head":null,"existing_pr":null,"issue_closure_policy":"keep-open"})
}

fn source_ref(comment: &Value) -> Value {
    json!({"kind":"issue-comment","id":comment["id"],"parent":{"kind":"issue","number":24},
        "sha256":crate::task_authority::hash(comment["body"].as_str().unwrap())})
}

fn writer_outcome(state: &MockState, request: Value) -> (Value, Value) {
    let result = json!({"kind":"qualification","revision":null,"identities":[{"kind":"qualification-run","id":"bounded-run-1"}]});
    let record = json!({"schema_version":"3.0","kind":"outcome","repository":TEST_REPOSITORY,"task":24,
        "parent":{"kind":"issue","number":24},"charter_sha256":crate::task_authority::hash(CHARTER),
        "request":request,"attempt":"run-10","status":"implemented","result":result,"warnings":[],
        "limitations":["Live deployment was outside this Task."],"summary":"The bounded qualification completed."});
    let native = json!({"id":2000,"body":crate::task_authority::render(&record),
        "html_url":format!("https://github.com/{TEST_REPOSITORY}/issues/24#issuecomment-2000"),
        "issue_url":format!("https://api.github.com/repos/{TEST_REPOSITORY}/issues/24"),
        "user":{"login":"example-writer[bot]","id":3,"type":"Bot"}});
    state
        .authority_comments
        .lock()
        .unwrap()
        .push(native.clone());
    (source_ref(&native), record)
}

fn approval(request: Value, outcome: Value, result: Value) -> Value {
    json!({"schema_version":"3.0","kind":"task-approval","repository":TEST_REPOSITORY,"task":24,
        "parent":{"kind":"issue","number":24},"charter_sha256":crate::task_authority::hash(CHARTER),
        "step":1,"request":request,"outcome":outcome,"result":result,"warnings":[],
        "limitations":["Live deployment was outside this Task."],"verdict":"APPROVE","summary":"The exact bounded result satisfies this Task Request."})
}

async fn publish(http: &reqwest::Client, url: &str, record: &Value) -> Value {
    rpc(http, url, 1, "tools/call", json!({"name":"publish_task_authority","arguments":{"repository":TEST_REPOSITORY,"record":record}})).await["result"].clone()
}

#[test]
fn rust_and_node_render_exact_same_typed_record() {
    let input: Value = serde_json::from_str(include_str!(
        "../../../contracts/test/fixtures/github-task-request-v3-input.json"
    ))
    .unwrap();
    crate::task_authority::validate_record(&input).unwrap();
    assert_eq!(
        crate::task_authority::render(&input),
        include_str!("../../../contracts/test/fixtures/github-task-request-v3.md")
    );
}

#[tokio::test]
async fn no_pr_task_has_trusted_result_approval_and_idempotent_native_identity() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let first = publish(&http, &url, &request()).await;
    assert_ne!(first["isError"], true, "{first}");
    let reference = first["structuredContent"]["reference"].clone();
    assert_eq!(reference["id"], 1000);
    let duplicate = publish(&http, &url, &request()).await;
    assert_eq!(duplicate["content"][0]["text"], "DUPLICATE_SUPPRESSED");
    assert_eq!(state.authority_comments.lock().unwrap().len(), 1);
    let (outcome, result) = writer_outcome(&state, reference.clone());
    let accepted = publish(
        &http,
        &url,
        &approval(reference, outcome, result["result"].clone()),
    )
    .await;
    assert_ne!(accepted["isError"], true, "{accepted}");
    assert_eq!(
        accepted["structuredContent"]["issue_closure_policy"],
        "keep-open"
    );
    assert_eq!(
        accepted["structuredContent"]["issue_closure_performed"],
        false
    );
    assert!(!state
        .requests
        .lock()
        .unwrap()
        .iter()
        .any(|path| path.contains("/pulls/")));
    assert!(state.reviews.lock().unwrap().is_empty());
}

#[tokio::test]
async fn closed_disposable_pr_context_does_not_require_reopening_for_approval() {
    let state = admitted();
    let mut pr = live_pr();
    pr["state"] = json!("closed");
    *state.pr.lock().unwrap() = Some(pr);
    let context = json!({"id":91,"body":"The disposable investigation is complete.",
        "pull_request_url":format!("https://api.github.com/repos/{TEST_REPOSITORY}/pulls/25"),
        "user":{"login":"example-owner","id":1,"type":"User"}});
    state
        .authority_sources
        .lock()
        .unwrap()
        .insert("pulls/comments/91".into(), context.clone());
    let mut requested = request();
    requested["context"] = json!([{"kind":"review-comment","id":91,"parent":{"kind":"pull_request","number":25},"sha256":crate::task_authority::hash(context["body"].as_str().unwrap())}]);
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let first = publish(&http, &url, &requested).await;
    assert_ne!(first["isError"], true, "{first}");
    assert_eq!(
        first["structuredContent"]["context_provenance"][0]["author"]["id"],
        1
    );
    let reference = first["structuredContent"]["reference"].clone();
    let (_, mut result) = writer_outcome(&state, reference.clone());
    result["parent"] = json!({"kind":"pull_request","number":25});
    let mut native = state.authority_comments.lock().unwrap().pop().unwrap();
    native["body"] = json!(crate::task_authority::render(&result));
    native["issue_url"] = json!(format!(
        "https://api.github.com/repos/{TEST_REPOSITORY}/issues/25"
    ));
    let outcome = json!({"kind":"issue-comment","id":native["id"],"parent":result["parent"],"sha256":crate::task_authority::hash(native["body"].as_str().unwrap())});
    state
        .authority_sources
        .lock()
        .unwrap()
        .insert("issues/comments/2000".into(), native);
    let accepted = publish(
        &http,
        &url,
        &approval(reference, outcome, result["result"].clone()),
    )
    .await;
    assert_ne!(accepted["isError"], true, "{accepted}");
    assert_eq!(
        state.pr.lock().unwrap().as_ref().unwrap()["state"],
        "closed"
    );
    assert!(!state
        .requests
        .lock()
        .unwrap()
        .iter()
        .any(|path| path.starts_with("PATCH ") && path.contains("/pulls/")));
}

#[tokio::test]
async fn ambiguous_publication_recovers_existing_native_comment_and_never_blind_retries() {
    for mode in ["ambiguous", "missing"] {
        let state = admitted();
        *state.authority_publication_mode.lock().unwrap() = Some(mode.into());
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let first = publish(&http, &url, &request()).await;
        assert_eq!(first["isError"], true);
        let second = publish(&http, &url, &request()).await;
        if mode == "ambiguous" {
            assert_eq!(
                second["content"][0]["text"], "AUTHORITY_RECOVERED",
                "{second}"
            );
            assert_eq!(state.authority_comments.lock().unwrap().len(), 1);
        } else {
            assert_eq!(
                second["content"][0]["text"],
                "AUTHORITY_PUBLICATION_UNCERTAIN"
            );
            assert!(state.authority_comments.lock().unwrap().is_empty());
        }
        assert_eq!(
            state
                .requests
                .lock()
                .unwrap()
                .iter()
                .filter(|path| *path == "POST /repos/example-org/sample-project/issues/24/comments")
                .count(),
            1
        );
    }
}

#[tokio::test]
async fn superseded_request_wrong_result_or_writer_identity_cannot_be_approved() {
    for failure in [
        "superseded",
        "result",
        "writer",
        "unrelated-outcome",
        "limits",
    ] {
        let state = admitted();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let first = publish(&http, &url, &request()).await;
        let reference = first["structuredContent"]["reference"].clone();
        let (outcome, result) = writer_outcome(&state, reference.clone());
        let mut review = approval(reference.clone(), outcome, result["result"].clone());
        match failure {
            "superseded" => {
                let mut next = request();
                next["purpose"] = json!("Verify the remaining result");
                next["supersedes"] = reference;
                let next = publish(&http, &url, &next).await;
                assert_ne!(next["isError"], true, "{next}");
            }
            "result" => review["result"]["identities"][0]["id"] = json!("unrelated-run"),
            "writer" => {
                let mut comments = state.authority_comments.lock().unwrap();
                comments[1]["user"]["id"] = json!(999);
            }
            "unrelated-outcome" => {
                let mut altered = result.clone();
                altered["request"]["id"] = json!(99);
                let mut comments = state.authority_comments.lock().unwrap();
                comments[1]["body"] = json!(crate::task_authority::render(&altered));
                review["outcome"] = source_ref(&comments[1]);
            }
            "limits" => review["limitations"] = json!([]),
            _ => unreachable!(),
        }
        let before = state.authority_comments.lock().unwrap().len();
        let rejected = publish(&http, &url, &review).await;
        assert_eq!(rejected["isError"], true, "{failure}: {rejected}");
        assert_eq!(state.authority_comments.lock().unwrap().len(), before);
    }
}

#[tokio::test]
async fn typed_findings_are_durable_evidence_then_next_request_not_an_executable_cr() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let first = publish(&http, &url, &request()).await;
    let reference = first["structuredContent"]["reference"].clone();
    let (outcome, result) = writer_outcome(&state, reference.clone());
    let mut findings = approval(reference.clone(), outcome, result["result"].clone());
    findings["kind"] = json!("task-review");
    findings["verdict"] = json!("REQUEST_CHANGES");
    findings["findings"] = json!([{"id":"F1","severity":"major","problem":"Qualification evidence omits one required bound.","impact":"The acceptance requirement is unresolved.","remediation":"Record the missing bounded evidence.","acceptance_criteria":["The bound is documented."]}]);
    let review = publish(&http, &url, &findings).await;
    assert_ne!(review["isError"], true, "{review}");
    let mut next = request();
    next["purpose"] = json!("Complete remaining qualification evidence");
    next["supersedes"] = reference;
    next["step"] = json!(2);
    next["context"] = json!([review["structuredContent"]["reference"]]);
    let next = publish(&http, &url, &next).await;
    assert_ne!(next["isError"], true, "{next}");
    assert_eq!(
        state.issue.lock().unwrap().as_ref().unwrap()["labels"],
        json!([{"name":"task"},{"name":"step-2"}])
    );
    assert!(state.reviews.lock().unwrap().is_empty());
}

#[tokio::test]
async fn reference_digest_and_native_parent_are_rechecked_before_mutation() {
    for field in ["body", "issue_url", "id"] {
        let state = admitted();
        let original = json!({"id":50,"body":"Selected owner evidence.","issue_url":format!("https://api.github.com/repos/{TEST_REPOSITORY}/issues/24"),"user":{"login":"example-owner","id":1,"type":"User"}});
        let mut changed = original.clone();
        changed[field] = if field == "id" {
            json!(51)
        } else {
            json!("altered-source")
        };
        state
            .authority_sources
            .lock()
            .unwrap()
            .insert("issues/comments/50".into(), changed);
        let mut selected = request();
        selected["context"] = json!([source_ref(&original)]);
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let result = publish(&http, &url, &selected).await;
        assert_eq!(result["isError"], true, "{field}: {result}");
        assert!(state.authority_comments.lock().unwrap().is_empty());
    }
}

#[tokio::test]
async fn typed_pr_cr_uses_native_review_check_and_recoverable_step_projection() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let mut initial = request();
    initial["route"] = json!("auto");
    initial["branch"] = json!("codex/task-24");
    initial["base_sha"] = json!("b".repeat(40));
    initial["starting_head"] = json!(HEAD);
    initial["existing_pr"] = json!(25);
    let first = publish(&http, &url, &initial).await;
    assert_ne!(first["isError"], true, "{first}");
    let mut cr = initial;
    cr["kind"] = json!("change-request");
    cr["parent"] = json!({"kind":"pull_request","number":25});
    cr["step"] = json!(2);
    cr["supersedes"] = first["structuredContent"]["reference"].clone();
    cr["change_request_id"] = json!("CR-24-001");
    cr["reviewed_head_sha"] = json!(HEAD);
    cr["purpose"] = json!("Repair the admitted PR defect");
    cr["findings"] = json!([{"id":"F1","severity":"major","problem":"The candidate violates the input bound.","impact":"The existing contract cannot be approved.","remediation":"Enforce the admitted input bound.","acceptance_criteria":["The bounded case passes."]}]);
    *state.metadata_failure.lock().unwrap() = Some("issues/24/labels".into());
    let partial = publish(&http, &url, &cr).await;
    assert_eq!(
        partial["content"][0]["text"], "AUTHORITY_PUBLISHED_METADATA_FAILED",
        "{partial}"
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
    let recovered = publish(&http, &url, &cr).await;
    assert_eq!(
        recovered["content"][0]["text"], "AUTHORITY_RECOVERED",
        "{recovered}"
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
    assert_eq!(
        recovered["structuredContent"]["reference"]["kind"],
        "review"
    );
    assert_eq!(recovered["structuredContent"]["check"]["head_sha"], HEAD);
    assert_eq!(
        state.issue.lock().unwrap().as_ref().unwrap()["labels"],
        json!([{"name":"task"},{"name":"step-2"}])
    );
    assert_eq!(
        state.pr.lock().unwrap().as_ref().unwrap()["labels"],
        json!([{"name":"step-2"}])
    );
    assert!(state.pr.lock().unwrap().as_ref().unwrap()["title"]
        .as_str()
        .unwrap()
        .starts_with("Task 24 · Step 2 · CR-24-001"));
}

#[tokio::test]
async fn typed_charter_rejects_legacy_cr_writer_but_preserves_native_approve() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let rejected = rpc(
        &http,
        &url,
        1,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":cr_fixture()}),
    )
    .await;
    assert_eq!(rejected["result"]["isError"], true, "{rejected}");
    assert!(state.reviews.lock().unwrap().is_empty());
    let approved = rpc(
        &http,
        &url,
        2,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
    )
    .await;
    assert_ne!(approved["result"]["isError"], true, "{approved}");
    let plan = &approved["result"]["structuredContent"]["post_review_continuation"];
    assert_eq!(plan["approved_head_sha"], HEAD);
    assert_eq!(plan["merge_method"], "squash");
    assert_eq!(plan["required_native_checks"], "must_pass_for_exact_head");
    assert_eq!(plan["close_issue_authorized"], false);
    assert_eq!(plan["execution_supported"], false);
    assert!(!state
        .requests
        .lock()
        .unwrap()
        .iter()
        .any(|path| path.contains("/merge")));
}

#[tokio::test]
async fn trusted_decisions_are_normalized_and_untrusted_or_superseded_sources_fail() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let decision = json!({"schema_version":"3.0","kind":"decision","repository":TEST_REPOSITORY,"task":24,
        "parent":{"kind":"issue","number":24},"charter_sha256":crate::task_authority::hash(CHARTER),
        "purpose":"Specify the selected validation purpose","amendments":{"purpose":"Validate the admitted native evidence"},"supersedes":null,"context":[]});
    let published = publish(&http, &url, &decision).await;
    assert_ne!(published["isError"], true, "{published}");
    let mut requested = request();
    requested["decisions"] = json!([published["structuredContent"]["reference"]]);
    let mismatch = publish(&http, &url, &requested).await;
    assert_eq!(
        mismatch["content"][0]["text"],
        "AUTHORITY_DECISION_NOT_NORMALIZED"
    );
    requested["purpose"] = decision["amendments"]["purpose"].clone();
    let accepted = publish(&http, &url, &requested).await;
    assert_ne!(accepted["isError"], true, "{accepted}");
    let mut next_decision = decision.clone();
    next_decision["supersedes"] = published["structuredContent"]["reference"].clone();
    next_decision["purpose"] = json!("Clarify the selected purpose");
    let next = publish(&http, &url, &next_decision).await;
    assert_ne!(next["isError"], true, "{next}");
    let mut next_request = requested.clone();
    next_request["supersedes"] = accepted["structuredContent"]["reference"].clone();
    let rejected = publish(&http, &url, &next_request).await;
    assert_eq!(
        rejected["content"][0]["text"],
        "AUTHORITY_DECISION_SUPERSEDED"
    );
    next_request["decisions"] = json!([next["structuredContent"]["reference"]]);
    state.authority_comments.lock().unwrap().last_mut().unwrap()["user"]["id"] = json!(99);
    let rejected = publish(&http, &url, &next_request).await;
    assert_eq!(rejected["content"][0]["text"], "AUTHORITY_SOURCE_UNTRUSTED");
}

#[tokio::test]
async fn typed_publisher_disabled_unknown_fields_and_writer_outcomes_fail_without_mutation() {
    let state = admitted();
    let (http, url) = client_with_state(false, None, state.clone()).await;
    let rejected = publish(&http, &url, &request()).await;
    assert_eq!(rejected["content"][0]["text"], "RELAY_DISABLED");
    assert!(state.requests.lock().unwrap().is_empty());
    let mut old_policy = admitted();
    old_policy.policy.github_native_authority_enabled = false;
    let (enabled_http, enabled_url) = client_with_state(true, None, old_policy.clone()).await;
    let old = publish(&enabled_http, &enabled_url, &request()).await;
    assert_eq!(
        old["content"][0]["text"],
        "GITHUB_NATIVE_AUTHORITY_NOT_ENABLED"
    );
    assert!(old_policy.requests.lock().unwrap().is_empty());
    let mut invalid = request();
    invalid["command"] = json!("arbitrary mutation");
    assert!(crate::task_authority::valid_input(
        TEST_REPOSITORY,
        &json!({"repository":TEST_REPOSITORY,"record":invalid})
    )
    .is_err());
    let (outcome, record) = writer_outcome(
        &state,
        json!({"kind":"issue-comment","id":99,"parent":{"kind":"issue","number":24},"sha256":"f".repeat(64)}),
    );
    let _ = outcome;
    assert_eq!(
        crate::task_authority::valid_input(
            TEST_REPOSITORY,
            &json!({"repository":TEST_REPOSITORY,"record":record})
        ),
        Err("WRITER_OUTCOME_PUBLICATION_FORBIDDEN")
    );
}

#[tokio::test]
async fn next_direction_requires_selected_current_task_decision_and_bounded_step() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let decision = json!({"schema_version":"3.0","kind":"decision","repository":TEST_REPOSITORY,"task":24,
        "parent":{"kind":"issue","number":24},"charter_sha256":crate::task_authority::hash(CHARTER),
        "purpose":"Continue the admitted qualification","amendments":{"purpose":"Verify the remaining evidence"},
        "supersedes":null,"context":[]});
    let published = publish(&http, &url, &decision).await;
    assert_ne!(published["isError"], true, "{published}");
    let reference = published["structuredContent"]["reference"].clone();
    let mut requested = request();
    requested["purpose"] = decision["amendments"]["purpose"].clone();
    requested["decisions"] = json!([reference]);
    requested["continuation"] = json!({"hold":false,"task_complete":false,
        "next":{"task":24,"direction":reference,"step":2}});
    for failure in ["unselected", "task", "parent", "step"] {
        let mut invalid = requested.clone();
        match failure {
            "unselected" => invalid["decisions"] = json!([]),
            "task" => invalid["continuation"]["next"]["task"] = json!(26),
            "parent" => {
                invalid["continuation"]["next"]["direction"]["parent"] =
                    json!({"kind":"pull_request","number":25})
            }
            "step" => invalid["continuation"]["next"]["step"] = json!(3),
            _ => unreachable!(),
        }
        let rejected = publish(&http, &url, &invalid).await;
        assert_eq!(
            rejected["content"][0]["text"], "AUTHORITY_NEXT_REFERENCE_INVALID",
            "{failure}: {rejected}"
        );
        assert_eq!(state.authority_comments.lock().unwrap().len(), 1);
    }
    let accepted = publish(&http, &url, &requested).await;
    assert_ne!(accepted["isError"], true, "{accepted}");
    assert_eq!(
        accepted["structuredContent"]["record"]["continuation"]["next"]["step"],
        2
    );
    assert!(state
        .requests
        .lock()
        .unwrap()
        .iter()
        .any(|path| path == "GET /repos/example-org/sample-project/issues/comments/1000"));
}

#[tokio::test]
async fn native_approve_continuation_binds_current_writer_result_and_respects_explicit_hold() {
    for hold in [false, true] {
        let state = admitted();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let mut requested = request();
        requested["route"] = json!("auto");
        requested["branch"] = json!("codex/task-24");
        requested["base_sha"] = json!("b".repeat(40));
        requested["starting_head"] = json!(HEAD);
        requested["existing_pr"] = json!(25);
        requested["continuation"] = json!({"hold":hold,"task_complete":true,"next":null});
        let first = publish(&http, &url, &requested).await;
        assert_ne!(first["isError"], true, "{first}");
        let (_, mut outcome) =
            writer_outcome(&state, first["structuredContent"]["reference"].clone());
        outcome["result"]["kind"] = json!("git");
        outcome["result"]["revision"] = json!(HEAD);
        state.authority_comments.lock().unwrap().last_mut().unwrap()["body"] =
            json!(crate::task_authority::render(&outcome));
        let approved = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
        )
        .await;
        let plan = &approved["result"]["structuredContent"]["post_review_continuation"];
        assert_eq!(plan["automatic_continuation_authorized"], !hold, "{plan}");
        assert_eq!(plan["hold"], hold);
        assert_eq!(plan["task_complete"], true);
        assert_eq!(plan["close_issue_authorized"], false);
        assert_eq!(plan["request_authority"]["outcome"]["id"], 2000);
        assert_eq!(plan["execution_supported"], false);
        assert!(!state
            .requests
            .lock()
            .unwrap()
            .iter()
            .any(|path| path.contains("/merge")));
    }
}

#[tokio::test]
async fn pr_scoped_decision_can_bind_existing_pr_request_without_promoting_fresh_task_scope() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let decision = json!({"schema_version":"3.0","kind":"decision","repository":TEST_REPOSITORY,"task":24,
        "parent":{"kind":"pull_request","number":25},"charter_sha256":crate::task_authority::hash(CHARTER),
        "purpose":"Bound the PR continuation","amendments":{"purpose":"Verify the existing PR result"},"supersedes":null,"context":[]});
    let published = publish(&http, &url, &decision).await;
    assert_ne!(published["isError"], true, "{published}");
    assert_eq!(
        published["structuredContent"]["reference"]["parent"]["kind"],
        "pull_request"
    );
    assert!(state.authority_comments.lock().unwrap().is_empty());
    assert_eq!(state.authority_pr_comments.lock().unwrap().len(), 1);
    let mut requested = request();
    requested["purpose"] = decision["amendments"]["purpose"].clone();
    requested["decisions"] = json!([published["structuredContent"]["reference"]]);
    let fresh = publish(&http, &url, &requested).await;
    assert_eq!(
        fresh["content"][0]["text"],
        "AUTHORITY_DECISION_SCOPE_MISMATCH"
    );
    requested["branch"] = json!("codex/task-24");
    requested["base_sha"] = json!("b".repeat(40));
    requested["starting_head"] = json!(HEAD);
    requested["existing_pr"] = json!(25);
    let bound = publish(&http, &url, &requested).await;
    assert_ne!(bound["isError"], true, "{bound}");
}

#[tokio::test]
async fn writer_created_artifact_cr_blocks_stale_approval_and_can_be_superseded_by_task_request() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let mut initial = request();
    initial["route"] = json!("auto");
    initial["branch"] = json!("codex/task-24");
    initial["base_sha"] = json!("b".repeat(40));
    initial["starting_head"] = json!(HEAD);
    let first = publish(&http, &url, &initial).await;
    assert_ne!(first["isError"], true, "{first}");
    let reference = first["structuredContent"]["reference"].clone();
    let mut artifact = live_pr();
    artifact["body"] = json!(format!(
        "Related to #24\nExecution request native ID: {}\nExecution request digest: {}",
        reference["id"],
        reference["sha256"].as_str().unwrap()
    ));
    *state.pr.lock().unwrap() = Some(artifact.clone());
    state
        .authority_sources
        .lock()
        .unwrap()
        .insert("pulls".into(), json!([artifact]));
    let (outcome, result) = writer_outcome(&state, reference.clone());
    let stale = approval(reference.clone(), outcome, result["result"].clone());
    let mut cr = initial;
    cr["kind"] = json!("change-request");
    cr["parent"] = json!({"kind":"pull_request","number":25});
    cr["step"] = json!(2);
    cr["supersedes"] = reference;
    cr["existing_pr"] = json!(25);
    cr["change_request_id"] = json!("CR-24-001");
    cr["reviewed_head_sha"] = json!(HEAD);
    cr["findings"] = json!([{"id":"F1","severity":"major","problem":"The artifact has an admitted defect.","impact":"Acceptance remains blocked.","remediation":"Repair the bounded defect.","acceptance_criteria":["The exact case passes."]}]);
    let change = publish(&http, &url, &cr).await;
    assert_ne!(change["isError"], true, "{change}");
    let rejected = publish(&http, &url, &stale).await;
    assert_eq!(
        rejected["content"][0]["text"],
        "AUTHORITY_APPROVAL_STALE_REQUEST"
    );
    let mut next = request();
    next["step"] = json!(2);
    next["supersedes"] = change["structuredContent"]["reference"].clone();
    let continued = publish(&http, &url, &next).await;
    assert_ne!(continued["isError"], true, "{continued}");
}
