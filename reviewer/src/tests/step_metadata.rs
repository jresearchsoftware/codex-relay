use super::*;

fn issue(labels: Value) -> Value {
    json!({"number":24,"state":"open","user":{"login":"example-owner","type":"User"},"body":"Canonical task authority","labels":labels})
}

#[test]
fn canonical_link_parser_preserves_native_controller_boundaries() {
    for body in [
        "Related to #24",
        "text(Fixes #24)",
        "\"CLOSES #24\"",
        "Related\nTo\t#24",
        "Resolves\u{feff}#24",
    ] {
        assert_eq!(step_sync::linked_issue(&json!({"body":body})), Ok(24));
    }
    for body in [
        "Unfixes #24",
        "Fixes #24A",
        "Fixes #024",
        "Fixes:#24",
        "Related to #24 and fixes #26",
    ] {
        assert_eq!(
            step_sync::linked_issue(&json!({"body":body})),
            Err("CANONICAL_ISSUE_AMBIGUOUS")
        );
    }
}

async fn publish(http: &reqwest::Client, url: &str, args: &Value) -> Value {
    rpc(
        http,
        url,
        1,
        "tools/call",
        json!({"name":"submit_pr_review","arguments":args}),
    )
    .await
}

#[tokio::test]
async fn partial_metadata_recovery_preserves_native_review_and_step_at_every_stage() {
    for stage in ["issues/24/labels", "issues/25/labels", "pulls/25"] {
        let state = MockState::default();
        *state.issue.lock().unwrap() = Some(issue(json!([{"name":"step-1"},{"name":"priority"}])));
        let mut pr = live_pr();
        pr["labels"] = json!([{"name":"step-1"},{"name":"topic"}]);
        *state.pr.lock().unwrap() = Some(pr);
        *state.metadata_failure.lock().unwrap() = Some(stage.into());
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let args = cr_fixture();
        let failed = publish(&http, &url, &args).await;
        assert_eq!(
            failed.pointer("/result/content/0/text"),
            Some(&json!("REVIEW_PUBLISHED_METADATA_FAILED")),
            "{stage}: {failed}"
        );
        assert_eq!(
            failed.pointer("/result/structuredContent/review_id"),
            Some(&json!(1))
        );
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
        let recovered = publish(&http, &url, &args).await;
        assert_eq!(
            recovered.pointer("/result/content/0/text"),
            Some(&json!("CHECK_RECOVERED")),
            "{stage}: {recovered}"
        );
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
        assert_eq!(
            state.issue.lock().unwrap().as_ref().unwrap()["labels"],
            json!([{"name":"priority"},{"name":"step-2"}])
        );
        let pr = state.pr.lock().unwrap().clone().unwrap();
        assert_eq!(pr["labels"], json!([{"name":"topic"},{"name":"step-2"}]));
        assert_eq!(pr["title"], step_sync::projection_title(24, &args).unwrap());
        assert!(pr["title"]
            .as_str()
            .unwrap()
            .starts_with("Task 24 · Step 2 · CR-24-serialization · "));
        let writes = state
            .requests
            .lock()
            .unwrap()
            .iter()
            .filter(|r| r.starts_with("PUT ") || r.starts_with("PATCH "))
            .count();
        let duplicate = publish(&http, &url, &args).await;
        assert_eq!(
            duplicate.pointer("/result/content/0/text"),
            Some(&json!("DUPLICATE_SUPPRESSED"))
        );
        assert_eq!(
            state
                .requests
                .lock()
                .unwrap()
                .iter()
                .filter(|r| r.starts_with("PUT ") || r.starts_with("PATCH "))
                .count(),
            writes
        );
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
    }
}

#[tokio::test]
async fn issue_and_title_authority_fail_before_new_review() {
    for (labels, code) in [
        (json!([]), "STEP_LABEL_MISSING"),
        (json!([{"name":"step-01"}]), "STEP_LABEL_INVALID"),
        (
            json!([{"name":"step-1"},{"name":"step-2"}]),
            "STEP_LABEL_MULTIPLE",
        ),
        (json!([{"name":"step-2"}]), "STEP_LABEL_MISMATCH"),
        (json!([{"name":"step-9"}]), "STEP_LABEL_MISMATCH"),
    ] {
        let state = MockState::default();
        *state.issue.lock().unwrap() = Some(issue(labels));
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let result = publish(&http, &url, &cr_fixture()).await;
        assert_eq!(
            result.pointer("/result/content/0/text"),
            Some(&json!(code)),
            "{result}"
        );
        assert!(state.reviews.lock().unwrap().is_empty());
        assert!(!state
            .requests
            .lock()
            .unwrap()
            .iter()
            .any(|r| r.starts_with("PUT ") || r.starts_with("PATCH ")));
    }
    for (key, value, code) in [
        (
            "body",
            json!("Related to #24 and fixes #26"),
            "CANONICAL_ISSUE_AMBIGUOUS",
        ),
        (
            "title",
            json!("Task 99 · Step 1 · other task"),
            "STEP_DISPLAY_MISMATCH",
        ),
    ] {
        let state = MockState::default();
        let mut pr = live_pr();
        pr[key] = value;
        *state.pr.lock().unwrap() = Some(pr);
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let result = publish(&http, &url, &cr_fixture()).await;
        assert_eq!(result.pointer("/result/content/0/text"), Some(&json!(code)));
        assert!(state.reviews.lock().unwrap().is_empty());
    }
}

