//! Fixed, bounded REST primitives for typed Task authority publication.
//! Native reference identifiers select only these source-controlled endpoints.
use super::*;
use std::time::Duration;

impl Github {
    async fn authority_request(
        &self,
        repository: &str,
        request: reqwest::RequestBuilder,
    ) -> Result<Value, &'static str> {
        let token = self.token(repository).await?;
        let mut response = request
            .timeout(Duration::from_secs(5))
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await
            .map_err(|_| "AUTHORITY_SOURCE_UNAVAILABLE")?;
        if !response.status().is_success() {
            return Err("AUTHORITY_SOURCE_UNAVAILABLE");
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| "AUTHORITY_SOURCE_UNAVAILABLE")?
        {
            if bytes.len() + chunk.len() > 262_144 {
                return Err("AUTHORITY_SOURCE_TOO_LARGE");
            }
            bytes.extend_from_slice(&chunk);
        }
        serde_json::from_slice::<crate::strict_json::StrictJson>(&bytes)
            .map(|value| value.0)
            .map_err(|_| "AUTHORITY_SOURCE_INVALID")
    }

    pub(crate) async fn authority_user(
        &self,
        repository: &str,
        login: &str,
    ) -> Result<Value, &'static str> {
        self.authority_request(
            repository,
            self.client.get(format!("{}/users/{login}", self.api)),
        )
        .await
    }

    pub(crate) async fn authority_source(
        &self,
        repository: &str,
        kind: &str,
        parent: u64,
        id: u64,
    ) -> Result<Value, &'static str> {
        let path = match kind {
            "issue-body" => format!("issues/{parent}"),
            "issue-comment" => format!("issues/comments/{id}"),
            "review" => format!("pulls/{parent}/reviews/{id}"),
            "review-comment" => format!("pulls/comments/{id}"),
            _ => return Err("AUTHORITY_REFERENCE_INVALID"),
        };
        self.authority_request(
            repository,
            self.client
                .get(format!("{}/repos/{repository}/{path}", self.api)),
        )
        .await
    }

    pub(crate) async fn authority_comments(
        &self,
        repository: &str,
        issue: u64,
    ) -> Result<Vec<Value>, &'static str> {
        let mut comments = Vec::new();
        for page in 1..=5 {
            let payload = self
                .authority_request(
                    repository,
                    self.client.get(format!(
                        "{}/repos/{repository}/issues/{issue}/comments?per_page=100&page={page}",
                        self.api
                    )),
                )
                .await?;
            let items = payload.as_array().ok_or("AUTHORITY_SOURCE_INVALID")?;
            comments.extend(items.iter().cloned());
            if items.len() < 100 {
                return Ok(comments);
            }
        }
        Err("AUTHORITY_SOURCE_TRUNCATED")
    }

    pub(crate) async fn authority_reviews(
        &self,
        repository: &str,
        pr: u64,
    ) -> Result<Vec<Value>, &'static str> {
        let mut reviews = Vec::new();
        for page in 1..=5 {
            let payload = self
                .authority_request(
                    repository,
                    self.client.get(format!(
                        "{}/repos/{repository}/pulls/{pr}/reviews?per_page=100&page={page}",
                        self.api
                    )),
                )
                .await?;
            let items = payload.as_array().ok_or("AUTHORITY_SOURCE_INVALID")?;
            reviews.extend(items.iter().cloned());
            if items.len() < 100 {
                return Ok(reviews);
            }
        }
        Err("AUTHORITY_SOURCE_TRUNCATED")
    }

    pub(crate) async fn authority_artifacts(
        &self,
        repository: &str,
        base: &str,
        branch: &str,
    ) -> Result<Vec<Value>, &'static str> {
        let owner = repository
            .split_once('/')
            .ok_or("AUTHORITY_PARENT_INVALID")?
            .0;
        let mut artifacts = Vec::new();
        for page in 1..=5 {
            let payload = self
                .authority_request(
                    repository,
                    self.client
                        .get(format!("{}/repos/{repository}/pulls", self.api))
                        .query(&[
                            ("state", "all".to_string()),
                            ("head", format!("{owner}:{branch}")),
                            ("base", base.to_string()),
                            ("per_page", "100".to_string()),
                            ("page", page.to_string()),
                        ]),
                )
                .await?;
            let items = payload.as_array().ok_or("AUTHORITY_SOURCE_INVALID")?;
            artifacts.extend(items.iter().cloned());
            if items.len() < 100 {
                return Ok(artifacts);
            }
        }
        Err("AUTHORITY_SOURCE_TRUNCATED")
    }

    pub(crate) async fn create_authority_comment(
        &self,
        repository: &str,
        issue: u64,
        body: &str,
    ) -> Result<Value, &'static str> {
        self.authority_request(
            repository,
            self.client
                .post(format!(
                    "{}/repos/{repository}/issues/{issue}/comments",
                    self.api
                ))
                .json(&json!({"body": body})),
        )
        .await
        .map_err(|_| "AUTHORITY_PUBLICATION_UNCERTAIN")
    }
}
