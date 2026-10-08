//! One service, App identity and SQLite journal with overlapping native numbers.
use super::*;

const REPOSITORIES: [&str; 2] = ["example/alpha", "example/beta"];
const CHARTER: &str = "Task 24: synthetic qualification.\nAuthority model: github-native-v1\nIssue closure policy: keep-open";

#[test]
fn managed_multi_repository_template_is_accepted_by_runtime_contract() {
    let rendered = rendered_runtime_config_repositories(&REPOSITORIES);
    let config: Value = serde_json::from_str(&rendered).unwrap();
    assert_eq!(config["repositories"], json!(REPOSITORIES));
    assert!(config.get("repository").is_none());
    let path = std::env::temp_dir().join(format!(
        "reviewer-managed-multiple-repositories-{}.json",
        std::process::id()
    ));
    fs::write(&path, rendered).unwrap();
    let runtime = load_runtime_config(path.to_str().unwrap());
    assert_eq!(runtime.repositories, repository_set());
    assert_eq!(
        runtime.policy,
        ReviewPolicy {
            github_native_authority_enabled: true,
            ..test_policy()
        }
    );
    fs::remove_file(path).unwrap();
}

#[test]
fn config_normalizes_legacy_and_multiple_repositories_and_rejects_ambiguous_forms() {
    let mut config: Value =
        serde_json::from_str(&rendered_runtime_config(REPOSITORIES[0])).unwrap();
    let path = std::env::temp_dir().join(format!(
        "reviewer-multiple-repositories-{}.json",
        std::process::id()
    ));
    fs::write(&path, config.to_string()).unwrap();
    let legacy = load_runtime_config(path.to_str().unwrap());
    config.as_object_mut().unwrap().remove("repository");
    config["repositories"] = json!([REPOSITORIES[0]]);
    fs::write(&path, config.to_string()).unwrap();
    assert_eq!(load_runtime_config(path.to_str().unwrap()), legacy);

    // Repeated entries collapse into the internal set, independent of order.
    config["repositories"] = json!([REPOSITORIES[1], REPOSITORIES[0], REPOSITORIES[1]]);
    fs::write(&path, config.to_string()).unwrap();
    let multiple = load_runtime_config(path.to_str().unwrap());
    assert_eq!(multiple.repositories, repository_set());
    assert_eq!(multiple.policy, legacy.policy);

    for value in [json!(REPOSITORIES[0]), Value::Null] {
        config["repository"] = value;
        fs::write(&path, config.to_string()).unwrap();
        assert!(std::panic::catch_unwind(|| load_runtime_config(path.to_str().unwrap())).is_err());
    }
    config.as_object_mut().unwrap().remove("repository");
    let mut invalid = vec![Value::Null, json!([]), json!(REPOSITORIES[0]), json!({})];
    invalid.extend(
        transport::invalid_repositories()
            .into_iter()
            .map(|value| json!([REPOSITORIES[0], value])),
    );
    for repositories in invalid {
        config["repositories"] = repositories;
        fs::write(&path, config.to_string()).unwrap();
        assert!(std::panic::catch_unwind(|| load_runtime_config(path.to_str().unwrap())).is_err());
    }
    config.as_object_mut().unwrap().remove("repositories");
    fs::write(&path, config.to_string()).unwrap();
    assert!(std::panic::catch_unwind(|| load_runtime_config(path.to_str().unwrap())).is_err());
    fs::remove_file(path).unwrap();
}

fn repository_set() -> BTreeSet<String> {
    REPOSITORIES.into_iter().map(String::from).collect()
}

fn request(repository: &str) -> Value {
    let mut record: Value = serde_json::from_str(include_str!(
        "../../../contracts/test/fixtures/github-task-request-v3-input.json"
    ))
    .unwrap();
    record["repository"] = json!(repository);
    record["charter_sha256"] = json!(crate::task_authority::hash(CHARTER));
    record["task"] = json!(24);
    record["parent"]["number"] = json!(24);
    record["route"] = json!("manual");
    record["validation"] = json!(["diff-check"]);
    for field in ["branch", "base_sha", "starting_head"] {
        record[field] = Value::Null;
    }
    record
}

