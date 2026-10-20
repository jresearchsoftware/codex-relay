use super::*;
use axum::{
    body::{Body, Bytes},
    extract::State,
    http::{Method, StatusCode, Uri},
    response::{IntoResponse, Response},
    routing::any,
    Json, Router,
};
use std::sync::{Arc, Mutex};

#[cfg(feature = "synthetic-github")]
#[test]
fn synthetic_endpoint_has_no_external_or_credential_override() {
    assert_eq!(
        synthetic_endpoint("http://127.0.0.1:18787").as_deref(),
        Some("http://127.0.0.1:18787")
    );
    for value in [
        "https://api.github.com",
        "http://example.com:18787",
        "http://127.0.0.1:18787/path",
        "http://user@127.0.0.1:18787",
        "http://127.0.0.1:18787/?q=1",
        "http://127.0.0.1:18787/#fragment",
    ] {
        assert_eq!(synthetic_endpoint(value), None, "{value}");
    }
}

#[derive(Clone)]
struct Fixture {
    requests: Arc<Mutex<Vec<String>>>,
    token_status: u16,
    mutation_status: u16,
    malformed: bool,
    incomplete: bool,
    checks: Vec<Value>,
    reviews: Vec<Value>,
}

impl Default for Fixture {
    fn default() -> Self {
        Self {
            requests: Default::default(),
            token_status: 200,
            mutation_status: 201,
            malformed: false,
            incomplete: false,
            checks: vec![],
            reviews: vec![],
        }
    }
}

async fn handle(State(state): State<Fixture>, method: Method, uri: Uri, _body: Bytes) -> Response {
    state
        .requests
        .lock()
        .unwrap()
        .push(format!("{method} {}", uri.path()));
    if uri.path().ends_with("/access_tokens") {
        return (
            StatusCode::from_u16(state.token_status).unwrap(),
            Json(json!({"token":"fixture-token","expires_at":"2099-01-01T00:00:00Z"})),
        )
            .into_response();
    }
    if method == Method::GET {
        let page = uri
            .query()
            .unwrap()
            .split('&')
            .find_map(|part| part.strip_prefix("page="))
            .unwrap()
            .parse::<usize>()
            .unwrap();
        let checks = uri.path().ends_with("/check-runs");
        if checks {
            assert!(uri.query().unwrap().contains("filter=all"));
        }
        let records = if checks {
            &state.checks
        } else {
            &state.reviews
        };
        let items: Vec<_> = records
            .iter()
            .skip((page - 1) * 100)
            .take(100)
            .cloned()
            .collect();
        let payload = if checks {
            json!({"check_runs":items})
        } else {
            json!(items)
        };
        let mut response = Json(payload).into_response();
        if state.incomplete || records.len() > page * 100 {
            response.headers_mut().insert(
                "link",
                "<https://untrusted.invalid/next>; rel=\"next\""
                    .parse()
                    .unwrap(),
            );
        }
        return response;
    }
    let mut response = if state.malformed {
        Response::new(Body::from("accepted but incomplete JSON"))
    } else {
        Json(json!({"id":1})).into_response()
    };
    *response.status_mut() = StatusCode::from_u16(state.mutation_status).unwrap();
    response
        .headers_mut()
        .insert("x-github-request-id", "ABCD:1234:EF-56".parse().unwrap());
    response
}

async fn fixture(state: Fixture) -> (Github, tokio::task::JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let task = tokio::spawn(async move {
        axum::serve(
            listener,
            Router::new().fallback(any(handle)).with_state(state),
        )
        .await
        .unwrap();
    });
    (Github::mock_api(format!("http://{address}")), task)
}

#[tokio::test]
async fn prepared_mutation_authenticates_without_sending_an_external_effect() {
    let state = Fixture::default();
    let (github, server) = fixture(state.clone()).await;
    let prepared = github
        .prepare_check("owner/repo", &json!({"name":"review"}))
        .await
        .unwrap();
    assert_eq!(
        *state.requests.lock().unwrap(),
        ["POST /app/installations/1/access_tokens"]
    );
    assert_eq!(github.send_mutation(prepared).await.unwrap()["id"], 1);
    assert_eq!(
        state
            .requests
            .lock()
            .unwrap()
            .iter()
            .filter(|path| path.ends_with("/check-runs"))
            .count(),
        1
    );
    server.abort();
}

#[tokio::test]
async fn token_and_request_build_failures_are_safe_before_send() {
    let state = Fixture {
        token_status: 403,
        ..Default::default()
    };
    let (github, server) = fixture(state.clone()).await;
    let failure = github
        .prepare_check("owner/repo", &json!({}))
        .await
        .err()
        .unwrap();
    assert!(failure.safe_to_retry);
    assert_eq!(failure.phase, "authorization");
    assert!(state
        .requests
        .lock()
        .unwrap()
        .iter()
        .all(|path| path.ends_with("/access_tokens")));
    server.abort();
    let (github, server) = fixture(Fixture::default()).await;
    let failure = github
        .prepare_mutation("owner/repo", github.client.post("http://["), "BUILD_FAILED")
        .await
        .err()
        .unwrap();
    assert!(failure.safe_to_retry);
    assert_eq!(failure.phase, "request-build");
    server.abort();
}

