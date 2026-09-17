//! Exercise the actual HTTP JSON-RPC boundary, with only GitHub mocked.
//! These tests do not simulate or claim to qualify the ChatGPT connector adapter.
use super::*;

fn assert_observed(state: &MockState, name: &str, arguments: &Value) {
    assert_eq!(
        state.observed_arguments.lock().unwrap().last(),
        Some(&(name.to_string(), arguments.clone())),
        "arguments immediately before valid_input must equal the supplied object"
    );
}

fn assert_no_publication(state: &MockState) {
    assert!(state.reviews.lock().unwrap().is_empty());
    assert!(!state.requests.lock().unwrap().iter().any(|request| {
        request.starts_with("POST /repos/") || request.starts_with("PATCH /repos/")
    }));
}

#[tokio::test]
async fn listed_schema_and_complete_calls_preserve_repository_for_both_actions() {
    let state = MockState::default();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let listed = rpc(&http, &url, 1, "tools/list", json!({})).await;
    // Neutralized fixture of the older conditional-root tool schema.
    // It reproduces a transport regression, not a second schema authority.
    let baseline: Value =
        serde_json::from_str(include_str!("fixtures/legacy-tools-list.json")).unwrap();
    assert_eq!(
        baseline["result"]["tools"][1]["inputSchema"]["oneOf"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    let schemas = listed["result"]["tools"].as_array().unwrap();
    assert_eq!(schemas.len(), 2);
    let check_schema = &schemas[0]["inputSchema"];
    let submit_schema = &schemas[1]["inputSchema"];
    assert_eq!(schemas[0]["name"], "check_pr_review_target");
    assert_eq!(schemas[1]["name"], "submit_pr_review");
    assert_eq!(submit_schema["properties"]["action"]["type"], "string");
    assert_eq!(
        submit_schema["properties"]["action"]["enum"],
        json!(["APPROVE", "REQUEST_CHANGES"])
    );
    let mut current_cr = submit_schema["properties"]["change_request"].clone();
    let mut baseline_cr =
        baseline["result"]["tools"][1]["inputSchema"]["properties"]["change_request"].clone();
    // Step/profile descriptions evolve independently. Preserve the fixture
    // and compare every structural constraint; Step behavior has native tests.
    for schema in [&mut current_cr, &mut baseline_cr] {
        for field in ["step", "remediation_thread_title"] {
            schema["properties"][field]
                .as_object_mut()
                .unwrap()
                .remove("description");
        }
    }
    assert_eq!(current_cr, baseline_cr);
    let repository = check_schema["properties"]["repository"]["const"].clone();
    assert_eq!(
        submit_schema["properties"]["repository"]["const"],
        repository
    );
    for schema in [check_schema, submit_schema] {
        for conditional in ["oneOf", "anyOf", "allOf", "if", "then", "else", "not"] {
            assert!(schema.get(conditional).is_none(), "root {conditional}");
        }
        assert_eq!(schema["type"], "object");
        assert_eq!(schema["additionalProperties"], false);
        let mut required = vec!["repository", "pr_number", "expected_head_sha"];
        if schema.get("properties").unwrap().get("action").is_some() {
            required.push("action");
        }
        assert_eq!(schema["required"], json!(required));
        for field in required {
            assert!(schema["properties"][field]["type"].is_string());
        }
    }

    let check = json!({"repository":repository,"pr_number":25,"expected_head_sha":HEAD});
    let checked = rpc(
        &http,
        &url,
        2,
        "tools/call",
        json!({
            "name":"check_pr_review_target", "arguments":check
        }),
    )
    .await;
    assert_eq!(
        checked["result"]["structuredContent"]["ready_for_review"],
        true
    );
    assert_observed(&state, "check_pr_review_target", &check);

    // Deliberately stale APPROVE reproduces the incident's safe diagnostic shape.
    // Repeat for structured REQUEST_CHANGES to isolate CR rendering from transport.
    for action in ["APPROVE", "REQUEST_CHANGES"] {
        let mut arguments = base_args(action);
        arguments["repository"] = repository.clone();
        arguments["expected_head_sha"] = json!("0".repeat(40));
        let result = rpc(
            &http,
            &url,
            3,
            "tools/call",
            json!({
                "name":"submit_pr_review", "arguments":arguments
            }),
        )
        .await;
        assert_observed(&state, "submit_pr_review", &arguments);
        assert_eq!(result["result"]["content"][0]["text"], "STALE_HEAD");
        assert_eq!(result["result"]["isError"], true);
        assert_no_publication(&state);
    }

    let mut arguments = cr_fixture();
    arguments["repository"] = repository;
    let result = rpc(
        &http,
        &url,
        4,
        "tools/call",
        json!({
            "name":"submit_pr_review", "arguments":arguments
        }),
    )
    .await;
    assert_observed(&state, "submit_pr_review", &arguments);
    assert_eq!(result["result"]["content"][0]["text"], "PUBLISHED");
    let publications = state.reviews.lock().unwrap();
    assert_eq!(publications.len(), 1);
    assert_consumer_admits(&arguments, &publications[0]);
}

#[tokio::test]
async fn repository_error_requires_changed_input_and_is_not_action_specific() {
    let state = MockState::default();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    for action in [None, Some("APPROVE"), Some("REQUEST_CHANGES")] {
        let (name, arguments) = match action {
            Some(action) => ("submit_pr_review", base_args(action)),
            None => (
                "check_pr_review_target",
                json!({
                    "repository":base_args("APPROVE")["repository"],
                    "pr_number":25,"expected_head_sha":HEAD
                }),
            ),
        };
        let mut missing = arguments.clone();
        missing.as_object_mut().unwrap().remove("repository");
        let mut wrong = arguments.clone();
        wrong["repository"] = json!("example/other");
        let mut wrongly_typed = arguments.clone();
        wrongly_typed["repository"] = json!([arguments["repository"]]);
        for (changed, code) in [
            (missing, "REPOSITORY_NOT_ALLOWED"),
            (wrong, "REPOSITORY_NOT_ALLOWED"),
            (wrongly_typed, "REPOSITORY_NOT_ALLOWED"),
            (json!({}), "REPOSITORY_NOT_ALLOWED"),
            (json!({"arguments":arguments}), "INVALID_PAYLOAD"),
            (
                json!(serde_json::to_string(&arguments).unwrap()),
                "INVALID_PAYLOAD",
            ),
            (Value::Null, "INVALID_PAYLOAD"),
        ] {
            let result = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({
                    "name":name,"arguments":changed
                }),
            )
            .await;
            assert_observed(&state, name, &changed);
            assert_eq!(result["result"]["content"][0]["text"], code);
        }
        if let Some(action) = action {
            // The sanitized live incident contained only action; it must remain rejected.
            let truncated = json!({"action": action});
            let result = rpc(
                &http,
                &url,
                2,
                "tools/call",
                json!({
                    "name": name, "arguments": truncated
                }),
            )
            .await;
            assert_observed(&state, name, &truncated);
            assert_eq!(
                result["result"]["content"][0]["text"],
                "REPOSITORY_NOT_ALLOWED"
            );
        }
    }
    assert!(state.requests.lock().unwrap().is_empty());
    assert_no_publication(&state);
}

#[tokio::test]
async fn unchanged_repository_reaches_action_specific_validation_before_github() {
    let state = MockState::default();
    let (http, url) = client_with_state(true, None, state.clone()).await;
    let mut malformed_cr = cr_fixture();
    malformed_cr["change_request"]["findings"] = json!([]);
    let mut prose_cr = cr_fixture();
    prose_cr["review_body"] = json!("Caller-rendered executable prose is disallowed.");
    let mut findings_cr = cr_fixture();
    findings_cr["structured_findings"] = json!([]);
    let mut remediation_approval = base_args("APPROVE");
    remediation_approval["change_request"] = cr_fixture()["change_request"].clone();
    let mut empty_approval = base_args("APPROVE");
    empty_approval["review_body"] = json!("");
    for (arguments, code) in [
        (malformed_cr, "INVALID_CHANGE_REQUEST"),
        (prose_cr, "STRUCTURED_CHANGE_REQUEST_REQUIRED"),
        (findings_cr, "STRUCTURED_CHANGE_REQUEST_REQUIRED"),
        (remediation_approval, "APPROVAL_REMEDIATION_FIELDS"),
        (empty_approval, "INVALID_REVIEW_BODY"),
    ] {
        let result = rpc(
            &http,
            &url,
            1,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":arguments}),
        )
        .await;
        assert_observed(&state, "submit_pr_review", &arguments);
        assert_eq!(result["result"]["content"][0]["text"], code);
    }
    assert!(state.requests.lock().unwrap().is_empty());
    assert_no_publication(&state);
}

fn invalid_repositories() -> Vec<Value> {
    vec![
        Value::Null,
        json!(false),
        json!(42),
        json!([]),
        json!({}),
        json!(""),
        json!("example"),
        json!("/alpha"),
        json!("example/"),
        json!("example/alpha/extra"),
        json!("https://github.com/example/alpha"),
        json!("example\\alpha"),
        json!(" example/alpha"),
        json!("example/alpha "),
        json!("example/alpha\n"),
        json!("example/al\u{0000}pha"),
        json!("example/álpha"),
        json!("example/al%70ha"),
        json!("example/alpha?x=1"),
        json!("example/alpha#fragment"),
        json!("example/."),
        json!("example/.."),
        json!("-example/alpha"),
        json!("example-/alpha"),
        json!("ex--ample/alpha"),
        json!("ex_ample/alpha"),
        json!(format!("{}/alpha", "a".repeat(40))),
        json!(format!("example/{}", "a".repeat(101))),
    ]
}

#[test]
fn runtime_repository_admission_is_bounded_and_required() {
    let base: Value = serde_json::from_str(&rendered_runtime_config("example/alpha")).unwrap();
    let path = std::env::temp_dir().join(format!(
        "reviewer-repository-admission-{}.json",
        std::process::id()
    ));
    for repository in [
        "example/alpha".to_string(),
        "example/beta".to_string(),
        "A/b".to_string(),
        "owner-name/.repo_1-2".to_string(),
        format!("{}/{}", "a".repeat(39), "b".repeat(100)),
    ] {
        let mut config = base.clone();
        config["repository"] = json!(repository);
        fs::write(&path, config.to_string()).unwrap();
        assert_eq!(
            load_runtime_config(path.to_str().unwrap()).repository,
            repository
        );
    }
    for repository in std::iter::once(None).chain(invalid_repositories().into_iter().map(Some)) {
        let mut config = base.clone();
        match repository {
            Some(value) => config["repository"] = value,
            None => {
                config.as_object_mut().unwrap().remove("repository");
            }
        }
        fs::write(&path, config.to_string()).unwrap();
        assert!(std::panic::catch_unwind(|| load_runtime_config(path.to_str().unwrap())).is_err());
    }
    fs::remove_file(path).unwrap();
}

fn repository_calls(repository: &str) -> Vec<(&'static str, Value)> {
    let mut calls = vec![(
        "check_pr_review_target",
        json!({
            "repository": repository, "pr_number": 25, "expected_head_sha": HEAD
        }),
    )];
    for action in ["APPROVE", "REQUEST_CHANGES"] {
        let mut arguments = base_args(action);
        arguments["repository"] = json!(repository);
        calls.push(("submit_pr_review", arguments));
    }
    calls
}

#[tokio::test]
async fn wrong_app_or_returned_review_actor_fails_closed_through_http() {
    for identity in [json!({"slug":"other-reviewer"}), json!({}), Value::Null] {
        let state = MockState::default();
        *state.app_identity.lock().unwrap() = Some(identity);
        let (http, url) = client_with_state(true, None, state.clone()).await;
        for (name, arguments) in repository_calls(TEST_REPOSITORY) {
            let result = rpc(
                &http,
                &url,
                1,
                "tools/call",
                json!({
                    "name": name, "arguments": arguments
                }),
            )
            .await;
            assert_observed(&state, name, &arguments);
            assert_eq!(
                result["result"]["content"][0]["text"],
                "ACTOR_VERIFICATION_FAILED"
            );
            assert_eq!(result["result"]["isError"], true);
        }
        assert_no_publication(&state);
    }

    for action in ["APPROVE", "REQUEST_CHANGES"] {
        let arguments = base_args(action);
        let payload = json!({
            "commit_id": HEAD, "event": action,
            "body": native_review_body(&[], &arguments, &operation_id(&[], &arguments))
        });
        let mut response = native_review(&payload);
        response["user"]["login"] = json!("other-reviewer[bot]");
        let state = MockState::default();
        *state.review_response.lock().unwrap() = Some(response);
        let (http, url) = client_with_state(true, None, state.clone()).await;
        let result = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({
                "name": "submit_pr_review", "arguments": arguments
            }),
        )
        .await;
        assert_eq!(
            result["result"]["content"][0]["text"],
            "ACTOR_VERIFICATION_FAILED"
        );
        assert_eq!(result["result"]["isError"], true);
        // GitHub was called, but an unverified review must not become a successful
        // result or trigger a check publication.
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
        assert!(!state
            .requests
            .lock()
            .unwrap()
            .iter()
            .any(|r| r.ends_with("/check-runs")));
    }
}

