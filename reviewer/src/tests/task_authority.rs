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

// Compatibility fixtures represent operations reserved before the current
// protocol was enabled, including retryable failures before a native POST.
fn retain_older_publication(store: &Arc<Mutex<store::Store>>, record: &Value) {
    if record["schema_version"] == "3.0"
        && matches!(
            record["kind"].as_str(),
            Some("decision" | "task-request" | "change-request")
        )
    {
        let operation = authority_operation(record);
        let store = store.lock().unwrap();
        if store.known(&operation).unwrap().is_none() {
            let body = format!(
                "{}\n<!-- jresearchsoftware-task-authority:v1 operation={operation} -->",
                crate::task_authority::render(record)
            );
            store
                .reserve_publication(&operation, "retained-publication", &body, &body)
                .unwrap();
            store.retryable_failure(&operation).unwrap();
        }
    }
}

async fn publish_retained(
    state: &MockState,
    http: &reqwest::Client,
    url: &str,
    record: &Value,
) -> Value {
    retain_older_publication(&state.store, record);
    publish_fresh(http, url, record).await
}

async fn publish_fresh(http: &reqwest::Client, url: &str, record: &Value) -> Value {
    rpc(http, url, 1, "tools/call", json!({"name":"publish_task_authority","arguments":{"repository":TEST_REPOSITORY,"record":record}})).await["result"].clone()
}

#[tokio::test]
async fn current_protocol_refuses_fresh_older_execution_authority_without_github_or_reservation() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let mut cr = request();
    cr["kind"] = json!("change-request");
    cr["parent"] = json!({"kind":"pull_request","number":25});
    cr["route"] = json!("auto");
    cr["step"] = json!(2);
    cr["branch"] = json!("codex/task-24");
    cr["base_sha"] = json!("b".repeat(40));
    cr["starting_head"] = json!(HEAD);
    cr["existing_pr"] = json!(25);
    cr["supersedes"] = json!({"kind":"issue-comment","id":1000,"parent":{"kind":"issue","number":24},"sha256":"f".repeat(64)});
    for field in [
        "purpose",
        "change_request_id",
        "reviewed_head_sha",
        "findings",
    ] {
        cr[field] = v4_cr()[field].clone();
    }
    let mut old_decision = decision_v4();
    old_decision["schema_version"] = json!("3.0");
    old_decision["amendments"] =
        json!({"purpose":"Retain the old independently admitted direction"});
    for record in [request(), cr, old_decision.clone()] {
        crate::task_authority::validate_record(&record).unwrap();
        for _ in 0..2 {
            let rejected = publish_fresh(&http, &url, &record).await;
            assert_eq!(
                rejected["content"][0]["text"], "CURRENT_PROTOCOL_REQUIRED",
                "{rejected}"
            );
            assert!(rejected["structuredContent"]["guidance"]
                .as_str()
                .unwrap()
                .contains("schema_version 4.0"));
        }
        assert!(state
            .store
            .lock()
            .unwrap()
            .known(&authority_operation(&record))
            .unwrap()
            .is_none());
    }
    let legacy = rpc(
        &http,
        &url,
        2,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":cr_fixture()}),
    )
    .await;
    assert_eq!(
        legacy["result"]["content"][0]["text"],
        "CURRENT_PROTOCOL_REQUIRED"
    );
    assert!(state
        .store
        .lock()
        .unwrap()
        .known(&operation_id(&[], &cr_fixture()))
        .unwrap()
        .is_none());
    assert!(state.requests.lock().unwrap().is_empty());
    assert!(state.authority_comments.lock().unwrap().is_empty());
    assert!(state.reviews.lock().unwrap().is_empty());
    let retained = publish_retained(&state, &http, &url, &old_decision).await;
    assert_ne!(retained["isError"], true, "{retained}");
    let duplicate = publish_fresh(&http, &url, &old_decision).await;
    assert_eq!(
        duplicate["content"][0]["text"], "DUPLICATE_SUPPRESSED",
        "{duplicate}"
    );
}