#[tokio::test]
async fn mutation_rejections_and_ambiguous_responses_preserve_bounded_diagnostics() {
    for status in [400, 401, 403, 404, 408, 409, 422, 429, 500, 503] {
        let (github, server) = fixture(Fixture {
            mutation_status: status,
            ..Default::default()
        })
        .await;
        let prepared = github
            .prepare_review("owner/repo", 1, &json!({}))
            .await
            .unwrap();
        let failure = github.send_mutation(prepared).await.err().unwrap();
        assert_eq!(
            failure.safe_to_retry,
            status < 500 && status != 408,
            "{status}"
        );
        assert_eq!(failure.http_status, Some(status));
        assert_eq!(failure.request_id.as_deref(), Some("ABCD:1234:EF-56"));
        assert_eq!(failure.diagnostics().as_object().unwrap().len(), 5);
        assert!(!failure.diagnostics().to_string().contains("fixture-token"));
        server.abort();
    }
    let (github, server) = fixture(Fixture {
        malformed: true,
        ..Default::default()
    })
    .await;
    let prepared = github
        .prepare_authority_comment("owner/repo", 1, "body")
        .await
        .unwrap();
    let failure = github.send_mutation(prepared).await.err().unwrap();
    assert!(!failure.safe_to_retry);
    assert_eq!(failure.phase, "response-body");
    assert_eq!(failure.http_status, Some(201));
    server.abort();
}

#[tokio::test]
async fn a_lost_transport_response_cannot_release_the_send_reservation() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let close = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.unwrap();
        drop(stream);
    });
    let github = Github::new();
    let prepared = PreparedMutation {
        request: github
            .client
            .post(format!("http://{address}"))
            .body("fixture")
            .build()
            .unwrap(),
        failure_code: "LOST_RESPONSE",
    };
    let failure = github.send_mutation(prepared).await.err().unwrap();
    assert!(!failure.safe_to_retry);
    assert_eq!(failure.phase, "request-send");
    assert_eq!(failure.http_status, None);
    close.await.unwrap();
}

fn check(id: i64) -> Value {
    json!({"id":id,"html_url":format!("https://fixture/check/{id}"),"name":"review",
        "head_sha":"a".repeat(40),"external_id":"operation","status":"completed",
        "conclusion":"success","app":{"id":1,"slug":"reviewer"},
        "output":{"title":"Review approved","summary":"Exact head.","annotations_count":0,
            "annotations_url":format!("https://api.github.com/repos/owner/repo/check-runs/{id}/annotations")}})
}

#[tokio::test]
async fn complete_check_readback_accepts_only_one_bounded_identical_late_duplicate() {
    let mut checks: Vec<_> = (100..200)
        .map(|id| {
            let mut value = check(id);
            value["external_id"] = json!("other");
            value
        })
        .collect();
    checks.extend([check(9), check(5)]);
    let (github, server) = fixture(Fixture {
        checks,
        ..Default::default()
    })
    .await;
    let checks = github
        .find_checks("owner/repo", &"a".repeat(40), "operation")
        .await
        .unwrap();
    assert_eq!(
        checks
            .iter()
            .map(|value| value["id"].as_i64().unwrap())
            .collect::<Vec<_>>(),
        [5, 9]
    );
    server.abort();
    for defect in ["third", "same-id", "conclusion", "body", "app", "sha"] {
        let mut checks = vec![check(1), check(2)];
        match defect {
            "third" => checks.push(check(3)),
            "same-id" => checks[1]["id"] = json!(1),
            "conclusion" => checks[1]["conclusion"] = json!("failure"),
            "body" => checks[1]["output"]["summary"] = json!("Different effect"),
            "app" => checks[1]["app"]["id"] = json!(99),
            "sha" => checks[1]["head_sha"] = json!("b".repeat(40)),
            _ => unreachable!(),
        }
        let (github, server) = fixture(Fixture {
            checks,
            ..Default::default()
        })
        .await;
        assert_eq!(
            github
                .find_checks("owner/repo", &"a".repeat(40), "operation")
                .await
                .err(),
            Some("CHECK_PUBLICATION_AMBIGUOUS"),
            "{defect}"
        );
        server.abort();
    }
}

#[tokio::test]
async fn review_markers_require_exactly_one_result_and_collection_completion() {
    let review = json!({"id":1,"body":"operation-marker"});
    let (github, server) = fixture(Fixture {
        reviews: vec![review.clone(), review],
        ..Default::default()
    })
    .await;
    assert_eq!(
        github
            .find_review("owner/repo", 1, "operation-marker")
            .await
            .err(),
        Some("REVIEW_PUBLICATION_AMBIGUOUS")
    );
    server.abort();
    let (github, server) = fixture(Fixture {
        checks: vec![check(1)],
        incomplete: true,
        ..Default::default()
    })
    .await;
    assert_eq!(
        github
            .find_checks("owner/repo", &"a".repeat(40), "operation")
            .await
            .err(),
        Some("GITHUB_RESPONSE_INVALID")
    );
    server.abort();
    let (github, server) = fixture(Fixture {
        reviews: vec![json!({"id":1,"body":"x".repeat(256 * 1024)})],
        ..Default::default()
    })
    .await;
    assert_eq!(
        github
            .find_review("owner/repo", 1, "operation-marker")
            .await
            .err(),
        Some("GITHUB_RESPONSE_TOO_LARGE")
    );
    server.abort();
}