#[tokio::test]
async fn only_configured_human_owner_issue_can_authorize_metadata_projection() {
    for user in [
        json!({"login":"another-owner","type":"User"}),
        json!({"login":"example-owner","type":"Bot"}),
        json!({"login":"example-owner"}),
        json!({"type":"User"}),
        Value::Null,
    ] {
        let state = MockState::default();
        let mut target = issue(json!([{"name":"step-1"}]));
        target["user"] = user;
        *state.issue.lock().unwrap() = Some(target);
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let result = publish(&http, &url, &cr_fixture()).await;
        assert_eq!(result["result"]["content"][0]["text"], "ISSUE_NOT_ADMITTED");
        assert!(state.reviews.lock().unwrap().is_empty());
        assert!(!state.requests.lock().unwrap().iter().any(|r| {
            r.starts_with("PUT ")
                || r.starts_with("PATCH ")
                || (r.starts_with("POST ") && !r.ends_with("/access_tokens"))
        }));
    }
}

#[tokio::test]
async fn changed_authority_blocks_partial_recovery_before_another_metadata_write() {
    for change in [
        "issue-body",
        "issue-author",
        "pr-body",
        "head",
        "review",
        "foreign-step",
        "title-previous-step",
        "title-next-step",
    ] {
        let state = MockState::default();
        *state.metadata_failure.lock().unwrap() = Some("issues/25/labels".into());
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let args = cr_fixture();
        let result = publish(&http, &url, &args).await;
        assert_eq!(
            result.pointer("/result/content/0/text"),
            Some(&json!("REVIEW_PUBLISHED_METADATA_FAILED"))
        );
        match change {
            "issue-body" => {
                state.issue.lock().unwrap().as_mut().unwrap()["body"] = json!("New authority")
            }
            "issue-author" => {
                state.issue.lock().unwrap().as_mut().unwrap()["user"] =
                    json!({"login":"another-owner","type":"User"})
            }
            "pr-body" => {
                let mut pr = live_pr();
                pr["body"] = json!("Related to #26");
                *state.pr.lock().unwrap() = Some(pr);
            }
            "head" => {
                let mut pr = live_pr();
                pr["head"]["sha"] = json!("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
                *state.pr.lock().unwrap() = Some(pr);
            }
            "review" => {
                *state.decisive_override.lock().unwrap() = Some(
                    json!([{"id":2,"state":"APPROVED","user":{"login":"example-reviewer[bot]"},"commit_id":HEAD,"body":"Later verdict"}]),
                )
            }
            "foreign-step" => {
                state.issue.lock().unwrap().as_mut().unwrap()["labels"] = json!([{"name":"step-7"}])
            }
            "title-previous-step" | "title-next-step" => {
                let mut pr = live_pr();
                pr["title"] = json!(if change == "title-previous-step" {
                    "Task 24 · Step 1 · Different owner phase"
                } else {
                    "Task 24 · Step 2 · CR-other · Different authority"
                });
                *state.pr.lock().unwrap() = Some(pr);
            }
            _ => unreachable!(),
        }
        let before = state.requests.lock().unwrap().len();
        let retry = publish(&http, &url, &args).await;
        assert_eq!(
            retry.pointer("/result/isError"),
            Some(&json!(true)),
            "{change}: {retry}"
        );
        assert!(!state.requests.lock().unwrap()[before..]
            .iter()
            .any(|r| r.starts_with("PUT ") || r.starts_with("PATCH ")));
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
    }
}

#[tokio::test]
async fn approve_never_projects_step_metadata() {
    let state = MockState::default();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let result = publish(&http, &url, &base_args("APPROVE")).await;
    assert_eq!(
        result.pointer("/result/content/0/text"),
        Some(&json!("PUBLISHED"))
    );
    assert!(!state
        .requests
        .lock()
        .unwrap()
        .iter()
        .any(|r| r.starts_with("PUT ") || r.starts_with("PATCH ") || r.contains("/issues/")));
}

#[tokio::test]
async fn historical_durable_review_requires_explicit_reconciliation_before_anchor_adoption() {
    let state = MockState::default();
    let args = cr_fixture();
    let operation = operation_id(&[], &args);
    state.reviews.lock().unwrap().push(json!({"commit_id":HEAD,"event":"REQUEST_CHANGES","body":native_review_body(&[], &args, &operation)}));
    let store = store::Store::open(":memory:").unwrap();
    store.reserve(&operation, "digest").unwrap();
    store
        .review_published(
            &operation,
            1,
            "https://example/reviews/1",
            "example-reviewer[bot]",
        )
        .unwrap();
    store
        .published(&operation, 2, "https://example/check/2")
        .unwrap();
    let app = App {
        policy: test_policy(),
        repository: TEST_REPOSITORY.into(),
        enabled: true,
        store: Arc::new(Mutex::new(store)),
        github: github::Github::mock_api(mock_api(state.clone()).await),
        trusted_client_ca: Arc::new(Vec::new()),
        observed_arguments: Default::default(),
    };
    assert_eq!(
        step_sync::synchronize(&app, &operation, 1, &args).await,
        Err("LEGACY_STEP_BINDING_REQUIRED")
    );
    assert!(!state
        .requests
        .lock()
        .unwrap()
        .iter()
        .any(|r| r.starts_with("PUT ") || r.starts_with("PATCH ")));
    assert!(app
        .store
        .lock()
        .unwrap()
        .step_binding(&operation)
        .unwrap()
        .is_none());
    *state.issue.lock().unwrap() = Some(issue(json!([{"name":"step-2"}])));
    let mut pr = live_pr();
    pr["labels"] = json!([{"name":"step-2"}]);
    pr["title"] = json!(step_sync::projection_title(24, &args).unwrap());
    *state.pr.lock().unwrap() = Some(pr);
    step_sync::synchronize(&app, &operation, 1, &args)
        .await
        .unwrap();
    assert!(app
        .store
        .lock()
        .unwrap()
        .step_binding(&operation)
        .unwrap()
        .is_some());
    assert_eq!(state.reviews.lock().unwrap().len(), 1);
    assert!(!state
        .requests
        .lock()
        .unwrap()
        .iter()
        .any(|r| r.starts_with("PUT ") || r.starts_with("PATCH ")));
}

#[tokio::test]
async fn historical_anchor_without_exact_title_only_upgrades_complete_unchanged_projection() {
    for scenario in ["partial", "complete", "changed-authority"] {
        let state = MockState::default();
        let args = cr_fixture();
        let operation = operation_id(&[], &args);
        state.reviews.lock().unwrap().push(json!({
            "commit_id":HEAD,"event":"REQUEST_CHANGES",
            "body":native_review_body(&[], &args, &operation)
        }));
        let store = store::Store::open(":memory:").unwrap();
        store.reserve(&operation, "digest").unwrap();
        let app = App {
            policy: test_policy(),
            repository: TEST_REPOSITORY.into(),
            enabled: true,
            store: Arc::new(Mutex::new(store)),
            github: github::Github::mock_api(mock_api(state.clone()).await),
            trusted_client_ca: Arc::new(Vec::new()),
            observed_arguments: Default::default(),
        };
        step_sync::prepare(&app, &operation, &args).await.unwrap();
        let anchor = app
            .store
            .lock()
            .unwrap()
            .step_binding(&operation)
            .unwrap()
            .unwrap();
        let mut old: Value = serde_json::from_str(&anchor).unwrap();
        old.as_object_mut().unwrap().remove("initial_pr_title");
        let old_text = old.to_string();
        assert!(app
            .store
            .lock()
            .unwrap()
            .upgrade_step_binding(&operation, &anchor, &old_text)
            .unwrap());
        if scenario != "partial" {
            *state.issue.lock().unwrap() = Some(issue(json!([{"name":"step-2"}])));
            let mut pr = live_pr();
            pr["labels"] = json!([{"name":"step-2"}]);
            pr["title"] = json!(step_sync::projection_title(24, &args).unwrap());
            *state.pr.lock().unwrap() = Some(pr);
        }
        if scenario == "changed-authority" {
            state.issue.lock().unwrap().as_mut().unwrap()["body"] = json!("Changed goal");
        }
        let result = step_sync::synchronize(&app, &operation, 1, &args).await;
        assert_eq!(
            result,
            match scenario {
                "complete" => Ok(()),
                "partial" => Err("LEGACY_STEP_BINDING_REQUIRED"),
                _ => Err("AUTHORITY_CHANGED"),
            }
        );
        let stored = app
            .store
            .lock()
            .unwrap()
            .step_binding(&operation)
            .unwrap()
            .unwrap();
        let stored: Value = serde_json::from_str(&stored).unwrap();
        assert_eq!(
            stored["initial_pr_title"].is_string(),
            scenario == "complete"
        );
        assert!(!state
            .requests
            .lock()
            .unwrap()
            .iter()
            .any(|r| r.starts_with("PUT ") || r.starts_with("PATCH ")));
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
    }
}