#[tokio::test]
async fn current_protocol_refuses_new_legacy_chain_on_unmarked_task_and_preserves_native_approval()
{
    let mut state = MockState::default();
    state.policy.github_native_authority_enabled = true;
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let legacy = rpc(
        &http,
        &url,
        1,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":cr_fixture()}),
    )
    .await;
    assert_eq!(
        legacy["result"]["content"][0]["text"],
        "CURRENT_PROTOCOL_REQUIRED"
    );
    assert!(state.requests.lock().unwrap().is_empty());
    let accepted = rpc(
        &http,
        &url,
        2,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
    )
    .await;
    assert_eq!(
        accepted["result"]["content"][0]["text"], "PUBLISHED",
        "{accepted}"
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn enabled_current_protocol_preserves_exact_legacy_reserved_partial_and_completed_operations()
{
    for phase in ["RESERVED", "REVIEW_PUBLISHED", "PUBLISHED"] {
        let mut state = MockState::default();
        let args = cr_fixture();
        let operation = operation_id(&[], &args);
        if phase == "RESERVED" {
            let body = native_review_body(&[], &args, &operation);
            state
                .store
                .lock()
                .unwrap()
                .reserve_publication(&operation, "retained-publication", &body, &body)
                .unwrap();
            let app = native_app(&state).await;
            step_sync::prepare(&app.target(&args).unwrap(), &operation, &args)
                .await
                .unwrap();
            state
                .reviews
                .lock()
                .unwrap()
                .push(json!({"commit_id":HEAD,"event":"REQUEST_CHANGES","body":body}));
        } else {
            if phase == "REVIEW_PUBLISHED" {
                *state.metadata_failure.lock().unwrap() = Some("issues/24/labels".into());
            }
            let (http, url) = client_with_state(true, None, state.clone()).await;
            let first = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(
                first["result"]["isError"] == true,
                phase == "REVIEW_PUBLISHED",
                "{first}"
            );
        }
        assert_eq!(
            state
                .store
                .lock()
                .unwrap()
                .known(&operation)
                .unwrap()
                .unwrap()
                .status,
            phase
        );
        let original_body = state.reviews.lock().unwrap()[0]["body"].clone();
        state.policy.github_native_authority_enabled = true;
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let before = state.requests.lock().unwrap().len();
        let recovered = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_ne!(recovered["result"]["isError"], true, "{phase}: {recovered}");
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
        assert_eq!(state.reviews.lock().unwrap()[0]["body"], original_body);
        assert!(!state.requests.lock().unwrap()[before..]
            .iter()
            .any(|path| path.starts_with("POST ") && path.ends_with("/reviews")));
        let mut changed = args.clone();
        changed["change_request"]["remediation_thread_title"] =
            json!("Task 24 — Step 2 — New work cannot reuse the old operation");
        let rejected = rpc(
            &http,
            &url,
            3,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":changed}),
        )
        .await;
        assert_eq!(
            rejected["result"]["content"][0]["text"],
            "CURRENT_PROTOCOL_REQUIRED"
        );
    }
}

#[test]
fn current_tool_descriptors_require_v4_new_work_and_preserve_older_recovery() {
    let listed = tools(&[], &BTreeSet::from([TEST_REPOSITORY.into()]));
    for name in ["publish_task_authority", "submit_pr_review"] {
        let descriptor = listed
            .as_array()
            .unwrap()
            .iter()
            .find(|tool| tool["name"] == name)
            .unwrap();
        let description = descriptor["description"].as_str().unwrap();
        for required in [
            "NEW",
            "schema_version 4.0",
            "qualified enabled typed capability",
            "never downgrade",
        ] {
            assert!(description.contains(required), "{name}: {description}");
        }
    }
}

#[test]
fn rust_and_node_render_exact_same_typed_record() {
    let input: Value = serde_json::from_str(include_str!(
        "../../../contracts/test/fixtures/github-task-request-v3-input.json"
    ))
    .unwrap();
    crate::task_authority::validate_record(&input).unwrap();
    assert_eq!(
        crate::task_authority::render_legacy(&input),
        include_str!("../../../contracts/test/fixtures/github-task-request-v3.md")
    );
}

#[tokio::test]
async fn no_pr_task_has_trusted_result_approval_and_idempotent_native_identity() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let first = publish_retained(&state, &http, &url, &request()).await;
    assert_ne!(first["isError"], true, "{first}");
    let reference = first["structuredContent"]["reference"].clone();
    assert_eq!(reference["id"], 1000);
    let duplicate = publish_retained(&state, &http, &url, &request()).await;
    assert_eq!(duplicate["content"][0]["text"], "DUPLICATE_SUPPRESSED");
    assert_eq!(state.authority_comments.lock().unwrap().len(), 1);
    let (outcome, result) = writer_outcome(&state, reference.clone());
    let accepted = publish_retained(
        &state,
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
    let first = publish_retained(&state, &http, &url, &requested).await;
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
    let accepted = publish_retained(
        &state,
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
        let first = publish_retained(&state, &http, &url, &request()).await;
        assert_eq!(first["isError"], true);
        let second = publish_retained(&state, &http, &url, &request()).await;
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
        let first = publish_retained(&state, &http, &url, &request()).await;
        let reference = first["structuredContent"]["reference"].clone();
        let (outcome, result) = writer_outcome(&state, reference.clone());
        let mut review = approval(reference.clone(), outcome, result["result"].clone());
        match failure {
            "superseded" => {
                let mut next = request();
                next["purpose"] = json!("Verify the remaining result");
                next["supersedes"] = reference;
                let next = publish_retained(&state, &http, &url, &next).await;
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
        let rejected = publish_retained(&state, &http, &url, &review).await;
        assert_eq!(rejected["isError"], true, "{failure}: {rejected}");
        assert_eq!(state.authority_comments.lock().unwrap().len(), before);
    }
}

#[tokio::test]
async fn typed_findings_are_durable_evidence_then_next_request_not_an_executable_cr() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let first = publish_retained(&state, &http, &url, &request()).await;
    let reference = first["structuredContent"]["reference"].clone();
    let (outcome, result) = writer_outcome(&state, reference.clone());
    let mut findings = approval(reference.clone(), outcome, result["result"].clone());
    findings["kind"] = json!("task-review");
    findings["verdict"] = json!("REQUEST_CHANGES");
    findings["findings"] = json!([{"id":"F1","severity":"major","problem":"Qualification evidence omits one required bound.","impact":"The acceptance requirement is unresolved.","remediation":"Record the missing bounded evidence.","acceptance_criteria":["The bound is documented."]}]);
    let review = publish_retained(&state, &http, &url, &findings).await;
    assert_ne!(review["isError"], true, "{review}");
    let mut next = request();
    next["purpose"] = json!("Complete remaining qualification evidence");
    next["supersedes"] = reference;
    next["step"] = json!(2);
    next["context"] = json!([review["structuredContent"]["reference"]]);
    let next = publish_retained(&state, &http, &url, &next).await;
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
        let result = publish_retained(&state, &http, &url, &selected).await;
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
    let first = publish_retained(&state, &http, &url, &initial).await;
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
    let partial = publish_retained(&state, &http, &url, &cr).await;
    assert_eq!(
        partial["content"][0]["text"], "AUTHORITY_PUBLISHED_METADATA_FAILED",
        "{partial}"
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
    let recovered = publish_retained(&state, &http, &url, &cr).await;
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
    let replay = publish_retained(&state, &http, &url, &cr).await;
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
    outcome_v4(
        &state,
        authority_v4(vec![], Value::Null, Value::Null),
        json!({"kind":"issue","number":24}),
        json!({"kind":"git","revision":HEAD,"identities":[]}),
    );
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
    assert!(plan.get("close_issue_authorized").is_none());
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
    let published = publish_retained(&state, &http, &url, &decision).await;
    assert_ne!(published["isError"], true, "{published}");
    let mut requested = request();
    requested["decisions"] = json!([published["structuredContent"]["reference"]]);
    let mismatch = publish_retained(&state, &http, &url, &requested).await;
    assert_eq!(
        mismatch["content"][0]["text"],
        "AUTHORITY_DECISION_NOT_NORMALIZED"
    );
    requested["purpose"] = decision["amendments"]["purpose"].clone();
    let accepted = publish_retained(&state, &http, &url, &requested).await;
    assert_ne!(accepted["isError"], true, "{accepted}");
    let mut next_decision = decision.clone();
    next_decision["supersedes"] = published["structuredContent"]["reference"].clone();
    next_decision["purpose"] = json!("Clarify the selected purpose");
    let next = publish_retained(&state, &http, &url, &next_decision).await;
    assert_ne!(next["isError"], true, "{next}");
    let mut next_request = requested.clone();
    next_request["supersedes"] = accepted["structuredContent"]["reference"].clone();
    let rejected = publish_retained(&state, &http, &url, &next_request).await;
    assert_eq!(
        rejected["content"][0]["text"],
        "AUTHORITY_DECISION_SUPERSEDED"
    );
    next_request["decisions"] = json!([next["structuredContent"]["reference"]]);
    state.authority_comments.lock().unwrap().last_mut().unwrap()["user"]["id"] = json!(99);
    let rejected = publish_retained(&state, &http, &url, &next_request).await;
    assert_eq!(rejected["content"][0]["text"], "AUTHORITY_SOURCE_UNTRUSTED");
}

#[tokio::test]
async fn typed_publisher_disabled_unknown_fields_and_writer_outcomes_fail_without_mutation() {
    let state = admitted();
    let (http, url) = client_with_state(false, None, state.clone()).await;
    let rejected = publish_retained(&state, &http, &url, &request()).await;
    assert_eq!(rejected["content"][0]["text"], "RELAY_DISABLED");
    assert!(state.requests.lock().unwrap().is_empty());
    let mut old_policy = admitted();
    old_policy.policy.github_native_authority_enabled = false;
    let (enabled_http, enabled_url) = client_with_state(true, None, old_policy.clone()).await;
    let old = publish_fresh(&enabled_http, &enabled_url, &decision_v4()).await;
    assert_eq!(
        old["content"][0]["text"],
        "CURRENT_PROTOCOL_CAPABILITY_REQUIRED"
    );
    assert!(old["structuredContent"]["guidance"]
        .as_str()
        .unwrap()
        .contains("do not fall back"));
    assert!(old_policy
        .store
        .lock()
        .unwrap()
        .known(&authority_operation(&decision_v4()))
        .unwrap()
        .is_none());
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
    let published = publish_retained(&state, &http, &url, &decision).await;
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
        let rejected = publish_retained(&state, &http, &url, &invalid).await;
        assert_eq!(
            rejected["content"][0]["text"], "AUTHORITY_NEXT_REFERENCE_INVALID",
            "{failure}: {rejected}"
        );
        assert_eq!(state.authority_comments.lock().unwrap().len(), 1);
    }
    let accepted = publish_retained(&state, &http, &url, &requested).await;
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
        let first = publish_retained(&state, &http, &url, &requested).await;
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
    let published = publish_retained(&state, &http, &url, &decision).await;
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
    let fresh = publish_retained(&state, &http, &url, &requested).await;
    assert_eq!(
        fresh["content"][0]["text"],
        "AUTHORITY_DECISION_SCOPE_MISMATCH"
    );
    requested["branch"] = json!("codex/task-24");
    requested["base_sha"] = json!("b".repeat(40));
    requested["starting_head"] = json!(HEAD);
    requested["existing_pr"] = json!(25);
    let bound = publish_retained(&state, &http, &url, &requested).await;
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
    let first = publish_retained(&state, &http, &url, &initial).await;
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
    let change = publish_retained(&state, &http, &url, &cr).await;
    assert_ne!(change["isError"], true, "{change}");
    let rejected = publish_retained(&state, &http, &url, &stale).await;
    assert_eq!(
        rejected["content"][0]["text"],
        "AUTHORITY_APPROVAL_STALE_REQUEST"
    );
    let mut next = request();
    next["step"] = json!(2);
    next["supersedes"] = change["structuredContent"]["reference"].clone();
    let continued = publish_retained(&state, &http, &url, &next).await;
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
            store: state.native.store.clone(),
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
            let accepted = publish_retained(&state.native, &http, &url, &candidate).await;
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
            let rejected = publish_retained(&state.native, &http, &url, &candidate).await;
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

fn decision_v4() -> Value {
    json!({"schema_version":"4.0","kind":"decision","repository":TEST_REPOSITORY,"task":24,
        "parent":{"kind":"issue","number":24},"charter_sha256":crate::task_authority::hash(CHARTER),
        "purpose":"Authorize the bounded continuation","amendments":{"issue_closure_policy":"close-authorized"},"supersedes":null,"context":[]})
}

fn authority_v4(
    decisions: Vec<Value>,
    change_request: Value,
    compatibility_request: Value,
) -> Value {
    let mut authority = json!({"charter":{"kind":"issue-body","id":240,"parent":{"kind":"issue","number":24},"sha256":crate::task_authority::hash(CHARTER)},
        "decisions":decisions,"change_request":change_request,"compatibility_request":compatibility_request});
    authority["sha256"] = json!(crate::task_authority::hash(
        &serde_json::to_string_pretty(&authority).unwrap()
    ));
    authority
}

fn outcome_v4(state: &MockState, authority: Value, parent: Value, result: Value) -> (Value, Value) {
    let record = json!({"schema_version":"4.0","kind":"outcome","repository":TEST_REPOSITORY,"task":24,"parent":parent,
        "charter_sha256":crate::task_authority::hash(CHARTER),"authority":authority,"admission":{"attempt":"run-10","step":1,"sha256":"a".repeat(64)},
        "attempt":"run-10","step":1,"status":"implemented","result":result,"warnings":[{"source":"bounded-check","impact":"Installed behavior is unverified.","resolution":"Deferred to authorized qualification.","next_action":"Obtain independent qualification.","evidence_gaps":["No live probe was authorized."]}],
        "limitations":["No live deployment evidence."],"summary":"The bounded result is available for independent review."});
    let native = json!({"id":2000,"body":crate::task_authority::render(&record),"html_url":format!("https://github.com/{TEST_REPOSITORY}/issues/{}#issuecomment-2000",parent["number"]),
        "issue_url":format!("https://api.github.com/repos/{TEST_REPOSITORY}/issues/{}",parent["number"]),"user":{"login":"example-writer[bot]","id":3,"type":"Bot"}});
    let reference = json!({"kind":"issue-comment","id":2000,"parent":parent,"sha256":crate::task_authority::hash(native["body"].as_str().unwrap())});
    if parent["kind"] == "issue" {
        state.authority_comments.lock().unwrap().push(native);
    } else {
        state
            .authority_sources
            .lock()
            .unwrap()
            .insert("issues/comments/2000".into(), native);
    }
    (reference, record)
}

fn approval_v4(reference: Value, outcome: &Value) -> Value {
    let mut record = outcome.clone();
    let object = record.as_object_mut().unwrap();
    object.remove("attempt");
    object.remove("status");
    object.remove("authority_drift");
    object.remove("authority_resolution");
    object.insert("kind".into(), json!("task-approval"));
    object.insert("parent".into(), json!({"kind":"issue","number":24}));
    object.insert("outcome".into(), reference);
    object.insert("verdict".into(), json!("APPROVE"));
    object.insert(
        "summary".into(),
        json!("The exact bounded no-PR result meets the admitted objective."),
    );
    record
}

#[tokio::test]
async fn fresh_v4_migration_accepts_original_no_compatibility_outcome_despite_historical_v3_request(
) {
    for with_pr in [false, true] {
        let state = admitted();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let old = publish_retained(&state, &http, &url, &request()).await;
        assert_ne!(old["isError"], true, "{old}");
        let mut direction = decision_v4();
        direction["amendments"] = json!({"purpose":"Use current admitted purpose","scope":["Use the explicitly migrated bounded scope."]});
        let decision = publish_fresh(&http, &url, &direction).await;
        assert_ne!(decision["isError"], true, "{decision}");
        let authority = authority_v4(
            vec![decision["structuredContent"]["reference"].clone()],
            Value::Null,
            Value::Null,
        );
        let (reference, delivered) = outcome_v4(
            &state,
            authority.clone(),
            if with_pr {
                json!({"kind":"pull_request","number":25})
            } else {
                json!({"kind":"issue","number":24})
            },
            if with_pr {
                json!({"kind":"git","revision":HEAD,"identities":[]})
            } else {
                json!({"kind":"qualification","revision":null,"identities":[{"kind":"qualification-run","id":"fresh4-migrated-run"}]})
            },
        );
        if with_pr {
            let native = state.authority_sources.lock().unwrap()["issues/comments/2000"].clone();
            state.authority_pr_comments.lock().unwrap().push(native);
            let preview = rpc(&http, &url, 1, "tools/call", json!({"name":"check_pr_review_target","arguments":{"repository":TEST_REPOSITORY,"pr_number":25,"expected_head_sha":HEAD}})).await;
            assert!(
                preview["result"]["structuredContent"]["task_acceptance"]
                    .get("error_code")
                    .is_none(),
                "{preview}"
            );
            assert_eq!(
                preview["result"]["structuredContent"]["task_acceptance"]["authority"],
                authority
            );
            let accepted = rpc(
                &http,
                &url,
                2,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
            )
            .await;
            assert_ne!(accepted["result"]["isError"], true, "{accepted}");
        } else {
            let accepted = publish_fresh(&http, &url, &approval_v4(reference, &delivered)).await;
            assert_ne!(accepted["isError"], true, "{accepted}");
            assert_eq!(
                accepted["structuredContent"]["task_acceptance"]["authority"],
                authority
            );
        }
    }
}

#[tokio::test]
async fn retained_v4_outcome_keeps_exact_v3_compatibility_source_and_rejects_its_successor() {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let old = publish_retained(&state, &http, &url, &request()).await;
    let old_reference = old["structuredContent"]["reference"].clone();
    let (reference, outcome) = outcome_v4(
        &state,
        authority_v4(vec![], Value::Null, old_reference.clone()),
        json!({"kind":"issue","number":24}),
        json!({"kind":"qualification","revision":null,"identities":[{"kind":"qualification-run","id":"retained-compat-run"}]}),
    );
    let accepted = publish_fresh(&http, &url, &approval_v4(reference.clone(), &outcome)).await;
    assert_ne!(accepted["isError"], true, "{accepted}");
    let mut successor = request();
    successor["purpose"] = json!("Complete an older separately admitted direction");
    successor["supersedes"] = old_reference;
    let next = publish_retained(&state, &http, &url, &successor).await;
    assert_ne!(next["isError"], true, "{next}");
    let stale = publish_fresh(&http, &url, &approval_v4(reference, &outcome)).await;
    assert_eq!(
        stale["content"][0]["text"], "AUTHORITY_APPROVAL_STALE_REQUEST",
        "{stale}"
    );
}

#[tokio::test]
async fn fresh_v4_cr_omits_old_compatibility_but_reserved_original_binding_is_preserved() {
    for retained_binding in [false, true] {
        let state = admitted();
        let mut pr = live_pr();
        pr["base"]["sha"] = json!("b".repeat(40));
        *state.pr.lock().unwrap() = Some(pr);
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let old = publish_retained(&state, &http, &url, &request()).await;
        let cr = v4_cr();
        let operation = authority_operation(&cr);
        let original = authority_v4(
            vec![],
            Value::Null,
            old["structuredContent"]["reference"].clone(),
        );
        if retained_binding {
            let body = format!(
                "{}\n<!-- jresearchsoftware-task-authority:v1 operation={operation} -->",
                crate::task_authority::render(&cr)
            );
            let store = state.store.lock().unwrap();
            store
                .reserve_publication(&operation, "retained-publication", &body, &body)
                .unwrap();
            store
                .bind_authority(&operation, &original.to_string())
                .unwrap();
            store.retryable_failure(&operation).unwrap();
        }
        let published = publish_fresh(&http, &url, &cr).await;
        assert_ne!(
            published["isError"], true,
            "{retained_binding}: {published}"
        );
        let binding: Value = serde_json::from_str(
            &state
                .store
                .lock()
                .unwrap()
                .authority_binding(&operation)
                .unwrap()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(
            binding["compatibility_request"],
            if retained_binding {
                original["compatibility_request"].clone()
            } else {
                Value::Null
            }
        );
        let replay = publish_fresh(&http, &url, &cr).await;
        assert_eq!(
            replay["content"][0]["text"], "DUPLICATE_SUPPRESSED",
            "{replay}"
        );
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
    }
}

#[tokio::test]
async fn v4_decisions_allocate_no_step_or_request_and_effective_closure_is_visible() {
    let state = admitted();
    state.issue.lock().unwrap().as_mut().unwrap()["labels"] = json!([]);
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let first = publish_retained(&state, &http, &url, &decision_v4()).await;
    assert_ne!(first["isError"], true, "{first}");
    assert_eq!(
        first["structuredContent"]["issue_closure_policy"],
        "close-authorized"
    );
    let mut second = decision_v4();
    second["purpose"] = json!("Keep open for the remaining qualification");
    second["amendments"]["issue_closure_policy"] = json!("keep-open");
    second["supersedes"] = first["structuredContent"]["reference"].clone();
    let next = publish_retained(&state, &http, &url, &second).await;
    assert_ne!(next["isError"], true, "{next}");
    assert_eq!(
        next["structuredContent"]["issue_closure_policy"],
        "keep-open"
    );
    assert_eq!(
        state.issue.lock().unwrap().as_ref().unwrap()["labels"],
        json!([])
    );
    assert!(state
        .requests
        .lock()
        .unwrap()
        .iter()
        .all(|path| !path.contains("/labels") && !path.starts_with("PATCH ")));
    assert_eq!(state.authority_comments.lock().unwrap().len(), 2);
    let replay = publish_retained(&state, &http, &url, &second).await;
    assert_eq!(replay["content"][0]["text"], "DUPLICATE_SUPPRESSED");
}

#[tokio::test]
async fn v4_native_cr_needs_no_request_or_step_projection_and_cannot_change_task_closure() {
    let state = admitted();
    state.issue.lock().unwrap().as_mut().unwrap()["labels"] = json!([]);
    let mut pr = live_pr();
    pr["labels"] = json!([]);
    pr["base"]["sha"] = json!("b".repeat(40));
    *state.pr.lock().unwrap() = Some(pr.clone());
    let cr = json!({"schema_version":"4.0","kind":"change-request","repository":TEST_REPOSITORY,"task":24,"parent":{"kind":"pull_request","number":25},
        "charter_sha256":crate::task_authority::hash(CHARTER),"purpose":"Repair the exact reviewed defect","branch":"codex/task-24","base_sha":"b".repeat(40),"reviewed_head_sha":HEAD,
        "change_request_id":"CR-24-001","findings":[{"id":"F1","severity":"major","problem":"The input bound is missing.","impact":"Unbounded input violates the admitted contract.","remediation":"Enforce the bound.","acceptance_criteria":["The oversized input is rejected."]}],"context":[],
        "overrides":{"effort":"xhigh","validation":["diff-check"],"boundaries":["Preserve Task scope and Writer separation."]}});
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let first = publish_retained(&state, &http, &url, &cr).await;
    assert_ne!(first["isError"], true, "{first}");
    assert_eq!(first["structuredContent"]["reference"]["kind"], "review");
    assert_eq!(
        first["structuredContent"]["issue_closure_policy"],
        "keep-open"
    );
    assert_eq!(
        state.pr.lock().unwrap().as_ref().unwrap()["title"],
        pr["title"]
    );
    assert!(state
        .requests
        .lock()
        .unwrap()
        .iter()
        .all(|path| !path.contains("/labels") && !path.starts_with("PATCH ")));
    let mut forbidden = cr.clone();
    forbidden["overrides"]["issue_closure_policy"] = json!("close-authorized");
    assert_eq!(
        publish_retained(&state, &http, &url, &forbidden).await["isError"],
        true
    );
    state.pr.lock().unwrap().as_mut().unwrap()["draft"] = json!(true);
    assert_eq!(
        publish_retained(&state, &http, &url, &cr).await["content"][0]["text"],
        "DUPLICATE_SUPPRESSED"
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn v4_fresh_cr_binds_observed_base_but_recovers_reserved_body_after_base_movement() {
    let state = admitted();
    let mut pr = live_pr();
    pr["base"]["sha"] = json!("c".repeat(40));
    *state.pr.lock().unwrap() = Some(pr);
    let mut cr = json!({"schema_version":"4.0","kind":"change-request","repository":TEST_REPOSITORY,"task":24,"parent":{"kind":"pull_request","number":25},
        "charter_sha256":crate::task_authority::hash(CHARTER),"purpose":"Repair the exact reviewed defect","branch":"codex/task-24","base_sha":"b".repeat(40),"reviewed_head_sha":HEAD,
        "change_request_id":"CR-24-001","findings":[{"id":"F1","severity":"major","problem":"The input bound is missing.","impact":"Unbounded input violates the admitted contract.","remediation":"Enforce the bound.","acceptance_criteria":["The oversized input is rejected."]}],"context":[]});
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let rejected = publish_retained(&state, &http, &url, &cr).await;
    assert_eq!(
        rejected["content"][0]["text"],
        "AUTHORITY_PR_BINDING_MISMATCH"
    );
    assert!(state.reviews.lock().unwrap().is_empty());
    cr["base_sha"] = json!("c".repeat(40));
    let published = publish_retained(&state, &http, &url, &cr).await;
    assert_ne!(published["isError"], true, "{published}");
    let native = state.reviews.lock().unwrap()[0].clone();
    let operation = crate::task_authority::hash(&format!(
        "task-authority-v1\n{}",
        crate::task_authority::render_legacy(&cr)
    ));
    let store = store::Store::open(":memory:").unwrap();
    store
        .reserve_publication(
            &operation,
            "existing",
            native["body"].as_str().unwrap(),
            "legacy",
        )
        .unwrap();
    state.pr.lock().unwrap().as_mut().unwrap()["base"]["sha"] = json!("d".repeat(40));
    let app = App {
        policy: state.policy.clone(),
        repositories: BTreeSet::from([TEST_REPOSITORY.into()]),
        enabled: true,
        store: Arc::new(Mutex::new(store)),
        github: github::Github::mock_api(mock_api(state.clone()).await),
        trusted_client_ca: Arc::new(Vec::new()),
        observed_arguments: Default::default(),
    };
    let args = json!({"repository":TEST_REPOSITORY,"record":cr});
    let target = app.target(&args).unwrap();
    let recovered = crate::task_authority::publish(&target, &args).await;
    assert_eq!(
        recovered["content"][0]["text"], "AUTHORITY_RECOVERED",
        "{recovered}"
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
    assert_eq!(state.reviews.lock().unwrap()[0]["body"], native["body"]);
}

#[tokio::test]
async fn v4_no_pr_approval_binds_writer_admission_and_preserves_warnings_without_public_request() {
    for failure in [
        "none",
        "writer",
        "admission",
        "warnings",
        "limits",
        "decisions",
    ] {
        let state = admitted();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let first = publish_retained(&state, &http, &url, &decision_v4()).await;
        assert_ne!(first["isError"], true, "{first}");
        let authority = authority_v4(
            vec![first["structuredContent"]["reference"].clone()],
            Value::Null,
            Value::Null,
        );
        let (reference, outcome) = outcome_v4(
            &state,
            authority,
            json!({"kind":"issue","number":24}),
            json!({"kind":"qualification","revision":null,"identities":[{"kind":"qualification-run","id":"bounded-run-1"}]}),
        );
        let mut approval = approval_v4(reference, &outcome);
        match failure {
            "writer" => state.authority_comments.lock().unwrap()[1]["user"]["type"] = json!("User"),
            "admission" => approval["admission"]["sha256"] = json!("b".repeat(64)),
            "warnings" => approval["warnings"] = json!([]),
            "limits" => approval["limitations"] = json!([]),
            "decisions" => {
                let mut next = decision_v4();
                next["purpose"] = json!("Add the later scope");
                next["amendments"] = json!({"scope":["The later authorized work"]});
                let result = publish_retained(&state, &http, &url, &next).await;
                assert_ne!(result["isError"], true, "{result}");
            }
            _ => {}
        }
        let count = state.authority_comments.lock().unwrap().len();
        let result = publish_retained(&state, &http, &url, &approval).await;
        if failure == "none" {
            assert_ne!(result["isError"], true, "{result}");
            assert_eq!(
                result["structuredContent"]["issue_closure_policy"],
                "close-authorized"
            );
        } else {
            assert_eq!(result["isError"], true, "{failure}: {result}");
            assert_eq!(state.authority_comments.lock().unwrap().len(), count);
        }
        assert!(state.reviews.lock().unwrap().is_empty());
    }
}

#[tokio::test]
async fn historical_authority_reservation_recovers_exact_original_body_across_renderer_upgrade() {
    let state = admitted();
    let record = request();
    let operation = crate::task_authority::hash(&format!(
        "task-authority-v1\n{}",
        crate::task_authority::render_legacy(&record)
    ));
    let body = format!(
        "{}\n<!-- jresearchsoftware-task-authority:v1 operation={operation} -->",
        crate::task_authority::render_legacy(&record)
    );
    state.authority_comments.lock().unwrap().push(json!({"id":1000,"body":body,"html_url":format!("https://github.com/{TEST_REPOSITORY}/issues/24#issuecomment-1000"),
        "issue_url":format!("https://api.github.com/repos/{TEST_REPOSITORY}/issues/24"),"user":{"login":"example-reviewer[bot]","id":2,"type":"Bot"}}));
    let store = store::Store::open(":memory:").unwrap();
    store.reserve(&operation, "old-body").unwrap();
    let app = App {
        policy: state.policy.clone(),
        repositories: BTreeSet::from([TEST_REPOSITORY.into()]),
        enabled: true,
        store: Arc::new(Mutex::new(store)),
        github: github::Github::mock_api(mock_api(state.clone()).await),
        trusted_client_ca: Arc::new(Vec::new()),
        observed_arguments: Default::default(),
    };
    let args = json!({"repository":TEST_REPOSITORY,"record":record});
    let target = app.target(&args).unwrap();
    let recovered = crate::task_authority::publish(&target, &args).await;
    assert_eq!(
        recovered["content"][0]["text"], "AUTHORITY_RECOVERED",
        "{recovered}"
    );
    let replay = crate::task_authority::publish(&target, &args).await;
    assert_eq!(
        replay["content"][0]["text"], "DUPLICATE_SUPPRESSED",
        "{replay}"
    );
    assert_eq!(state.authority_comments.lock().unwrap().len(), 1);
    assert!(state
        .requests
        .lock()
        .unwrap()
        .iter()
        .all(|path| !path.starts_with("POST ") || !path.ends_with("/comments")));
}

#[tokio::test]
async fn manual_outcome_capability_is_optional_mtls_gated_and_cannot_select_reviewer_publication() {
    for enabled in [false, true] {
        let mut state = MockState::default();
        state.policy.manual_outcome_enabled = enabled;
        state.policy.manual_outcome_client_path = "/unavailable-synthetic-writer-capability".into();
        let (http, url) = client_with_state(false, None, state.clone()).await;
        let listed = rpc(&http, &url, 1, "tools/list", json!({})).await;
        assert_eq!(
            listed["result"]["tools"]
                .as_array()
                .unwrap()
                .iter()
                .any(|tool| tool["name"] == "submit_manual_outcome"),
            enabled
        );
        let args = json!({"repository":TEST_REPOSITORY,"task":24,"run_id":10,"result":{"summary":"Manual claimed result"}});
        let response=http.post(&url).json(&json!({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"submit_manual_outcome","arguments":args}})).send().await.unwrap();
        assert_eq!(response.status(), reqwest::StatusCode::FORBIDDEN);
        let mut forbidden = args.clone();
        forbidden["operation"] = json!("merge");
        let result = rpc(
            &http,
            &url,
            3,
            "tools/call",
            json!({"name":"submit_manual_outcome","arguments":forbidden}),
        )
        .await;
        assert_eq!(
            result["result"]["content"][0]["text"],
            "INVALID_MANUAL_OUTCOME"
        );
        {
            let result = rpc(
                &http,
                &url,
                4,
                "tools/call",
                json!({"name":"submit_manual_outcome","arguments":args}),
            )
            .await;
            assert_eq!(
                result["result"]["content"][0]["text"],
                if enabled {
                    "WRITER_CAPABILITY_UNAVAILABLE"
                } else {
                    "MANUAL_OUTCOME_CAPABILITY_DISABLED"
                }
            );
            assert!(result["result"]["structuredContent"]["guidance"]
                .as_str()
                .unwrap()
                .contains("do not replace"));
        }
        assert!(state.requests.lock().unwrap().is_empty());
        assert!(state.reviews.lock().unwrap().is_empty());
    }
}

#[tokio::test]
async fn v4_closed_disposable_pr_approval_preserves_immutable_binding_without_reopening() {
    let state = admitted();
    let mut pr = live_pr();
    pr["state"] = json!("closed");
    *state.pr.lock().unwrap() = Some(pr);
    let (reference, outcome) = outcome_v4(
        &state,
        authority_v4(vec![], Value::Null, Value::Null),
        json!({"kind":"pull_request","number":25}),
        json!({"kind":"qualification","revision":null,"identities":[{"kind":"qualification-run","id":"closed-artifact-result"}]}),
    );
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let result = publish_retained(&state, &http, &url, &approval_v4(reference, &outcome)).await;
    assert_ne!(result["isError"], true, "{result}");
    assert_eq!(
        state.pr.lock().unwrap().as_ref().unwrap()["state"],
        "closed"
    );
    assert!(state
        .requests
        .lock()
        .unwrap()
        .iter()
        .all(|path| !path.starts_with("PATCH ")));
}

#[tokio::test]
async fn v4_exact_native_approve_returns_conditional_closure_authority_without_inventing_completion(
) {
    let state = admitted();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let decision = publish_retained(&state, &http, &url, &decision_v4()).await;
    assert_ne!(decision["isError"], true, "{decision}");
    let authority = authority_v4(
        vec![decision["structuredContent"]["reference"].clone()],
        Value::Null,
        Value::Null,
    );
    outcome_v4(
        &state,
        authority,
        json!({"kind":"issue","number":24}),
        json!({"kind":"git","revision":HEAD,"identities":[]}),
    );
    let approved = rpc(
        &http,
        &url,
        2,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
    )
    .await;
    assert_ne!(approved["result"]["isError"], true, "{approved}");
    let continuation = &approved["result"]["structuredContent"]["post_review_continuation"];
    assert_eq!(
        continuation["issue_closure_policy"], "close-authorized",
        "{approved}"
    );
    assert_eq!(
        continuation["completion_conditions"],
        "trusted-owner-canonical-state-required"
    );
    assert!(continuation.get("task_complete").is_none());
    assert!(continuation.get("close_issue_authorized").is_none());
    assert_eq!(continuation["execution_supported"], false);
    assert_eq!(
        continuation["request_authority"]["admission"]["attempt"],
        "run-10"
    );
}

fn v4_cr() -> Value {
    json!({"schema_version":"4.0","kind":"change-request","repository":TEST_REPOSITORY,"task":24,"parent":{"kind":"pull_request","number":25},
        "charter_sha256":crate::task_authority::hash(CHARTER),"purpose":"Repair the exact reviewed defect","branch":"codex/task-24","base_sha":"b".repeat(40),"reviewed_head_sha":HEAD,
        "change_request_id":"CR-24-001","findings":[{"id":"F1","severity":"major","problem":"The input bound is missing.","impact":"Unbounded input violates the admitted contract.","remediation":"Enforce the bound.","acceptance_criteria":["The oversized input is rejected."]}],"context":[]})
}

async fn native_app(state: &MockState) -> App {
    App {
        policy: state.policy.clone(),
        repositories: BTreeSet::from([TEST_REPOSITORY.into()]),
        enabled: true,
        store: state.store.clone(),
        github: github::Github::mock_api(mock_api(state.clone()).await),
        trusted_client_ca: Arc::new(Vec::new()),
        observed_arguments: Default::default(),
    }
}

async fn native_publish(app: &App, record: &Value) -> Value {
    retain_older_publication(&app.store, record);
    crate::task_authority::validate_record(record).unwrap();
    let args = json!({"repository":TEST_REPOSITORY,"record":record});
    crate::task_authority::publish(&app.target(&args).unwrap(), &args).await
}

async fn publication_cr(app: &App, version: &str) -> Value {
    if version == "4.0" {
        return v4_cr();
    }
    let mut initial = request();
    initial["route"] = json!("auto");
    initial["branch"] = json!("codex/task-24");
    initial["base_sha"] = json!("b".repeat(40));
    initial["starting_head"] = json!(HEAD);
    initial["existing_pr"] = json!(25);
    let published = native_publish(app, &initial).await;
    assert_ne!(published["isError"], true, "{published}");
    let mut cr = initial;
    cr["kind"] = json!("change-request");
    cr["parent"] = json!({"kind":"pull_request","number":25});
    cr["step"] = json!(2);
    cr["supersedes"] = published["structuredContent"]["reference"].clone();
    for field in [
        "purpose",
        "change_request_id",
        "reviewed_head_sha",
        "findings",
    ] {
        cr[field] = v4_cr()[field].clone();
    }
    cr
}

fn authority_operation(record: &Value) -> String {
    crate::task_authority::hash(&format!(
        "task-authority-v1\n{}",
        crate::task_authority::render_legacy(record)
    ))
}

#[tokio::test]
async fn original_outcome_accepts_current_amended_task_without_rewriting_execution_binding() {
    for scenario in ["new", "superseded", "equivalent"] {
        let state = admitted();
        let app = native_app(&state).await;
        let mut first = decision_v4();
        first["amendments"] = json!({"scope":["Original bounded scope"]});
        let prior = if scenario == "new" {
            Value::Null
        } else {
            native_publish(&app, &first).await["structuredContent"]["reference"].clone()
        };
        let original = authority_v4(
            if prior.is_null() {
                vec![]
            } else {
                vec![prior.clone()]
            },
            Value::Null,
            Value::Null,
        );
        let (reference, outcome) = outcome_v4(
            &state,
            original.clone(),
            json!({"kind":"issue","number":24}),
            json!({"kind":"qualification","revision":null,"identities":[{"kind":"qualification-run","id":"immutable-run"}]}),
        );
        let before = state
            .authority_comments
            .lock()
            .unwrap()
            .iter()
            .find(|native| native["id"] == 2000)
            .unwrap()["body"]
            .clone();
        let mut next = first;
        next["purpose"] = json!("Review the result against the current Task");
        next["supersedes"] = prior;
        if scenario != "equivalent" {
            next["amendments"] = json!({"scope":["Current bounded scope"]});
        }
        let current = native_publish(&app, &next).await;
        assert_ne!(current["isError"], true, "{current}");
        let mut accepted = approval_v4(reference, &outcome);
        let stale = native_publish(&app, &accepted).await;
        assert_eq!(
            stale["content"][0]["text"], "AUTHORITY_APPROVAL_STALE_REQUEST",
            "{scenario}: {stale}"
        );
        accepted["authority"] = authority_v4(
            vec![current["structuredContent"]["reference"].clone()],
            Value::Null,
            Value::Null,
        );
        let published = native_publish(&app, &accepted).await;
        assert_ne!(published["isError"], true, "{scenario}: {published}");
        assert_eq!(
            published["structuredContent"]["record"]["admission"],
            outcome["admission"]
        );
        assert_eq!(outcome["authority"], original);
        assert_eq!(
            state
                .authority_comments
                .lock()
                .unwrap()
                .iter()
                .find(|native| native["id"] == 2000)
                .unwrap()["body"],
            before
        );
        let mut later = decision_v4();
        later["amendments"] = json!({"validation":["diff-check"]});
        native_publish(&app, &later).await;
        let replay = native_publish(&app, &accepted).await;
        assert_eq!(
            replay["content"][0]["text"], "AUTHORITY_APPROVAL_STALE_REQUEST",
            "{replay}"
        );
    }
}

#[tokio::test]
async fn native_approve_requires_reviewed_current_task_on_material_drift_and_pins_that_acceptance()
{
    let state = admitted();
    let (reference, outcome) = outcome_v4(
        &state,
        authority_v4(vec![], Value::Null, Value::Null),
        json!({"kind":"issue","number":24}),
        json!({"kind":"git","revision":HEAD,"identities":[]}),
    );
    let original_body = state.authority_comments.lock().unwrap()[0]["body"].clone();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let mut decision = decision_v4();
    decision["amendments"] = json!({"scope":["Current additional requirement"]});
    let current = publish_retained(&state, &http, &url, &decision).await;
    let preview = rpc(&http,&url,2,"tools/call",json!({"name":"check_pr_review_target","arguments":{"repository":TEST_REPOSITORY,"pr_number":25,"expected_head_sha":HEAD}})).await;
    let accepted = &preview["result"]["structuredContent"]["task_acceptance"];
    assert_eq!(
        accepted["original_authority"], outcome["authority"],
        "{preview}"
    );
    assert_eq!(
        accepted["authority_drift"]["changed_fields"],
        json!(["scope"])
    );
    assert_eq!(accepted["outcome"], reference);
    assert_eq!(
        accepted["authority"]["decisions"],
        json!([current["structuredContent"]["reference"]])
    );
    let mut args = base_args("APPROVE");
    let missing = rpc(
        &http,
        &url,
        3,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":args}),
    )
    .await;
    assert_eq!(
        missing["result"]["content"][0]["text"], "AUTHORITY_APPROVAL_CURRENT_TASK_REQUIRED",
        "{missing}"
    );
    args["expected_task_authority_sha256"] = json!("f".repeat(64));
    let stale = rpc(
        &http,
        &url,
        4,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":args}),
    )
    .await;
    assert_eq!(
        stale["result"]["content"][0]["text"],
        "AUTHORITY_APPROVAL_STALE_REQUEST"
    );
    assert!(state.reviews.lock().unwrap().is_empty());
    assert!(state.check_runs.lock().unwrap().is_empty());
    args["expected_task_authority_sha256"] = accepted["authority"]["sha256"].clone();
    let approved = rpc(
        &http,
        &url,
        5,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":args}),
    )
    .await;
    assert_ne!(approved["result"]["isError"], true, "{approved}");
    assert_eq!(
        approved["result"]["structuredContent"]["post_review_continuation"]["request_authority"]
            ["authority"],
        accepted["authority"]
    );
    assert!(state.reviews.lock().unwrap()[0]["body"]
        .as_str()
        .unwrap()
        .contains(&format!(
            "jresearchsoftware-reviewer-acceptance:v1 authority_sha256={}",
            accepted["authority"]["sha256"].as_str().unwrap()
        )));
    assert_eq!(
        state.authority_comments.lock().unwrap()[0]["body"],
        original_body
    );
    decision["purpose"] = json!("Change the next current requirement");
    decision["amendments"] = json!({"boundaries":["New acceptance boundary"]});
    publish_retained(&state, &http, &url, &decision).await;
    let before = state.requests.lock().unwrap().len();
    let replay = rpc(
        &http,
        &url,
        6,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":args}),
    )
    .await;
    assert_eq!(
        replay["result"]["content"][0]["text"], "AUTHORITY_APPROVAL_STALE_REQUEST",
        "{replay}"
    );
    assert!(!state.requests.lock().unwrap()[before..]
        .iter()
        .any(
            |path| (path.starts_with("POST ") && path.contains("/repos/"))
                || path.starts_with("PUT ")
                || path.starts_with("PATCH ")
        ));
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
    assert_eq!(state.check_runs.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn typed_cr_recovers_each_partial_publication_phase_without_duplicate_native_posts() {
    for version in ["3.0", "4.0"] {
        for phase in [
            "review-response",
            "issue-label",
            "pr-label",
            "title",
            "check-response",
            "check-reread",
            "completion",
        ] {
            if version == "4.0" && matches!(phase, "issue-label" | "pr-label" | "title") {
                continue;
            }
            let state = admitted();
            let mut pr = live_pr();
            pr["base"]["sha"] = json!("b".repeat(40));
            *state.pr.lock().unwrap() = Some(pr);
            let app = native_app(&state).await;
            let cr = publication_cr(&app, version).await;
            match phase {
                "review-response" => {
                    *state.authority_review_mode.lock().unwrap() = Some("lost".into())
                }
                "issue-label" => {
                    *state.metadata_failure.lock().unwrap() = Some("issues/24/labels".into())
                }
                "pr-label" => {
                    *state.metadata_failure.lock().unwrap() = Some("issues/25/labels".into())
                }
                "title" => *state.metadata_failure.lock().unwrap() = Some("pulls/25".into()),
                "check-response" => {
                    *state.authority_check_mode.lock().unwrap() = Some("lost".into())
                }
                "check-reread" => {
                    *state.authority_check_mode.lock().unwrap() = Some("reread".into())
                }
                _ => {}
            }
            let partial = native_publish(&app, &cr).await;
            if phase == "completion" {
                assert_ne!(partial["isError"], true, "{partial}");
                let native = partial["structuredContent"]["reference"]["id"]
                    .as_i64()
                    .unwrap();
                app.store
                    .lock()
                    .unwrap()
                    .authority_published(
                        &authority_operation(&cr),
                        native,
                        partial["structuredContent"]["native_url"].as_str().unwrap(),
                        &state.policy.actor,
                    )
                    .unwrap();
            } else {
                assert_eq!(partial["isError"], true, "{version}/{phase}: {partial}");
            }
            // Restart service ownership while retaining its protected journal.
            let restarted = App {
                store: app.store.clone(),
                github: github::Github::mock_api(mock_api(state.clone()).await),
                ..app
            };
            state.pr.lock().unwrap().as_mut().unwrap()["draft"] = json!(true);
            let recovered = native_publish(&restarted, &cr).await;
            assert_eq!(
                recovered["content"][0]["text"], "AUTHORITY_RECOVERED",
                "{version}/{phase}: {recovered}"
            );
            assert_eq!(state.reviews.lock().unwrap().len(), 1);
            assert_eq!(state.check_runs.lock().unwrap().len(), 1);
            assert_eq!(
                state
                    .requests
                    .lock()
                    .unwrap()
                    .iter()
                    .filter(|path| path.starts_with("POST ") && path.ends_with("/reviews"))
                    .count(),
                1
            );
            assert_eq!(
                state
                    .requests
                    .lock()
                    .unwrap()
                    .iter()
                    .filter(|path| path.starts_with("POST ") && path.ends_with("/check-runs"))
                    .count(),
                1
            );
            let row = restarted
                .store
                .lock()
                .unwrap()
                .known(&authority_operation(&cr))
                .unwrap()
                .unwrap();
            assert_eq!(row.status, "PUBLISHED");
            assert_eq!(row.native_id, Some(1));
            assert!(row.check_id.is_some());
            assert_eq!(
                crate::step_sync::current_step(state.issue.lock().unwrap().as_ref().unwrap())
                    .unwrap(),
                if version == "3.0" { 2 } else { 1 }
            );
        }
    }
}

#[tokio::test]
async fn uncertain_absent_review_or_check_never_repeats_its_post() {
    for stage in ["review", "check"] {
        let state = admitted();
        let mut pr = live_pr();
        pr["base"]["sha"] = json!("b".repeat(40));
        *state.pr.lock().unwrap() = Some(pr);
        let app = native_app(&state).await;
        let cr = v4_cr();
        if stage == "review" {
            *state.authority_review_mode.lock().unwrap() = Some("missing".into());
        } else {
            *state.authority_check_mode.lock().unwrap() = Some("missing".into());
        }
        assert_eq!(native_publish(&app, &cr).await["isError"], true);
        let before = state.requests.lock().unwrap().len();
        let retry = native_publish(&app, &cr).await;
        assert_eq!(
            retry["content"][0]["text"],
            if stage == "review" {
                "AUTHORITY_PUBLICATION_UNCERTAIN"
            } else {
                "CHECK_PUBLICATION_UNCERTAIN"
            },
            "{retry}"
        );
        assert!(!state.requests.lock().unwrap()[before..]
            .iter()
            .any(|path| path.starts_with("POST ") && path.contains("/repos/")));
    }
}

#[tokio::test]
async fn typed_cr_recovery_rejects_native_tampering_authority_drift_and_ambiguous_checks() {
    for defect in [
        "body",
        "actor",
        "parent",
        "review-head",
        "review-state",
        "native-reread-head",
        "pr-head",
        "pr-parent",
        "charter",
        "decision",
        "duplicate-review",
        "conflicting-review",
        "duplicate-check",
        "wrong-app",
        "wrong-app-id",
        "wrong-check-head",
        "wrong-check-state",
        "wrong-conclusion",
        "check-operation",
        "check-id",
    ] {
        let state = admitted();
        let mut pr = live_pr();
        pr["base"]["sha"] = json!("b".repeat(40));
        *state.pr.lock().unwrap() = Some(pr);
        let app = native_app(&state).await;
        let cr = v4_cr();
        let completed = native_publish(&app, &cr).await;
        assert_ne!(completed["isError"], true, "{completed}");
        let operation = authority_operation(&cr);
        app.store
            .lock()
            .unwrap()
            .authority_published(
                &operation,
                1,
                completed["structuredContent"]["native_url"]
                    .as_str()
                    .unwrap(),
                &state.policy.actor,
            )
            .unwrap();
        let mut native = native_review(&state.reviews.lock().unwrap()[0]);
        match defect {
            "body" => native["body"] = json!("Tampered authority"),
            "actor" => native["user"]["id"] = json!(999),
            "parent" => {
                native["pull_request_url"] =
                    json!("https://api.github.com/repos/other/repository/pulls/25")
            }
            "review-head" | "native-reread-head" => native["commit_id"] = json!("c".repeat(40)),
            "review-state" => native["state"] = json!("APPROVED"),
            "pr-head" => {
                state.pr.lock().unwrap().as_mut().unwrap()["head"]["sha"] = json!("c".repeat(40))
            }
            "pr-parent" => {
                state.pr.lock().unwrap().as_mut().unwrap()["body"] = json!("Related to #26")
            }
            "charter" => {
                state.issue.lock().unwrap().as_mut().unwrap()["body"] =
                    json!(format!("{CHARTER}\nChanged charter"))
            }
            "decision" => {
                let mut changed = decision_v4();
                changed["amendments"] = json!({"scope":["Changed authority"]});
                native_publish(&app, &changed).await;
            }
            "duplicate-review" | "conflicting-review" => {
                let mut conflict = native.clone();
                conflict["id"] = json!(2);
                if defect == "conflicting-review" {
                    conflict["body"]=json!(format!("Tampered record\n<!-- jresearchsoftware-task-authority:v1 operation={operation} -->"));
                    conflict["user"]["id"] = json!(999);
                }
                *state.decisive_override.lock().unwrap() = Some(json!([native.clone(), conflict]));
            }
            "duplicate-check" => {
                let check = state.check_runs.lock().unwrap()[0].clone();
                state.check_runs.lock().unwrap().push(check);
            }
            "wrong-app" => state.check_runs.lock().unwrap()[0]["app"]["slug"] = json!("other-app"),
            "wrong-app-id" => state.check_runs.lock().unwrap()[0]["app"]["id"] = json!(999),
            "wrong-check-head" => {
                state.check_runs.lock().unwrap()[0]["head_sha"] = json!("c".repeat(40))
            }
            "wrong-check-state" => {
                state.check_runs.lock().unwrap()[0]["status"] = json!("in_progress")
            }
            "wrong-conclusion" => {
                state.check_runs.lock().unwrap()[0]["conclusion"] = json!("success")
            }
            "check-operation" => {
                state.check_runs.lock().unwrap()[0]["external_id"] = json!("another-operation")
            }
            "check-id" => state.check_runs.lock().unwrap()[0]["id"] = json!(999),
            _ => unreachable!(),
        }
        if matches!(
            defect,
            "body" | "actor" | "parent" | "review-head" | "review-state" | "native-reread-head"
        ) {
            state
                .authority_sources
                .lock()
                .unwrap()
                .insert("pulls/25/reviews/1".into(), native);
        }
        let before = state.requests.lock().unwrap().len();
        let retry = native_publish(&app, &cr).await;
        assert_eq!(retry["isError"], true, "{defect}: {retry}");
        assert!(
            !state.requests.lock().unwrap()[before..]
                .iter()
                .any(
                    |path| (path.starts_with("POST ") && path.contains("/repos/"))
                        || path.starts_with("PUT ")
                        || path.starts_with("PATCH ")
                ),
            "{defect}: {retry}"
        );
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
    }
}

#[tokio::test]
async fn ordinary_unlinked_pr_keeps_preview_and_native_approve_without_task_admission() {
    let state = MockState::default();
    let mut pr = live_pr();
    pr["body"] = json!("Ordinary contributor change.");
    pr["title"] = json!("Improve a bounded implementation");
    pr["labels"] = json!([]);
    *state.pr.lock().unwrap() = Some(pr);
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let preview=rpc(&http,&url,1,"tools/call",json!({"name":"check_pr_review_target","arguments":{"repository":TEST_REPOSITORY,"pr_number":25,"expected_head_sha":HEAD}})).await;
    assert_eq!(preview["result"]["content"][0]["text"], "OK");
    assert!(preview["result"]["structuredContent"]["task_acceptance"].is_null());
    let approved = rpc(
        &http,
        &url,
        2,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
    )
    .await;
    assert_eq!(
        approved["result"]["content"][0]["text"], "PUBLISHED",
        "{approved}"
    );
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn incomplete_task_link_inspection_refuses_governed_approval_and_preserves_generic_multi_links(
) {
    for scenario in [
        "projected-admission",
        "admission-only",
        "request-only",
        "unavailable-multi",
        "generic",
    ] {
        let state = admitted();
        let mut pr = live_pr();
        if scenario != "projected-admission" && scenario != "unavailable-multi" {
            pr["title"] = json!("Ordinary contributor improvement");
            pr["labels"] = json!([]);
        }
        let ids: Vec<u64> = if scenario == "unavailable-multi" {
            vec![1, 24]
        } else {
            (1..=20).chain(std::iter::once(24)).collect()
        };
        let mut body = ids
            .iter()
            .map(|id| format!("Related to #{id}"))
            .collect::<Vec<_>>()
            .join("\n");
        if matches!(scenario, "projected-admission" | "admission-only") {
            body.push_str(&format!("\nExecution admission digest: {}", "a".repeat(64)));
        } else if scenario == "request-only" {
            body.push_str(&format!("\nExecution request digest: {}", "a".repeat(64)));
        }
        pr["body"] = json!(body);
        *state.pr.lock().unwrap() = Some(pr);
        for id in 1..=20 {
            if scenario == "unavailable-multi" && id == 1 {
                continue;
            }
            state.authority_sources.lock().unwrap().insert(format!("issues/{id}"), json!({"id":id,"number":id,"state":"open","body":"Ordinary unmarked Issue.","user":{"login":"example-owner","id":1,"type":"User"}}));
        }
        if scenario == "generic" {
            state.issue.lock().unwrap().as_mut().unwrap()["body"] =
                json!("Ordinary unmarked Issue.");
        }
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let preview=rpc(&http,&url,1,"tools/call",json!({"name":"check_pr_review_target","arguments":{"repository":TEST_REPOSITORY,"pr_number":25,"expected_head_sha":HEAD}})).await;
        let before = state.requests.lock().unwrap().len();
        let approved = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
        )
        .await;
        if scenario == "generic" {
            assert!(preview["result"]["structuredContent"]["task_acceptance"].is_null());
            assert_eq!(
                approved["result"]["content"][0]["text"], "PUBLISHED",
                "{approved}"
            );
            assert_eq!(
                approved["result"]["structuredContent"]["post_review_continuation"]
                    ["automatic_continuation_authorized"],
                false
            );
            assert_eq!(state.reviews.lock().unwrap().len(), 1);
        } else {
            assert!(
                preview["result"]["structuredContent"]["task_acceptance"]["error_code"].is_string(),
                "{scenario}: {preview}"
            );
            assert_eq!(
                approved["result"]["isError"], true,
                "{scenario}: {approved}"
            );
            assert!(
                !state.requests.lock().unwrap()[before..]
                    .iter()
                    .any(|path| path.starts_with("POST ") && path.contains("/repos/")),
                "{scenario}: {approved}"
            );
            assert!(state.reviews.lock().unwrap().is_empty());
            assert!(state.check_runs.lock().unwrap().is_empty());
        }
    }
}

#[tokio::test]
async fn historical_cr_journal_observes_existing_check_but_cannot_invent_absent_post_intent() {
    static SEQUENCE: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    for version in ["3.0", "4.0"] {
        for observed_check in [false, true] {
            let state = admitted();
            let mut pr = live_pr();
            pr["base"]["sha"] = json!("b".repeat(40));
            *state.pr.lock().unwrap() = Some(pr);
            let app = native_app(&state).await;
            let cr = publication_cr(&app, version).await;
            let completed = native_publish(&app, &cr).await;
            assert_ne!(completed["isError"], true, "{completed}");
            let operation = authority_operation(&cr);
            let (body, step_binding) = {
                let store = app.store.lock().unwrap();
                (
                    store.publication_body(&operation).unwrap().unwrap(),
                    store.step_binding(&operation).unwrap(),
                )
            };
            let path = std::env::temp_dir().join(format!(
                "relay-historical-check-{}-{}.db",
                std::process::id(),
                SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
            let db = rusqlite::Connection::open(&path).unwrap();
            db.execute_batch("CREATE TABLE operations(operation_id TEXT PRIMARY KEY,status TEXT NOT NULL,review_id INTEGER,review_url TEXT,actor_login TEXT,check_id INTEGER,check_url TEXT,finding_digest TEXT NOT NULL DEFAULT '',created_at INTEGER NOT NULL,native_id INTEGER,native_url TEXT,publication_body TEXT,step_binding TEXT);").unwrap();
            db.execute("INSERT INTO operations(operation_id,status,actor_login,created_at,native_id,native_url,publication_body,step_binding) VALUES(?1,'AUTHORITY_PUBLISHED',?2,0,1,?3,?4,?5)",rusqlite::params![operation,state.policy.actor,completed["structuredContent"]["native_url"].as_str().unwrap(),body,step_binding]).unwrap();
            drop(db);
            let historical = App {
                store: Arc::new(Mutex::new(
                    store::Store::open(path.to_str().unwrap()).unwrap(),
                )),
                ..app
            };
            if !observed_check {
                state.check_runs.lock().unwrap().clear();
            }
            let before = state.requests.lock().unwrap().len();
            let recovered = native_publish(&historical, &cr).await;
            assert_eq!(
                recovered["content"][0]["text"],
                if observed_check {
                    "AUTHORITY_RECOVERED"
                } else {
                    "CHECK_PUBLICATION_UNCERTAIN"
                },
                "{version}/{observed_check}: {recovered}"
            );
            assert!(!state.requests.lock().unwrap()[before..]
                .iter()
                .any(|path| path.starts_with("POST ") && path.contains("/repos/")));
            assert_eq!(state.reviews.lock().unwrap().len(), 1);
            drop(historical);
            std::fs::remove_file(path).unwrap();
        }
    }
}

#[tokio::test]
async fn ambiguous_marked_task_linkage_and_postpreview_drift_block_native_approval_before_mutation()
{
    for defect in [
        "ambiguous",
        "postpreview",
        "original-body",
        "original-actor",
        "original-parent",
    ] {
        let state = admitted();
        let (reference, outcome) = outcome_v4(
            &state,
            authority_v4(vec![], Value::Null, Value::Null),
            json!({"kind":"issue","number":24}),
            json!({"kind":"git","revision":HEAD,"identities":[]}),
        );
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let mut direction = decision_v4();
        direction["amendments"] = json!({"scope":["Current requirement"]});
        publish_retained(&state, &http, &url, &direction).await;
        let preview=rpc(&http,&url,1,"tools/call",json!({"name":"check_pr_review_target","arguments":{"repository":TEST_REPOSITORY,"pr_number":25,"expected_head_sha":HEAD}})).await;
        let mut args = base_args("APPROVE");
        args["expected_task_authority_sha256"] = preview["result"]["structuredContent"]
            ["task_acceptance"]["authority"]["sha256"]
            .clone();
        match defect {
            "ambiguous" => {
                let mut pr = live_pr();
                pr["body"] = json!("Related to #24\nRelated to #26");
                *state.pr.lock().unwrap() = Some(pr);
            }
            "postpreview" => {
                direction["amendments"] = json!({"boundaries":["A new current boundary"]});
                publish_retained(&state, &http, &url, &direction).await;
            }
            _ => {
                let mut native = state.authority_comments.lock().unwrap()[0].clone();
                match defect {
                    "original-body" => native["body"] = json!("Changed Outcome"),
                    "original-actor" => native["user"]["id"] = json!(999),
                    _ => {
                        native["issue_url"] =
                            json!("https://api.github.com/repos/another/repository/issues/24")
                    }
                };
                state
                    .authority_sources
                    .lock()
                    .unwrap()
                    .insert(format!("issues/comments/{}", reference["id"]), native);
            }
        }
        let before = state.requests.lock().unwrap().len();
        let rejected = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(rejected["result"]["isError"], true, "{defect}: {rejected}");
        assert!(
            !state.requests.lock().unwrap()[before..]
                .iter()
                .any(|path| path.starts_with("POST ") && path.contains("/repos/")),
            "{defect}: {rejected}"
        );
        assert_eq!(outcome["admission"]["attempt"], "run-10");
        assert!(state.reviews.lock().unwrap().is_empty());
    }
}

#[tokio::test]
async fn verified_nonstandard_resolution_proves_equivalent_defaults_and_old_outcomes_show_only_real_gaps(
) {
    for resolved in [false, true] {
        let state = admitted();
        let (_, mut outcome) = outcome_v4(
            &state,
            authority_v4(vec![], Value::Null, Value::Null),
            json!({"kind":"issue","number":24}),
            json!({"kind":"git","revision":HEAD,"identities":[]}),
        );
        if resolved {
            outcome["authority_resolution"] = json!({"project_defaults":{"model":"project-model","effort":"high","subagents":false,"validation":["diff-check"]},
                "purpose":"Original configured purpose","starting_state":{"branch":"codex/task-24","base_sha":"b".repeat(40),"starting_head":HEAD,"existing_pr":25}});
            crate::task_authority::validate_record(&outcome).unwrap();
            state.authority_comments.lock().unwrap()[0]["body"] =
                json!(crate::task_authority::render(&outcome));
        }
        let original_body = state.authority_comments.lock().unwrap()[0]["body"].clone();
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let mut decision = decision_v4();
        decision["amendments"] = json!({"model":"project-model","effort":"high","subagents":false,"validation":["diff-check"],"purpose":"Original configured purpose","branch":"codex/task-24","base_sha":"b".repeat(40),"starting_head":HEAD,"existing_pr":25});
        publish_retained(&state, &http, &url, &decision).await;
        let preview=rpc(&http,&url,1,"tools/call",json!({"name":"check_pr_review_target","arguments":{"repository":TEST_REPOSITORY,"pr_number":25,"expected_head_sha":HEAD}})).await;
        let acceptance = &preview["result"]["structuredContent"]["task_acceptance"];
        assert_eq!(
            acceptance["authority_drift"]["changed_fields"],
            json!([]),
            "{preview}"
        );
        assert_eq!(
            acceptance["authority_drift"]["review_required"], !resolved,
            "{preview}"
        );
        if resolved {
            assert!(acceptance["authority_drift"]
                .get("comparison_gaps")
                .is_none());
        } else {
            assert_eq!(
                acceptance["authority_drift"]["comparison_gaps"],
                json!([
                    "base_sha",
                    "branch",
                    "effort",
                    "existing_pr",
                    "model",
                    "purpose",
                    "starting_head",
                    "subagents",
                    "validation"
                ])
            );
        }
        let rejected = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":base_args("APPROVE")}),
        )
        .await;
        if resolved {
            assert_eq!(
                rejected["result"]["content"][0]["text"], "PUBLISHED",
                "{rejected}"
            );
        } else {
            assert_eq!(
                rejected["result"]["content"][0]["text"],
                "AUTHORITY_APPROVAL_CURRENT_TASK_REQUIRED"
            );
            assert!(state.reviews.lock().unwrap().is_empty());
            assert!(state.check_runs.lock().unwrap().is_empty());
        }
        assert_eq!(
            state.authority_comments.lock().unwrap()[0]["body"],
            original_body
        );
    }
}

#[test]
fn drift_shape_rejects_invalid_digest_flags_unsorted_or_overlapping_gaps() {
    let state = admitted();
    let (_, outcome) = outcome_v4(
        &state,
        authority_v4(vec![], Value::Null, Value::Null),
        json!({"kind":"issue","number":24}),
        json!({"kind":"qualification","revision":null,"identities":[{"kind":"qualification-run","id":"shape-run"}]}),
    );
    for defect in ["digest", "flag", "sort", "overlap", "gap-sort", "gap-flag"] {
        let mut candidate = outcome.clone();
        candidate["authority_drift"] = json!({"current_authority":outcome["authority"],"changed_fields":["boundaries","scope"],"review_required":true});
        match defect {
            "digest" => {
                candidate["authority_drift"]["current_authority"]["sha256"] = json!("f".repeat(64))
            }
            "flag" => candidate["authority_drift"]["review_required"] = json!(false),
            "sort" => {
                candidate["authority_drift"]["changed_fields"] = json!(["scope", "boundaries"])
            }
            "overlap" => candidate["authority_drift"]["comparison_gaps"] = json!(["scope"]),
            "gap-sort" => {
                candidate["authority_drift"]["comparison_gaps"] = json!(["model", "effort"])
            }
            _ => {
                candidate["authority_drift"]["changed_fields"] = json!([]);
                candidate["authority_drift"]["comparison_gaps"] = json!(["model"]);
                candidate["authority_drift"]["review_required"] = json!(false);
            }
        }
        assert!(
            crate::task_authority::validate_record(&candidate).is_err(),
            "{defect}: {candidate}"
        );
    }
}
