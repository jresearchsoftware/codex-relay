use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
pub mod authority;
pub mod evidence;
use reqwest::{Client, Request, RequestBuilder};
use serde_json::{json, Value};
use std::{
    env, fs,
    time::{SystemTime, UNIX_EPOCH},
};

#[cfg(any(not(feature = "synthetic-github"), test))]
const API: &str = "https://api.github.com";
pub const USER_AGENT: &str = "codex-relay-reviewer/0.1.0";

// Native rejected responses belong only in the existing protected host journal.
// Bound the read, redact actual request credentials before generic redaction,
// and retain read gaps explicitly. Never call this for token success payloads.
async fn rejected_response(
    mut response: reqwest::Response,
    code: &'static str,
    secrets: &[&str],
) -> &'static str {
    let status = response.status().as_u16();
    let url = response.url().to_string();
    let request_id = response
        .headers()
        .get("x-github-request-id")
        .map(|value| format!("{value:?}"));
    let mut bytes = Vec::new();
    let mut truncated = false;
    let mut read_error = None;
    loop {
        match response.chunk().await {
            Ok(Some(chunk)) => {
                let remaining = 4096 - bytes.len();
                bytes.extend_from_slice(&chunk[..remaining.min(chunk.len())]);
                if chunk.len() >= remaining {
                    truncated = true;
                    break;
                }
            }
            Ok(None) => break,
            Err(error) => {
                read_error = Some(format!("{error:?}"));
                break;
            }
        }
    }
    let mut cause = format!("status={status} url={url} request_id={request_id:?} native_response_truncated={truncated} native_response_read_error={read_error:?} native_response={}", String::from_utf8_lossy(&bytes));
    for secret in secrets.iter().filter(|secret| !secret.is_empty()) {
        cause = cause.replace(secret, "[REDACTED]");
        if let Some(token) = secret.strip_prefix("Bearer ") {
            cause = cause.replace(token, "[REDACTED]");
        }
    }
    crate::diagnostics::record(code, "http-response", &cause);
    code
}

fn rejected_mutation_response(
    response: reqwest::Response,
    code: &'static str,
    credential: Option<String>,
) {
    use tracing::instrument::WithSubscriber;
    // Preserve the known rejection and return its retry classification before
    // awaiting diagnostic I/O. Cancellation must not turn a definite 4xx into
    // an uncertain send. A process exit can leave only this explicit body gap.
    crate::diagnostics::record(code, "http-response", &format!(
        "status={} url={} request_id={:?} native_response_capture=pending; body unavailable unless a subsequent bounded response record is present",
        response.status().as_u16(), response.url(), response.headers().get("x-github-request-id")));
    tokio::spawn(
        async move {
            rejected_response(response, code, &[credential.as_deref().unwrap_or("")]).await;
        }
        .with_current_subscriber(),
    );
}

/// Authentication and request construction have completed, but no mutation has
/// been sent. Callers reserve the possible external effect after this boundary.
pub(crate) struct PreparedMutation {
    request: Request,
    failure_code: &'static str,
}

#[derive(Debug)]
pub(crate) struct MutationFailure {
    pub code: &'static str,
    pub safe_to_retry: bool,
    pub phase: &'static str,
    pub http_status: Option<u16>,
    pub request_id: Option<String>,
}

impl MutationFailure {
    fn new(code: &'static str, safe_to_retry: bool, phase: &'static str) -> Self {
        Self {
            code,
            safe_to_retry,
            phase,
            http_status: None,
            request_id: None,
        }
    }

    pub(crate) fn diagnostics(&self) -> Value {
        json!({"code":self.code,"safe_to_retry":self.safe_to_retry,"phase":self.phase,
            "http_status":self.http_status,"request_id":self.request_id})
    }
}

