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
        recovered["structuredContent"]["pr_lifecycle"],
        json!({"operation":"begin-remediation","prNumber":25,"reviewId":1,"head":HEAD})
    );
    state.pr.lock().unwrap().as_mut().unwrap()["draft"] = json!(true);
    let replay = publish(&http, &url, &cr).await;
    assert_ne!(replay["isError"], true, "{replay}");
    assert_eq!(
        replay["structuredContent"]["pr_lifecycle"],
        recovered["structuredContent"]["pr_lifecycle"]
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
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
        &BTreeSet::from([TEST_REPOSITORY.into()]),
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
            &BTreeSet::from([TEST_REPOSITORY.into()]),
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

// These mocks implement native page/offset semantics. The older transport fixture
// intentionally returns one array and cannot exercise byte-driven page reduction.
mod pagination {
    use super::*;
    use std::collections::BTreeMap;

    #[derive(Clone, Debug, PartialEq, Eq)]
    struct PageRead {
        path: String,
        size: usize,
        page: usize,
    }

    #[derive(Clone)]
    struct PageReply {
        status: StatusCode,
        body: String,
        link: Option<String>,
    }

    #[derive(Clone)]
    struct Pages {
        native: MockState,
        sources: Arc<Mutex<BTreeMap<String, Vec<Value>>>>,
        overrides: Arc<Mutex<BTreeMap<(String, usize, usize), PageReply>>>,
        reads: Arc<Mutex<Vec<PageRead>>>,
    }

    impl Pages {
        fn new(native: MockState) -> Self {
            Self {
                native,
                sources: Default::default(),
                overrides: Default::default(),
                reads: Default::default(),
            }
        }

        fn source(&self, path: &str, records: Vec<Value>) {
            self.sources.lock().unwrap().insert(path.into(), records);
        }

        fn reply(&self, path: &str, size: usize, page: usize, reply: PageReply) {
            self.overrides
                .lock()
                .unwrap()
                .insert((path.into(), size, page), reply);
        }
    }

    fn list_path(source: &str, parent: u64) -> String {
        match source {
            "comments" => format!("issues/{parent}/comments"),
            "reviews" => format!("pulls/{parent}/reviews"),
            "artifacts" => "pulls".into(),
            _ => unreachable!(),
        }
    }

    fn records(count: usize, body_bytes: usize) -> Vec<Value> {
        (0..count)
            .map(|index| {
                json!({"id":10000 + index,"body":format!("Evidence {index}: {}", "x".repeat(body_bytes)),
                    "user":{"login":"example-owner","id":1,"type":"User"}})
            })
            .collect()
    }

    async fn paged_github(
        State(state): State<Pages>,
        headers: HeaderMap,
        method: Method,
        uri: Uri,
        body: axum::body::Bytes,
    ) -> axum::response::Response {
        let prefix = format!("/repos/{TEST_REPOSITORY}/");
        let path = uri.path().strip_prefix(&prefix).unwrap_or(uri.path());
        let collection = method == Method::GET
            && (path == "pulls"
                || path.ends_with("/comments") && path.starts_with("issues/")
                || path.ends_with("/reviews") && path.starts_with("pulls/"));
        if !collection {
            return mock_github(State(state.native), headers, method, uri, body).await;
        }
        if headers
            .get("user-agent")
            .and_then(|value| value.to_str().ok())
            != Some(github::USER_AGENT)
            || headers
                .get("authorization")
                .and_then(|value| value.to_str().ok())
                != Some("Bearer mock-installation-token")
        {
            return StatusCode::FORBIDDEN.into_response();
        }
        let query: BTreeMap<_, _> = uri
            .query()
            .unwrap_or("")
            .split('&')
            .filter_map(|field| field.split_once('='))
            .collect();
        let size = query.get("per_page").unwrap().parse::<usize>().unwrap();
        let page = query.get("page").unwrap().parse::<usize>().unwrap();
        assert!(matches!(size, 1 | 5 | 25 | 50 | 100));
        assert!(page > 0);
        state.reads.lock().unwrap().push(PageRead {
            path: path.into(),
            size,
            page,
        });
        state
            .native
            .requests
            .lock()
            .unwrap()
            .push(format!("GET {}", uri.path()));
        if path == "pulls" {
            assert_eq!(query.get("state"), Some(&"all"));
            assert_eq!(query.get("base"), Some(&"main"));
            assert!(query.get("head").unwrap().starts_with("example-org"));
        }
        let override_reply = state
            .overrides
            .lock()
            .unwrap()
            .get(&(path.into(), size, page))
            .cloned();
        let reply = override_reply.unwrap_or_else(|| {
            let sources = state.sources.lock().unwrap();
            let values = sources.get(path).cloned().unwrap_or_else(|| match path {
                "issues/24/comments" => state.native.authority_comments.lock().unwrap().clone(),
                "issues/25/comments" => state.native.authority_pr_comments.lock().unwrap().clone(),
                _ => Vec::new(),
            });
            let start = (page - 1) * size;
            let items: Vec<_> = values.iter().skip(start).take(size).cloned().collect();
            PageReply {
                status: StatusCode::OK,
                body: serde_json::to_string(&items).unwrap(),
                link: (start + items.len() < values.len()).then(|| {
                    // A cursor supplied by GitHub is evidence of another page,
                    // never an endpoint the reader is allowed to follow.
                    "<http://127.0.0.1:1/untrusted-cursor>; rel=\"next\"".into()
                }),
            }
        });
        let mut response = (reply.status, reply.body).into_response();
        response.headers_mut().insert(
            "content-type",
            axum::http::HeaderValue::from_static("application/json"),
        );
        if let Some(link) = reply.link {
            response
                .headers_mut()
                .insert("link", axum::http::HeaderValue::from_str(&link).unwrap());
        }
        response
    }

    async fn paged_api(state: Pages) -> github::Github {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().fallback(any(paged_github)).with_state(state),
            )
            .await
            .unwrap();
        });
        github::Github::mock_api(format!("http://{address}"))
    }

    async fn paged_client(state: Pages) -> (reqwest::Client, String) {
        let github = paged_api(state.clone()).await;
        let app = router(App {
            policy: state.native.policy.clone(),
            repositories: BTreeSet::from([TEST_REPOSITORY.into()]),
            observed_arguments: state.native.observed_arguments.clone(),
            enabled: true,
            store: Arc::new(Mutex::new(store::Store::open(":memory:").unwrap())),
            github,
            trusted_client_ca: Arc::new(Vec::new()),
        });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (reqwest::Client::new(), format!("http://{address}/mcp"))
    }

    async fn collect(
        github: &github::Github,
        source: &str,
        parent: u64,
    ) -> Result<Vec<Value>, &'static str> {
        match source {
            "comments" => github.authority_comments(TEST_REPOSITORY, parent).await,
            "reviews" => github.authority_reviews(TEST_REPOSITORY, parent).await,
            "artifacts" => {
                github
                    .authority_artifacts(TEST_REPOSITORY, "main", "codex/task-24")
                    .await
            }
            _ => unreachable!(),
        }
    }

    #[tokio::test]
    async fn task84_and_task109_synthetic_histories_exceed_one_response_without_losing_records() {
        for (task, count, bytes) in [(84, 37, 12000), (109, 23, 16000)] {
            let state = Pages::new(admitted());
            let expected = records(count, bytes);
            assert!(serde_json::to_vec(&expected).unwrap().len() > 262144);
            state.source(&list_path("comments", task), expected.clone());
            let github = paged_api(state.clone()).await;
            assert_eq!(collect(&github, "comments", task).await.unwrap(), expected);
            let reads = state.reads.lock().unwrap();
            assert!(reads.iter().any(|read| read.size == 5));
            assert!(reads
                .iter()
                .all(|read| read.path == list_path("comments", task)));
        }
    }

    #[tokio::test]
    async fn every_native_collection_preserves_order_and_exact_record_capacity() {
        for source in ["comments", "reviews", "artifacts"] {
            for count in [0, 1, 99, 100, 101, 499, 500, 501] {
                let state = Pages::new(admitted());
                let mut expected = records(count, 16);
                if source == "artifacts" {
                    // Pull-list order is native API order, not ascending ID order.
                    expected.reverse();
                }
                state.source(&list_path(source, 24), expected.clone());
                let github = paged_api(state.clone()).await;
                let collected = collect(&github, source, 24).await;
                if count > 500 {
                    assert_eq!(collected, Err("AUTHORITY_SOURCE_TRUNCATED"), "{source}");
                } else {
                    assert_eq!(collected.unwrap(), expected, "{source}/{count}");
                }
                if count == 500 {
                    assert!(
                        state
                            .reads
                            .lock()
                            .unwrap()
                            .iter()
                            .any(|read| { (read.page - 1) * read.size == 500 }),
                        "{source}: completion needs a sentinel read"
                    );
                }
            }
        }
    }

    #[tokio::test]
    async fn reduction_after_a_complete_page_retries_only_the_unread_offset() {
        let state = Pages::new(admitted());
        let mut expected = records(100, 16);
        expected.extend(records(37, 12000).into_iter().map(|mut value| {
            value["id"] = json!(value["id"].as_u64().unwrap() + 100);
            value
        }));
        state.source("issues/24/comments", expected.clone());
        let github = paged_api(state.clone()).await;
        assert_eq!(collect(&github, "comments", 24).await.unwrap(), expected);
        let reads = state.reads.lock().unwrap();
        assert_eq!((reads[0].size, reads[0].page), (100, 1));
        assert_eq!((reads[1].size, reads[1].page), (100, 2));
        assert!(reads.iter().any(|read| read.size < 100));
        assert!(reads
            .iter()
            .skip(1)
            .all(|read| (read.page - 1) * read.size >= 100));
    }

    #[tokio::test]
    async fn reduced_page_size_still_accepts_exactly_500_records_with_completion_proof() {
        let state = Pages::new(admitted());
        let expected = records(500, 11000);
        state.source("issues/24/comments", expected.clone());
        let github = paged_api(state.clone()).await;
        assert_eq!(collect(&github, "comments", 24).await.unwrap(), expected);
        let reads = state.reads.lock().unwrap();
        assert_eq!(
            (reads.last().unwrap().size, reads.last().unwrap().page),
            (5, 101)
        );
        assert!(reads.len() <= 505);
    }

    #[tokio::test]
    async fn oversized_record_and_aggregate_budget_have_distinct_errors() {
        for (count, bytes, error) in [
            (1, 262144, "AUTHORITY_SOURCE_TOO_LARGE"),
            (500, 15700, "AUTHORITY_COLLECTION_BUDGET_EXCEEDED"),
        ] {
            let state = Pages::new(admitted());
            let source = records(count, bytes);
            if count == 500 {
                // The source itself fits the aggregate bound. Failed oversized
                // attempts also consume transferred bytes and exhaust it.
                assert!(serde_json::to_vec(&source).unwrap().len() < 8 * 1024 * 1024);
            }
            state.source("issues/24/comments", source);
            let github = paged_api(state.clone()).await;
            assert_eq!(collect(&github, "comments", 24).await, Err(error));
            assert!(state.reads.lock().unwrap().len() <= 505);
            if count == 1 {
                assert_eq!(state.reads.lock().unwrap().last().unwrap().size, 1);
            }
        }
    }

    #[tokio::test]
    async fn incomplete_invalid_duplicate_and_failed_pages_never_return_a_prefix() {
        for (failure, error) in [
            ("api", "AUTHORITY_SOURCE_UNAVAILABLE"),
            ("json", "AUTHORITY_SOURCE_INVALID"),
            ("shape", "AUTHORITY_SOURCE_INVALID"),
            ("many", "AUTHORITY_SOURCE_INVALID"),
            ("duplicate", "AUTHORITY_SOURCE_INVALID"),
            ("missing-id", "AUTHORITY_SOURCE_INVALID"),
            ("incomplete", "AUTHORITY_SOURCE_TRUNCATED"),
        ] {
            let state = Pages::new(admitted());
            let expected = records(101, 16);
            state.source("issues/24/comments", expected.clone());
            let mut reply = PageReply {
                status: StatusCode::OK,
                body: "[]".into(),
                link: None,
            };
            match failure {
                "api" => reply.status = StatusCode::SERVICE_UNAVAILABLE,
                "json" => reply.body = "[{".into(),
                "shape" => reply.body = "{}".into(),
                "many" => reply.body = serde_json::to_string(&records(101, 0)).unwrap(),
                "duplicate" => {
                    reply.body = serde_json::to_string(&vec![expected[0].clone()]).unwrap()
                }
                "missing-id" => reply.body = "[{\"body\":\"Unverifiable native record\"}]".into(),
                "incomplete" => {
                    reply.link = Some("<http://127.0.0.1:1/do-not-follow>; rel=\"next\"".into())
                }
                _ => unreachable!(),
            }
            state.reply("issues/24/comments", 100, 2, reply);
            let github = paged_api(state.clone()).await;
            assert_eq!(
                collect(&github, "comments", 24).await,
                Err(error),
                "{failure}"
            );
            assert_eq!(state.reads.lock().unwrap().len(), 2, "{failure}");
        }
    }

    fn native_request(id: u64, record: &Value) -> Value {
        json!({"id":id,"body":crate::task_authority::render(record),
            "html_url":format!("https://github.com/{TEST_REPOSITORY}/issues/24#issuecomment-{id}"),
            "issue_url":format!("https://api.github.com/repos/{TEST_REPOSITORY}/issues/24"),
            "user":{"login":"example-reviewer[bot]","id":2,"type":"Bot"}})
    }

    #[tokio::test]
    async fn task_approval_verifies_late_request_outcome_and_large_history_before_publication() {
        for (count, bytes) in [(37, 12000), (23, 16000), (105, 16)] {
            let state = Pages::new(admitted());
            let mut comments = records(count, bytes);
            let native = native_request(1000, &request());
            let reference = source_ref(&native);
            comments.push(native);
            *state.native.authority_comments.lock().unwrap() = comments;
            let (outcome, result) = writer_outcome(&state.native, reference.clone());
            let candidate = approval(reference, outcome, result["result"].clone());
            let (http, url) = paged_client(state.clone()).await;
            let accepted = publish(&http, &url, &candidate).await;
            assert_ne!(accepted["isError"], true, "{count}: {accepted}");
            assert_eq!(accepted["structuredContent"]["record"], candidate);
            assert_eq!(
                state.native.authority_comments.lock().unwrap().len(),
                count + 3
            );
            let requests = state.native.requests.lock().unwrap();
            for id in [1000, 2000] {
                assert!(
                    requests.iter().any(|path| path
                        == &format!("GET /repos/{TEST_REPOSITORY}/issues/comments/{id}")),
                    "native source {id} must be re-read"
                );
            }
            assert_eq!(
                requests
                    .iter()
                    .filter(|path| path.starts_with("POST ") && path.ends_with("/comments"))
                    .count(),
                1
            );
            assert!(state.native.reviews.lock().unwrap().is_empty());
        }
    }

    #[tokio::test]
    async fn paged_approval_rejects_stale_chain_wrong_actor_and_changed_digest_without_writes() {
        for failure in ["stale", "actor", "digest", "incomplete"] {
            let state = Pages::new(admitted());
            let native = native_request(1000, &request());
            let reference = source_ref(&native);
            let mut comments = vec![native];
            comments.extend(records(100, 16));
            *state.native.authority_comments.lock().unwrap() = comments;
            let (outcome, result) = writer_outcome(&state.native, reference.clone());
            let candidate = approval(reference.clone(), outcome, result["result"].clone());
            let error = match failure {
                "stale" => {
                    let mut successor = request();
                    successor["supersedes"] = reference;
                    successor["purpose"] = json!("Verify the remaining admitted evidence");
                    state
                        .native
                        .authority_comments
                        .lock()
                        .unwrap()
                        .push(native_request(3000, &successor));
                    "AUTHORITY_APPROVAL_STALE_REQUEST"
                }
                "actor" => {
                    state
                        .native
                        .authority_comments
                        .lock()
                        .unwrap()
                        .last_mut()
                        .unwrap()["user"]["id"] = json!(99);
                    "AUTHORITY_SOURCE_UNTRUSTED"
                }
                "digest" => {
                    state
                        .native
                        .authority_comments
                        .lock()
                        .unwrap()
                        .last_mut()
                        .unwrap()["body"] = json!("Changed native source");
                    "AUTHORITY_REFERENCE_CHANGED"
                }
                "incomplete" => {
                    state.reply(
                        "issues/24/comments",
                        100,
                        2,
                        PageReply {
                            status: StatusCode::OK,
                            body: "[]".into(),
                            link: Some("<http://127.0.0.1:1/untrusted>; rel=\"next\"".into()),
                        },
                    );
                    "AUTHORITY_SOURCE_TRUNCATED"
                }
                _ => unreachable!(),
            };
            let before = state.native.authority_comments.lock().unwrap().len();
            let (http, url) = paged_client(state.clone()).await;
            let rejected = publish(&http, &url, &candidate).await;
            assert_eq!(rejected["isError"], true, "{failure}: {rejected}");
            assert_eq!(
                rejected["content"][0]["text"], error,
                "{failure}: {rejected}"
            );
            assert_eq!(
                state.native.authority_comments.lock().unwrap().len(),
                before
            );
            assert!(!state
                .native
                .requests
                .lock()
                .unwrap()
                .iter()
                .any(|path| path.starts_with("POST ") && path.ends_with("/comments")));
        }
    }
}
