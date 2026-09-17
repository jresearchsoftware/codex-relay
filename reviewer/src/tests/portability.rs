use super::*;

#[tokio::test]
async fn two_consumer_same_artifact_reviewer_to_writer_qualification() {
    for consumer in ["example", "canary", "inventory"] {
        let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join(format!("../consumer/fixtures/{consumer}.json"));
        let config: Value = serde_json::from_slice(&fs::read(fixture).unwrap()).unwrap();
        let policy = review_policy(&json!({
            "baseBranch":config["baseBranch"], "reviewCheckName":format!("{consumer}-review"),
            "githubApp":config["reviewerApp"], "writerActor":config["writerApp"]["expectedActor"],
            "validationNames":config.get("validationNames").cloned().unwrap_or(json!([]))
        }));
        let repository = config["repository"].as_str().unwrap();
        let state = MockState {
            repository: repository.into(),
            policy: policy.clone(),
            installation_id: policy.installation_id.clone(),
            ..Default::default()
        };
        let (http, url) = client_with_repository(true, None, state.clone(), repository).await;
        let tools_result = rpc(&http, &url, 1, "tools/list", json!({})).await;
        assert_eq!(
            tools_result["result"]["tools"][0]["inputSchema"]["properties"]["repository"]["const"],
            repository
        );
        let mut args = cr_fixture();
        args["repository"] = json!(repository);
        args["change_request"]["step"] = json!(2);
        args["change_request"]["remediation_thread_title"] =
            json!("Task 24 — Step 2 — Consumer qualification");
        if consumer == "inventory" {
            args["change_request"]["required_validation"] = config["validationNames"].clone();
            args["change_request"]["findings"][0]["problem"] =
                json!("Stock reservations can exceed available inventory.");
            args["change_request"]["findings"][0]["remediation"] =
                json!("Reject an oversubscribed reservation and preserve the API response schema.");
            let choices = &tools_result["result"]["tools"][1]["inputSchema"]["properties"]
                ["change_request"]["properties"]["required_validation"]["items"]["enum"];
            for name in config["validationNames"].as_array().unwrap() {
                assert!(choices.as_array().unwrap().contains(name));
            }
        }
        // A caller cannot extend the allowlist, even with an otherwise valid CR.
        let mut undeclared = args.clone();
        undeclared["change_request"]["required_validation"] = json!(["undeclared-check"]);
        let rejected = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":undeclared}),
        )
        .await;
        assert!(rejected.get("error").is_some() || rejected["result"]["isError"] == true);
        assert!(state.requests.lock().unwrap().is_empty());
        let mut wrong = args.clone();
        wrong["repository"] = json!("foreign/repository");
        let rejected = rpc(
            &http,
            &url,
            2,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":wrong}),
        )
        .await;
        assert!(rejected.get("error").is_some() || rejected["result"]["isError"] == true);
        assert!(state.requests.lock().unwrap().is_empty());
        for (field, value) in [
            ("/base/ref", json!("foreign-base")),
            ("/head/repo/full_name", json!("foreign/fork")),
            ("/head/sha", json!("b".repeat(40))),
        ] {
            let mut pr = live_pr_for_repository(repository);
            pr["base"]["ref"] = json!(policy.base_branch);
            *pr.pointer_mut(field).unwrap() = value;
            *state.pr.lock().unwrap() = Some(pr);
            let result = rpc(
                &http,
                &url,
                3,
                "tools/call",
                json!({"name":"submit_pr_review","arguments":args}),
            )
            .await;
            assert_eq!(result["result"]["isError"], true, "{result}");
            assert!(state.reviews.lock().unwrap().is_empty());
        }
        *state.pr.lock().unwrap() = None;
        *state.app_identity.lock().unwrap() = Some(
            json!({"slug":config["writerApp"]["slug"],"id":config["writerApp"]["appId"].as_str().unwrap().parse::<u64>().unwrap()}),
        );
        let rejected = rpc(
            &http,
            &url,
            4,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(rejected["result"]["isError"], true);
        assert!(state.reviews.lock().unwrap().is_empty());
        *state.app_identity.lock().unwrap() = None;
        let result = rpc(
            &http,
            &url,
            5,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_ne!(result["result"]["isError"], true, "{result}");
        assert_eq!(
            result["result"]["structuredContent"]["actor_login"],
            policy.actor
        );
        let publication = state.reviews.lock().unwrap()[0].clone();
        assert_consumer_admits_with_config(&args, &publication, consumer);
        rpc(
            &http,
            &url,
            6,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(state.reviews.lock().unwrap().len(), 1);
        assert_eq!(
            state
                .requests
                .lock()
                .unwrap()
                .iter()
                .filter(|r| r.starts_with("POST ") && r.ends_with("/check-runs"))
                .count(),
            1
        );
        assert!(state
            .token_requests
            .lock()
            .unwrap()
            .iter()
            .all(|t| t["repositories"] == json!([repository.split('/').nth(1).unwrap()])));
    }
}

#[test]
fn declared_validation_names_are_bounded_and_fail_closed() {
    for names in [
        json!(null),
        json!("pytest"),
        json!(["pytest", "pytest"]),
        json!(["pytest;id"]),
        json!(["UPPER"]),
        json!(["a".repeat(65)]),
        json!((0..33).map(|n| format!("check-{n}")).collect::<Vec<_>>()),
    ] {
        assert!(std::panic::catch_unwind(|| executable_cr::validation_names(
            &json!({"validationNames":names})
        ))
        .is_err());
    }
    let names = executable_cr::validation_names(&json!({"validationNames":["pytest-inventory"]}));
    let mut args = cr_fixture();
    args["change_request"]["required_validation"] = json!(["pytest-inventory"]);
    assert!(executable_cr::render(&names, &args).is_ok());
    assert_eq!(
        executable_cr::render(&[], &args),
        Err("CR_VALIDATION_INVALID")
    );
}

#[test]
fn plain_reviewer_example_and_publication_mode_are_unambiguous() {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../examples/reviewer-mcp.json");
    assert_eq!(
        load_runtime_config(path.to_str().unwrap()).policy,
        test_policy()
    );
    assert!(publication_enabled(Some("true")));
    for value in [None, Some("false"), Some("TRUE"), Some("1"), Some("")] {
        assert!(!publication_enabled(value));
    }
    let mut config: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    config["mutation"] = json!("none");
    let temporary =
        std::env::temp_dir().join(format!("relay-obsolete-mode-{}.json", std::process::id()));
    fs::write(&temporary, config.to_string()).unwrap();
    assert!(std::panic::catch_unwind(|| load_runtime_config(temporary.to_str().unwrap())).is_err());
    fs::remove_file(temporary).unwrap();
}

#[tokio::test]
async fn disabled_publication_has_no_github_mutation_for_either_action() {
    let state = MockState::default();
    let (http, url) = client_with_state(false, None, state.clone()).await;
    for args in [cr_fixture(), base_args("APPROVE")] {
        let result = rpc(
            &http,
            &url,
            1,
            "tools/call",
            json!({"name":"submit_pr_review","arguments":args}),
        )
        .await;
        assert_eq!(result["result"]["content"][0]["text"], "RELAY_DISABLED");
    }
    assert!(state.requests.lock().unwrap().is_empty());
    assert!(state.reviews.lock().unwrap().is_empty());
}

#[test]
fn consumer_policy_has_no_implicit_identity_or_base() {
    let base = json!({"baseBranch":"trunk", "reviewCheckName":"fixture-review", "writerActor":"fixture-writer[bot]",
        "githubApp":{"slug":"fixture-reviewer", "appId":"702", "installationId":"802", "expectedActor":"fixture-reviewer[bot]"}});
    assert_eq!(review_policy(&base).base_branch, "trunk");
    for field in ["baseBranch", "reviewCheckName", "writerActor", "githubApp"] {
        let mut config = base.clone();
        config.as_object_mut().unwrap().remove(field);
        assert!(std::panic::catch_unwind(|| review_policy(&config)).is_err());
    }
    for (pointer, value) in [
        ("/baseBranch", json!("../main")),
        ("/githubApp/appId", json!("unknown")),
        ("/writerActor", json!("malformed actor[bot]")),
        ("/githubApp/expectedActor", json!("wrong[bot]")),
        ("/writerActor", json!("fixture-reviewer[bot]")),
    ] {
        let mut config = base.clone();
        *config.pointer_mut(pointer).unwrap() = value;
        assert!(std::panic::catch_unwind(|| review_policy(&config)).is_err());
    }
}