#[derive(Clone)]
pub struct Github {
    client: Client,
    api: String,
    #[cfg(test)]
    test_installation_id: Option<String>,
    #[cfg(test)]
    test_check_mode: Option<String>,
    #[cfg(test)]
    test_check_attempt: std::sync::Arc<std::sync::atomic::AtomicUsize>,
}
impl Github {
    pub fn new() -> Self {
        #[cfg(all(feature = "synthetic-github", not(test)))]
        let api = {
            let supplied = env::var("REVIEWER_SYNTHETIC_GITHUB_API")
                .expect("synthetic-github requires its loopback fixture endpoint");
            let api = synthetic_endpoint(&supplied)
                .expect("synthetic-github endpoint must be http://127.0.0.1:<port>");
            eprintln!(
                "SYNTHETIC_GITHUB_ONLY: loopback fixture transport; not a deployment artifact"
            );
            api
        };
        #[cfg(any(not(feature = "synthetic-github"), test))]
        let api = API.into();
        Self {
            client: Client::builder()
                .user_agent(USER_AGENT)
                .redirect(reqwest::redirect::Policy::none())
                .build()
                .expect("HTTP client"),
            api,
            #[cfg(test)]
            test_installation_id: None,
            #[cfg(test)]
            test_check_mode: None,
            #[cfg(test)]
            test_check_attempt: std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0)),
        }
    }
    #[cfg(test)]
    pub fn mock_api(base: String) -> Self {
        Self::mock_api_with_check_mode(base, None)
    }
    #[cfg(test)]
    pub fn mock_api_with_check_mode(base: String, mode: Option<&str>) -> Self {
        Self {
            client: Client::builder()
                .user_agent(USER_AGENT)
                .redirect(reqwest::redirect::Policy::none())
                .build()
                .expect("HTTP client"),
            api: base,
            test_installation_id: Some("1".into()),
            test_check_mode: mode.map(ToOwned::to_owned),
            test_check_attempt: std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0)),
        }
    }

    #[cfg(test)]
    pub fn with_test_installation(mut self, installation_id: String) -> Self {
        self.test_installation_id = Some(installation_id);
        self
    }

    async fn app_jwt(&self) -> Result<String, &'static str> {
        #[cfg(test)]
        if self.test_installation_id.is_some() {
            return Ok("test-jwt".into());
        }
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?
            .as_secs();
        let key = fs::read(
            env::var("GITHUB_APP_PRIVATE_KEY_FILE")
                .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?,
        )
        .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?;
        let claims = json!({"iat":now.saturating_sub(30),"exp":now + 540,"iss":env::var("GITHUB_APP_ID").map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?});
        let jwt = encode(
            &Header::new(Algorithm::RS256),
            &claims,
            &EncodingKey::from_rsa_pem(&key)
                .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?,
        )
        .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?;
        Ok(jwt)
    }

    async fn token(&self, repository: &str) -> Result<String, &'static str> {
        // Config admission and caller validation supply owner/name. GitHub's
        // installation-token restriction takes the name within that installation.
        let (_, name) = repository.split_once('/').ok_or("GITHUB_AUTH_FAILED")?;
        let jwt = self.app_jwt().await?;
        let id = {
            #[cfg(test)]
            if let Some(id) = &self.test_installation_id {
                id.clone()
            } else {
                env::var("GITHUB_APP_INSTALLATION_ID")
                    .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?
            }
            #[cfg(not(test))]
            {
                env::var("GITHUB_APP_INSTALLATION_ID")
                    .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?
            }
        };
        let response = self
            .client
            .post(format!("{}/app/installations/{id}/access_tokens", self.api))
            .timeout(std::time::Duration::from_secs(5))
            .header("Authorization", format!("Bearer {jwt}"))
            .json(&json!({
                "repositories": [name],
                "permissions": {"metadata": "read", "pull_requests": "write", "checks": "write", "issues": "write", "actions": "read"}
            }))
            .send()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?;
        if !response.status().is_success() {
            return Err(rejected_response(response, "GITHUB_AUTH_FAILED", &[&jwt]).await);
        }
        let payload = response
            .json::<Value>()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_AUTH_FAILED", error))?;
        payload
            .get("token")
            .and_then(Value::as_str)
            .filter(|token| !token.is_empty())
            .map(ToOwned::to_owned)
            .ok_or_else(|| {
                crate::diagnostics::failure(
                    "GITHUB_AUTH_FAILED",
                    "Successful installation token response lacks a nonempty token",
                )
            })
    }

    async fn request(
        &self,
        repository: &str,
        request: reqwest::RequestBuilder,
    ) -> Result<Value, &'static str> {
        let token = self.token(repository).await?;
        let response = request
            .timeout(std::time::Duration::from_secs(5))
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_REQUEST_FAILED", error))?;
        if !response.status().is_success() {
            let code = if response.status().as_u16() == 404 {
                "GITHUB_NOT_FOUND"
            } else {
                "GITHUB_REQUEST_FAILED"
            };
            return Err(rejected_response(response, code, &[&token]).await);
        }
        response
            .json()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_REQUEST_FAILED", error))
    }

    async fn prepare_mutation(
        &self,
        repository: &str,
        request: RequestBuilder,
        failure_code: &'static str,
    ) -> Result<PreparedMutation, MutationFailure> {
        let token = self
            .token(repository)
            .await
            .map_err(|code| MutationFailure::new(code, true, "authorization"))?;
        let request = request
            .timeout(std::time::Duration::from_secs(5))
            .header("Authorization", format!("Bearer {token}"))
            .build()
            .map_err(|error| {
                MutationFailure::new(
                    crate::diagnostics::failure(failure_code, error),
                    true,
                    "request-build",
                )
            })?;
        Ok(PreparedMutation {
            request,
            failure_code,
        })
    }

    pub(crate) async fn send_mutation(
        &self,
        prepared: PreparedMutation,
    ) -> Result<Value, MutationFailure> {
        let credential = prepared
            .request
            .headers()
            .get("authorization")
            .and_then(|value| value.to_str().ok())
            .map(ToOwned::to_owned);
        let mut response = self
            .client
            .execute(prepared.request)
            .await
            .map_err(|error| {
                // A transport failure does not prove that GitHub rejected the POST.
                MutationFailure::new(
                    crate::diagnostics::failure(prepared.failure_code, error),
                    false,
                    "request-send",
                )
            })?;
        let status = response.status().as_u16();
        let request_id = response
            .headers()
            .get("x-github-request-id")
            .and_then(|value| value.to_str().ok())
            .filter(|value| {
                !value.is_empty()
                    && value.len() <= 128
                    && value
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b":._-".contains(&byte))
            })
            .map(ToOwned::to_owned);
        let failure = |phase, safe_to_retry| MutationFailure {
            code: prepared.failure_code,
            safe_to_retry,
            phase,
            http_status: Some(status),
            request_id: request_id.clone(),
        };
        if !response.status().is_success() {
            // Explicit rejection is different from a timeout or a server error
            // after a possibly accepted mutation. The bounded native response
            // remains in the host journal, never in public diagnostics.
            let rejected = failure(
                "http-response",
                (400..500).contains(&status) && status != 408,
            );
            rejected_mutation_response(response, prepared.failure_code, credential);
            return Err(rejected);
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|error| {
            crate::diagnostics::failure(prepared.failure_code, error);
            failure("response-body", false)
        })? {
            if bytes.len() + chunk.len() > 256 * 1024 {
                crate::diagnostics::record(
                    prepared.failure_code,
                    "response-body",
                    "Native mutation response exceeded 262144 bytes; publication remains uncertain",
                );
                return Err(failure("response-body", false));
            }
            bytes.extend_from_slice(&chunk);
        }
        serde_json::from_slice::<crate::strict_json::StrictJson>(&bytes)
            .map(|value| value.0)
            .map_err(|error| {
                crate::diagnostics::failure(prepared.failure_code, error);
                failure("response-body", false)
            })
    }

    // Preserve pagination completion metadata without following GitHub URLs.
    async fn collection_page(
        &self,
        repository: &str,
        request: RequestBuilder,
    ) -> Result<(Value, bool), &'static str> {
        let token = self.token(repository).await?;
        let mut response = request
            .timeout(std::time::Duration::from_secs(5))
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_REQUEST_FAILED", error))?;
        if !response.status().is_success() {
            return Err(rejected_response(response, "GITHUB_REQUEST_FAILED", &[&token]).await);
        }
        let has_next = response
            .headers()
            .get(reqwest::header::LINK)
            .map(|value| {
                value
                    .to_str()
                    .map_err(|error| crate::diagnostics::failure("GITHUB_RESPONSE_INVALID", error))
            })
            .transpose()?
            .is_some_and(|links| {
                links.split(',').any(|link| {
                    link.split(';')
                        .skip(1)
                        .any(|part| part.trim() == "rel=\"next\"")
                })
            });
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_REQUEST_FAILED", error))?
        {
            if bytes.len() + chunk.len() > 256 * 1024 {
                return Err("GITHUB_RESPONSE_TOO_LARGE");
            }
            bytes.extend_from_slice(&chunk);
        }
        let payload = serde_json::from_slice::<crate::strict_json::StrictJson>(&bytes)
            .map(|value| value.0)
            .map_err(|error| crate::diagnostics::failure("GITHUB_RESPONSE_INVALID", error))?;
        Ok((payload, has_next))
    }

    async fn app_request(&self, request: reqwest::RequestBuilder) -> Result<Value, &'static str> {
        let jwt = self.app_jwt().await?;
        let response = request
            .timeout(std::time::Duration::from_secs(5))
            .header("Authorization", format!("Bearer {jwt}"))
            .send()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_REQUEST_FAILED", error))?;
        if !response.status().is_success() {
            return Err(rejected_response(response, "GITHUB_REQUEST_FAILED", &[&jwt]).await);
        }
        response
            .json()
            .await
            .map_err(|error| crate::diagnostics::failure("GITHUB_REQUEST_FAILED", error))
    }

    pub async fn get_pr(&self, repository: &str, number: i64) -> Result<Value, &'static str> {
        self.request(
            repository,
            self.client
                .get(format!("{}/repos/{repository}/pulls/{number}", self.api)),
        )
        .await
    }
    pub async fn app_identity(&self) -> Result<Value, &'static str> {
        self.app_request(self.client.get(format!("{}/app", self.api)))
            .await
    }
    pub(crate) async fn get_issue(
        &self,
        repository: &str,
        number: u64,
    ) -> Result<Value, &'static str> {
        self.request(
            repository,
            self.client
                .get(format!("{}/repos/{repository}/issues/{number}", self.api)),
        )
        .await
    }

    pub(crate) async fn decisive_review(
        &self,
        repository: &str,
        number: i64,
        actor: &str,
    ) -> Result<Option<Value>, &'static str> {
        let mut decisive: Option<Value> = None;
        for page in 1..=20 {
            let payload = self
                .request(
                    repository,
                    self.client.get(format!(
                        "{}/repos/{repository}/pulls/{number}/reviews?per_page=100&page={page}",
                        self.api
                    )),
                )
                .await?;
            let items = payload.as_array().ok_or("GITHUB_RESPONSE_INVALID")?;
            for review in items {
                if review.pointer("/user/login").and_then(Value::as_str) == Some(actor)
                    && matches!(
                        review["state"].as_str(),
                        Some("CHANGES_REQUESTED" | "APPROVED" | "DISMISSED")
                    )
                {
                    let id = review["id"]
                        .as_i64()
                        .filter(|id| *id > 0)
                        .ok_or("GITHUB_RESPONSE_INVALID")?;
                    if decisive
                        .as_ref()
                        .is_none_or(|previous| previous["id"].as_i64().unwrap_or(0) < id)
                    {
                        decisive = Some(review.clone());
                    }
                }
            }
            if items.len() < 100 {
                return Ok(decisive);
            }
        }
        Err("GITHUB_PAGINATION_LIMIT")
    }

    // Internal projection primitives. No MCP caller can supply these paths or payloads.
    pub(crate) async fn ensure_step_label(
        &self,
        repository: &str,
        step: u64,
    ) -> Result<(), &'static str> {
        let label = format!("step-{step}");
        match self
            .request(
                repository,
                self.client
                    .get(format!("{}/repos/{repository}/labels/{label}", self.api)),
            )
            .await
        {
            Ok(value) if value["name"] == label => Ok(()),
            Ok(_) => Err("STEP_LABEL_INVALID"),
            Err("GITHUB_NOT_FOUND") => {
                self.request(
                    repository,
                    self.client
                        .post(format!("{}/repos/{repository}/labels", self.api))
                        .json(&json!({"name": label, "color": "ededed"})),
                )
                .await?;
                Ok(())
            }
            Err(code) => Err(code),
        }
    }
    pub(crate) async fn project_step_labels(
        &self,
        repository: &str,
        number: u64,
        labels: &[String],
    ) -> Result<(), &'static str> {
        self.request(
            repository,
            self.client
                .put(format!(
                    "{}/repos/{repository}/issues/{number}/labels",
                    self.api
                ))
                .json(&json!({"labels":labels})),
        )
        .await?;
        Ok(())
    }
    pub(crate) async fn project_step_title(
        &self,
        repository: &str,
        number: i64,
        title: &str,
    ) -> Result<(), &'static str> {
        self.request(
            repository,
            self.client
                .patch(format!("{}/repos/{repository}/pulls/{number}", self.api))
                .json(&json!({"title":title})),
        )
        .await?;
        Ok(())
    }
    pub async fn find_review(
        &self,
        repository: &str,
        number: i64,
        marker: &str,
    ) -> Result<Option<Value>, &'static str> {
        let mut reviews = Vec::new();
        for page in 1..=20 {
            let (current, has_next) = self
                .collection_page(
                    repository,
                    self.client.get(format!(
                        "{}/repos/{repository}/pulls/{number}/reviews?per_page=100&page={page}",
                        self.api
                    )),
                )
                .await?;
            let Some(items) = current.as_array() else {
                return Err("GITHUB_RESPONSE_INVALID");
            };
            let count = items.len();
            if count > 100 || (count < 100 && has_next) {
                return Err("GITHUB_RESPONSE_INVALID");
            }
            reviews.extend(items.iter().cloned());
            if count < 100 {
                break;
            }
            if page == 20 {
                return Err("GITHUB_PAGINATION_LIMIT");
            }
        }
        let matches: Vec<_> = reviews
            .into_iter()
            .filter(|r| {
                r.get("body")
                    .and_then(Value::as_str)
                    .is_some_and(|b| b.contains(marker))
            })
            .collect();
        if matches.len() > 1 {
            return Err("REVIEW_PUBLICATION_AMBIGUOUS");
        }
        Ok(matches.into_iter().next())
    }
    pub(crate) async fn find_checks(
        &self,
        repository: &str,
        sha: &str,
        operation: &str,
    ) -> Result<Vec<Value>, &'static str> {
        let mut checks = Vec::new();
        for page in 1..=20 {
            let request = self.client.get(format!(
                "{}/repos/{repository}/commits/{sha}/check-runs?filter=all&per_page=100&page={page}",
                self.api
            ));
            #[cfg(test)]
            let request = if let Some(mode) = &self.test_check_mode {
                request.header("x-test-check-mode", mode)
            } else {
                request
            };
            let (payload, has_next) = self.collection_page(repository, request).await?;
            let Some(items) = payload.get("check_runs").and_then(Value::as_array) else {
                return Err("GITHUB_RESPONSE_INVALID");
            };
            let count = items.len();
            if count > 100 || (count < 100 && has_next) {
                return Err("GITHUB_RESPONSE_INVALID");
            }
            checks.extend(items.iter().cloned());
            if count < 100 {
                break;
            }
            if page == 20 {
                return Err("GITHUB_PAGINATION_LIMIT");
            }
        }
        let mut matches: Vec<_> = checks
            .into_iter()
            .filter(|check| check.get("external_id").and_then(Value::as_str) == Some(operation))
            .collect();
        if matches.len() > 2
            || matches
                .iter()
                .any(|check| check["id"].as_i64().is_none_or(|id| id <= 0))
        {
            return Err("CHECK_PUBLICATION_AMBIGUOUS");
        }
        if matches.len() == 2
            && (matches[0]["id"] == matches[1]["id"]
                || !same_check_effect(&matches[0], &matches[1]))
        {
            return Err("CHECK_PUBLICATION_AMBIGUOUS");
        }
        matches.sort_by_key(|check| check["id"].as_i64().unwrap());
        Ok(matches)
    }
    pub(crate) async fn prepare_review(
        &self,
        repository: &str,
        number: i64,
        payload: &Value,
    ) -> Result<PreparedMutation, MutationFailure> {
        self.prepare_mutation(
            repository,
            self.client
                .post(format!(
                    "{}/repos/{repository}/pulls/{number}/reviews",
                    self.api
                ))
                .json(payload),
            "GITHUB_PUBLICATION_FAILED",
        )
        .await
    }
    pub(crate) async fn prepare_check(
        &self,
        repository: &str,
        payload: &Value,
    ) -> Result<PreparedMutation, MutationFailure> {
        let request = self
            .client
            .post(format!("{}/repos/{repository}/check-runs", self.api))
            .json(payload);
        #[cfg(test)]
        let request = if let Some(mode) = &self.test_check_mode {
            let attempt = self
                .test_check_attempt
                .fetch_add(1, std::sync::atomic::Ordering::SeqCst)
                + 1;
            request
                .header("x-test-check-mode", mode)
                .header("x-test-check-attempt", attempt.to_string())
        } else {
            request
        };
        self.prepare_mutation(repository, request, "GITHUB_CHECK_PUBLICATION_FAILED")
            .await
    }
}

fn same_check_effect(left: &Value, right: &Value) -> bool {
    ["name", "head_sha", "external_id", "status", "conclusion"]
        .iter()
        .all(|key| left[*key] == right[*key])
        && [
            "title",
            "summary",
            "text",
            "annotations_count",
            "annotations",
        ]
        .iter()
        .all(|key| left["output"][*key] == right["output"][*key])
        && left["app"]["id"] == right["app"]["id"]
        && left["app"]["slug"] == right["app"]["slug"]
}

#[cfg(feature = "synthetic-github")]
fn synthetic_endpoint(value: &str) -> Option<String> {
    let url = reqwest::Url::parse(value).ok()?;
    (url.scheme() == "http"
        && url.host_str() == Some("127.0.0.1")
        && url.port().is_some()
        && url.username().is_empty()
        && url.password().is_none()
        && url.path() == "/"
        && url.query().is_none()
        && url.fragment().is_none())
    .then(|| url.as_str().trim_end_matches('/').to_string())
}

#[cfg(test)]
mod mutation_tests;