async fn mock_multiple_github(
    State(states): State<Vec<MockState>>,
    headers: HeaderMap,
    method: Method,
    uri: Uri,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let token: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
    let state = if uri.path().starts_with("/repos/") {
        states.iter().find(|state| {
            uri.path()
                .starts_with(&format!("/repos/{}/", state.repository))
        })
    } else if uri.path().ends_with("/access_tokens") {
        states.iter().find(|state| {
            token["repositories"] == json!([state.repository.split('/').nth(1).unwrap()])
        })
    } else {
        states.first()
    };
    match state {
        Some(state) => mock_github(State(state.clone()), headers, method, uri, body).await,
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn client(
    native_authority: bool,
) -> (
    reqwest::Client,
    String,
    Vec<MockState>,
    Arc<Mutex<store::Store>>,
) {
    let states: Vec<_> = REPOSITORIES.into_iter().map(|repository| {
        let mut state = MockState { repository: repository.into(), ..MockState::default() };
        state.policy.github_native_authority_enabled = native_authority;
        *state.issue.lock().unwrap() = Some(json!({"id":240,"number":24,"state":"open",
            "body":if native_authority { CHARTER } else { "Synthetic Task\nIssue closure policy: keep-open" },
            "repository_url":format!("https://api.github.com/repos/{repository}"),
            "user":{"login":"example-owner","id":1,"type":"User"},"labels":[{"name":"step-1"}]}));
        state
    }).collect();
    let github_listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let github_address = github_listener.local_addr().unwrap();
    let github_router = Router::new()
        .fallback(any(mock_multiple_github))
        .with_state(states.clone());
    tokio::spawn(async move {
        axum::serve(github_listener, github_router).await.unwrap();
    });
    let store = Arc::new(Mutex::new(store::Store::open(":memory:").unwrap()));
    let app = router(App {
        policy: states[0].policy.clone(),
        repositories: repository_set(),
        enabled: true,
        store: store.clone(),
        github: github::Github::mock_api(format!("http://{github_address}")),
        trusted_client_ca: Arc::new(Vec::new()),
        observed_arguments: Default::default(),
    });
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    (
        reqwest::Client::new(),
        format!("http://{address}/mcp"),
        states,
        store,
    )
}

async fn call(http: &reqwest::Client, url: &str, name: &str, arguments: &Value) -> Value {
    rpc(
        http,
        url,
        1,
        "tools/call",
        json!({"name":name,"arguments":arguments}),
    )
    .await["result"]
        .clone()
}

#[tokio::test]
async fn every_tool_requires_a_configured_explicit_target_before_github_access() {
    let (http, url, states, _) = client(true).await;
    let listed = rpc(&http, &url, 1, "tools/list", json!({})).await;
    for tool in listed["result"]["tools"].as_array().unwrap() {
        let schema = &tool["inputSchema"];
        assert_eq!(
            schema["properties"]["repository"],
            json!({"type":"string","enum":REPOSITORIES})
        );
        assert!(schema["required"]
            .as_array()
            .unwrap()
            .contains(&json!("repository")));
    }
    for name in [
        "check_pr_review_target",
        "submit_pr_review",
        "read_pr_review_evidence",
        "publish_task_authority",
    ] {
        let mut arguments = if name == "publish_task_authority" {
            json!({"repository":REPOSITORIES[0],"record":request(REPOSITORIES[0])})
        } else if name == "submit_pr_review" {
            base_args("APPROVE")
        } else {
            json!({"repository":REPOSITORIES[0],"pr_number":25,"expected_head_sha":HEAD})
        };
        for repository in [
            Value::Null,
            json!(false),
            json!(42),
            json!("foreign/repository"),
            json!(REPOSITORIES[0].to_uppercase()),
        ] {
            arguments["repository"] = repository;
            let result = call(&http, &url, name, &arguments).await;
            assert_eq!(result["content"][0]["text"], "REPOSITORY_NOT_ALLOWED");
            assert_eq!(result["isError"], true);
        }
        arguments.as_object_mut().unwrap().remove("repository");
        assert_eq!(
            call(&http, &url, name, &arguments).await["content"][0]["text"],
            if name == "publish_task_authority" {
                "INVALID_PAYLOAD"
            } else {
                "REPOSITORY_NOT_ALLOWED"
            }
        );
    }
    // Both repositories are admitted, but one operation cannot mix their authority.
    let result = call(
        &http,
        &url,
        "publish_task_authority",
        &json!({"repository":REPOSITORIES[0],"record":request(REPOSITORIES[1])}),
    )
    .await;
    assert_eq!(result["content"][0]["text"], "REPOSITORY_NOT_ALLOWED");
    assert!(states
        .iter()
        .all(|state| state.requests.lock().unwrap().is_empty()));
}

#[tokio::test]
async fn review_evidence_publication_and_recovery_use_one_service_without_pr_or_step_collisions() {
    let (http, url, states, store) = client(false).await;
    let mut ids = Vec::new();
    for (index, repository) in REPOSITORIES.into_iter().enumerate() {
        let target = json!({"repository":repository,"pr_number":25,"expected_head_sha":HEAD});
        let checked = call(&http, &url, "check_pr_review_target", &target).await;
        assert_eq!(checked["structuredContent"]["ready_for_review"], true);
        let previous_tokens = states[index].token_requests.lock().unwrap().len();
        let evidence = call(&http, &url, "read_pr_review_evidence", &target).await;
        assert_eq!(evidence["content"][0]["text"], "EVIDENCE_OBSERVED");
        assert_eq!(evidence["structuredContent"]["repository"], repository);
        assert_eq!(evidence["structuredContent"]["expected_head_sha"], HEAD);
        // The evidence fixture leaves unsupported mock endpoints as explicit gaps.
        let tokens = states[index].token_requests.lock().unwrap();
        assert_eq!(tokens.len(), previous_tokens + 1);
        assert_eq!(
            tokens.last().unwrap()["permissions"],
            json!({"metadata":"read","pull_requests":"read","checks":"read","actions":"read","issues":"read"})
        );
        drop(tokens);

        let mut approval = base_args("APPROVE");
        approval["repository"] = json!(repository);
        let mut stale = approval.clone();
        stale["expected_head_sha"] = json!("b".repeat(40));
        let rejected = call(&http, &url, "submit_pr_review", &stale).await;
        assert_eq!(rejected["content"][0]["text"], "STALE_HEAD");
        assert!(states[index].reviews.lock().unwrap().is_empty());

        let approved = call(&http, &url, "submit_pr_review", &approval).await;
        assert_eq!(approved["content"][0]["text"], "PUBLISHED");
        let plan = &approved["structuredContent"]["post_review_continuation"];
        assert_eq!(plan["repository"], repository, "{approved}");
        assert_eq!(plan["approved_head_sha"], HEAD);
        assert_eq!(plan["automatic_continuation_authorized"], true);
        assert_eq!(plan["execution_supported"], false);
        ids.push(operation_id(&[], &approval));

        let mut cr = cr_fixture();
        cr["repository"] = json!(repository);
        for expected in ["PUBLISHED", "DUPLICATE_SUPPRESSED"] {
            let result = call(&http, &url, "submit_pr_review", &cr).await;
            assert_eq!(
                result["content"][0]["text"], expected,
                "{repository}: {result}"
            );
            assert_eq!(result["structuredContent"]["review_id"], 2);
        }
        ids.push(operation_id(&[], &cr));
        assert_eq!(states[index].reviews.lock().unwrap().len(), 2);
        assert_eq!(
            states[index].issue.lock().unwrap().as_ref().unwrap()["labels"],
            json!([{"name":"step-2"}])
        );
        assert_eq!(
            states[index].pr.lock().unwrap().as_ref().unwrap()["title"],
            step_sync::projection_title(24, &cr).unwrap()
        );
        if index == 0 {
            assert_eq!(
                states[1].issue.lock().unwrap().as_ref().unwrap()["labels"],
                json!([{"name":"step-1"}])
            );
            assert!(states[1].reviews.lock().unwrap().is_empty());
            assert!(states[1].requests.lock().unwrap().is_empty());
        }
        let duplicate = call(&http, &url, "submit_pr_review", &approval).await;
        assert_eq!(duplicate["content"][0]["text"], "DUPLICATE_SUPPRESSED");
    }
    assert_eq!(ids.iter().collect::<BTreeSet<_>>().len(), 4);
    let store = store.lock().unwrap();
    for id in &ids {
        assert_eq!(store.known(id).unwrap().unwrap().status, "PUBLISHED");
    }
    for id in [&ids[1], &ids[3]] {
        assert!(store.step_binding(id).unwrap().is_some());
    }
    assert_targeted_requests(&states);
}

#[tokio::test]
async fn typed_authority_retains_repository_identity_in_the_shared_journal_and_native_readback() {
    let (http, url, states, store) = client(true).await;
    let mut ids = Vec::new();
    for (index, repository) in REPOSITORIES.into_iter().enumerate() {
        let record = request(repository);
        let arguments = json!({"repository":repository,"record":record});
        for expected in ["AUTHORITY_PUBLISHED", "DUPLICATE_SUPPRESSED"] {
            let result = call(&http, &url, "publish_task_authority", &arguments).await;
            assert_eq!(
                result["content"][0]["text"], expected,
                "{repository}: {result}"
            );
            assert_eq!(result["structuredContent"]["reference"]["id"], 1000);
            if expected == "AUTHORITY_PUBLISHED" {
                assert_eq!(
                    result["structuredContent"]["record"]["repository"],
                    repository
                );
            }
            assert!(result["structuredContent"]["native_url"]
                .as_str()
                .unwrap()
                .starts_with(&format!("https://github.com/{repository}/")));
        }
        ids.push(crate::task_authority::hash(&format!(
            "task-authority-v1\n{}",
            crate::task_authority::render(&record)
        )));
        assert_eq!(states[index].authority_comments.lock().unwrap().len(), 1);
        if index == 0 {
            assert!(states[1].authority_comments.lock().unwrap().is_empty());
        }
    }
    assert_ne!(ids[0], ids[1]);
    for id in ids {
        let operation = store.lock().unwrap().known(&id).unwrap().unwrap();
        assert_eq!(operation.status, "PUBLISHED");
        assert_eq!(operation.native_id, Some(1000));
    }
    assert_targeted_requests(&states);
}

fn assert_targeted_requests(states: &[MockState]) {
    for state in states {
        let requests = state.requests.lock().unwrap();
        assert!(requests
            .iter()
            .any(|request| request.starts_with("GET /repos/")));
        for request in requests.iter() {
            if let Some((_, path)) = request.split_once(" /repos/") {
                assert!(
                    path.starts_with(&format!("{}/", state.repository)),
                    "{request}"
                );
            }
        }
        let tokens = state.token_requests.lock().unwrap();
        assert!(!tokens.is_empty());
        for token in tokens.iter() {
            assert_eq!(
                token["repositories"],
                json!([state.repository.split('/').nth(1).unwrap()])
            );
        }
    }
}