#[tokio::test]
async fn managed_config_instances_bind_tools_tokens_and_publications_to_their_own_repository() {
    let mut instances = Vec::new();
    for (index, (repository, token_repository)) in
        [("example/alpha", "alpha"), ("example/beta", "beta")]
            .iter()
            .enumerate()
    {
        // Exercise the real managed template -> config admission -> App -> MCP path.
        let path = std::env::temp_dir().join(format!(
            "reviewer-repository-instance-{}-{index}.json",
            std::process::id()
        ));
        fs::write(&path, rendered_runtime_config(repository)).unwrap();
        let config = effective_runtime_config(&Args {
            config: path.to_str().unwrap().into(),
        });
        fs::remove_file(path).unwrap();
        let state = MockState {
            repository: repository.to_string(),
            ..MockState::default()
        };
        let (http, url) =
            client_with_repository(true, None, state.clone(), &config.repository).await;
        instances.push((config.repository, *token_repository, state, http, url));
    }

    // Both differently configured instances remain alive in the same test binary.
    for (repository, token_repository, state, http, url) in &instances {
        let listed = rpc(http, url, 1, "tools/list", json!({})).await;
        let schemas = listed["result"]["tools"].as_array().unwrap();
        assert_eq!(schemas.len(), 2);
        for tool in schemas {
            assert_eq!(
                tool["inputSchema"]["properties"]["repository"]["const"],
                *repository
            );
            assert_eq!(
                tool["inputSchema"]["properties"]["repository"]["type"],
                "string"
            );
            assert!(tool["inputSchema"]["required"]
                .as_array()
                .unwrap()
                .contains(&json!("repository")));
        }
        let peer = instances
            .iter()
            .find(|(other, _, _, _, _)| other != repository)
            .unwrap();
        let mut rejected = invalid_repositories();
        rejected.extend([
            json!(peer.0),
            json!(TEST_REPOSITORY),
            json!(repository.to_uppercase()),
        ]);
        for (name, arguments) in repository_calls(repository) {
            for rejected_repository in
                std::iter::once(None).chain(rejected.iter().cloned().map(Some))
            {
                let mut changed = arguments.clone();
                match rejected_repository {
                    Some(value) => changed["repository"] = value,
                    None => {
                        changed.as_object_mut().unwrap().remove("repository");
                    }
                }
                let result = rpc(
                    http,
                    url,
                    2,
                    "tools/call",
                    json!({
                        "name": name, "arguments": changed
                    }),
                )
                .await;
                assert_observed(state, name, &changed);
                assert_eq!(result["result"]["isError"], true);
                assert_eq!(
                    result["result"]["content"][0]["text"],
                    "REPOSITORY_NOT_ALLOWED"
                );
            }
        }
        assert!(state.requests.lock().unwrap().is_empty());
        assert!(state.token_requests.lock().unwrap().is_empty());
        assert_no_publication(state);

        for (name, arguments) in repository_calls(repository) {
            let previous_tokens = state.token_requests.lock().unwrap().len();
            let result = rpc(
                http,
                url,
                3,
                "tools/call",
                json!({
                    "name": name, "arguments": arguments
                }),
            )
            .await;
            let tokens = state.token_requests.lock().unwrap();
            assert!(tokens.len() > previous_tokens, "{repository}: {name}");
            for payload in &tokens[previous_tokens..] {
                assert_eq!(
                    payload,
                    &json!({
                        "repositories": [token_repository],
                        "permissions": {
                            "metadata": "read", "pull_requests": "write", "checks": "write"
                        }
                    }),
                    "{repository}: {name} installation-token scope"
                );
            }
            drop(tokens);
            assert_observed(state, name, &arguments);
            if name == "check_pr_review_target" {
                assert_eq!(
                    result["result"]["structuredContent"]["ready_for_review"],
                    true
                );
            } else {
                assert_eq!(result["result"]["content"][0]["text"], "PUBLISHED");
            }
        }
        let reviews = state.reviews.lock().unwrap();
        assert_eq!(reviews.len(), 2);
        assert_eq!(reviews[0]["event"], "APPROVE");
        assert_eq!(reviews[1]["event"], "REQUEST_CHANGES");
        assert!(reviews[1]["body"]
            .as_str()
            .unwrap()
            .contains(&format!("Repository: {repository}")));
        let requests = state.requests.lock().unwrap();
        assert_eq!(
            state.token_requests.lock().unwrap().len(),
            requests.iter().filter(|r| r.contains(" /repos/")).count(),
            "every repository API request must use a scoped installation token"
        );
        for request in requests.iter() {
            if let Some((_, target)) = request.split_once(" /repos/") {
                assert!(target.starts_with(&format!("{repository}/")), "{request}");
            }
        }
        assert_eq!(
            requests
                .iter()
                .filter(|r| **r == format!("POST /repos/{repository}/check-runs"))
                .count(),
            2
        );
    }
}
