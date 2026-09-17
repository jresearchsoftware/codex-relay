use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use reqwest::Client;
use serde_json::{json, Value};
use std::{
    env, fs,
    time::{SystemTime, UNIX_EPOCH},
};

const API: &str = "https://api.github.com";
pub const USER_AGENT: &str = "codex-relay-reviewer/0.1.0";

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
        Self {
            client: Client::builder()
                .user_agent(USER_AGENT)
                .build()
                .expect("HTTP client"),
            api: API.into(),
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
            .map_err(|_| "GITHUB_AUTH_FAILED")?
            .as_secs();
        let key =
            fs::read(env::var("GITHUB_APP_PRIVATE_KEY_FILE").map_err(|_| "GITHUB_AUTH_FAILED")?)
                .map_err(|_| "GITHUB_AUTH_FAILED")?;
        let claims = json!({"iat":now.saturating_sub(30),"exp":now + 540,"iss":env::var("GITHUB_APP_ID").map_err(|_| "GITHUB_AUTH_FAILED")?});
        let jwt = encode(
            &Header::new(Algorithm::RS256),
            &claims,
            &EncodingKey::from_rsa_pem(&key).map_err(|_| "GITHUB_AUTH_FAILED")?,
        )
        .map_err(|_| "GITHUB_AUTH_FAILED")?;
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
                env::var("GITHUB_APP_INSTALLATION_ID").map_err(|_| "GITHUB_AUTH_FAILED")?
            }
            #[cfg(not(test))]
            {
                env::var("GITHUB_APP_INSTALLATION_ID").map_err(|_| "GITHUB_AUTH_FAILED")?
            }
        };
        let response = self
            .client
            .post(format!("{}/app/installations/{id}/access_tokens", self.api))
            .header("Authorization", format!("Bearer {jwt}"))
            .json(&json!({
                "repositories": [name],
                "permissions": {"metadata": "read", "pull_requests": "write", "checks": "write"}
            }))
            .send()
            .await
            .map_err(|_| "GITHUB_AUTH_FAILED")?;
        if !response.status().is_success() {
            return Err("GITHUB_AUTH_FAILED");
        }
        let payload = response
            .json::<Value>()
            .await
            .map_err(|_| "GITHUB_AUTH_FAILED")?;
        if payload
            .get("expires_at")
            .and_then(Value::as_str)
            .is_none_or(|value| value.is_empty())
        {
            return Err("GITHUB_TOKEN_LIFETIME_UNAVAILABLE");
        }
        payload
            .get("token")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned)
            .ok_or("GITHUB_AUTH_FAILED")
    }

    async fn request(
        &self,
        repository: &str,
        request: reqwest::RequestBuilder,
    ) -> Result<Value, &'static str> {
        let token = self.token(repository).await?;
        let response = request
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await
            .map_err(|_| "GITHUB_REQUEST_FAILED")?;
        if !response.status().is_success() {
            return Err(if response.status().as_u16() == 404 {
                "GITHUB_NOT_FOUND"
            } else {
                "GITHUB_REQUEST_FAILED"
            });
        }
        response.json().await.map_err(|_| "GITHUB_REQUEST_FAILED")
    }

    async fn app_request(&self, request: reqwest::RequestBuilder) -> Result<Value, &'static str> {
        let jwt = self.app_jwt().await?;
        let response = request
            .header("Authorization", format!("Bearer {jwt}"))
            .send()
            .await
            .map_err(|_| "GITHUB_REQUEST_FAILED")?;
        if !response.status().is_success() {
            return Err("GITHUB_REQUEST_FAILED");
        }
        response.json().await.map_err(|_| "GITHUB_REQUEST_FAILED")
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
    pub async fn find_review(
        &self,
        repository: &str,
        number: i64,
        marker: &str,
    ) -> Result<Option<Value>, &'static str> {
        let mut reviews = Vec::new();
        for page in 1..=20 {
            let current = self
                .request(
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
            reviews.extend(items.iter().cloned());
            if count < 100 {
                break;
            }
            if page == 20 {
                return Err("GITHUB_PAGINATION_LIMIT");
            }
        }
        Ok(reviews
            .iter()
            .find(|r| {
                r.get("body")
                    .and_then(Value::as_str)
                    .is_some_and(|b| b.contains(marker))
            })
            .cloned())
    }
    pub async fn find_check(
        &self,
        repository: &str,
        sha: &str,
        operation: &str,
    ) -> Result<Option<Value>, &'static str> {
        let mut checks = Vec::new();
        for page in 1..=20 {
            let mut request = self.client.get(format!(
                "{}/repos/{repository}/commits/{sha}/check-runs?per_page=100&page={page}",
                self.api
            ));
            #[cfg(test)]
            if let Some(mode) = &self.test_check_mode {
                request = request.header("x-test-check-mode", mode);
            }
            let payload = self.request(repository, request).await?;
            let Some(items) = payload.get("check_runs").and_then(Value::as_array) else {
                return Err("GITHUB_RESPONSE_INVALID");
            };
            let count = items.len();
            checks.extend(items.iter().cloned());
            if count < 100 {
                break;
            }
            if page == 20 {
                return Err("GITHUB_PAGINATION_LIMIT");
            }
        }
        Ok(checks
            .iter()
            .find(|check| check.get("external_id").and_then(Value::as_str) == Some(operation))
            .cloned())
    }
    pub async fn create_review(
        &self,
        repository: &str,
        number: i64,
        payload: &Value,
    ) -> Result<Value, &'static str> {
        self.request(
            repository,
            self.client
                .post(format!(
                    "{}/repos/{repository}/pulls/{number}/reviews",
                    self.api
                ))
                .json(payload),
        )
        .await
        .map_err(|_| "GITHUB_PUBLICATION_FAILED")
    }
    pub async fn create_check(
        &self,
        repository: &str,
        payload: &Value,
    ) -> Result<Value, &'static str> {
        let mut request = self
            .client
            .post(format!("{}/repos/{repository}/check-runs", self.api))
            .json(payload);
        #[cfg(test)]
        if let Some(mode) = &self.test_check_mode {
            let attempt = self
                .test_check_attempt
                .fetch_add(1, std::sync::atomic::Ordering::SeqCst)
                + 1;
            request = request
                .header("x-test-check-mode", mode)
                .header("x-test-check-attempt", attempt.to_string());
        }
        self.request(repository, request)
            .await
            .map_err(|_| "GITHUB_CHECK_PUBLICATION_FAILED")
    }
}
