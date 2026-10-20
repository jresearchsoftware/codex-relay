//! Fixed, bounded REST primitives for typed Task authority publication.
//! Native reference identifiers select only these source-controlled endpoints.
use super::*;
use std::{collections::HashSet, time::Duration};

const SOURCE_BYTES: usize = 256 * 1024;
const COLLECTION_BYTES: usize = 8 * 1024 * 1024;
const COLLECTION_RECORDS: usize = 500;

impl Github {
    async fn authority_request(
        &self,
        repository: &str,
        request: reqwest::RequestBuilder,
    ) -> Result<Value, &'static str> {
        self.authority_response(repository, request, None)
            .await
            .map(|(payload, _)| payload)
    }

    async fn authority_response(
        &self,
        repository: &str,
        request: reqwest::RequestBuilder,
        mut transferred: Option<&mut usize>,
    ) -> Result<(Value, bool), &'static str> {
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
        // Observe completion metadata, but never follow a server-supplied URL.
        let has_next = response
            .headers()
            .get(reqwest::header::LINK)
            .map(|value| value.to_str().map_err(|_| "AUTHORITY_SOURCE_INVALID"))
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
            .map_err(|_| "AUTHORITY_SOURCE_UNAVAILABLE")?
        {
            if let Some(total) = transferred.as_deref_mut() {
                *total = total.saturating_add(chunk.len());
                if *total > COLLECTION_BYTES {
                    return Err("AUTHORITY_COLLECTION_BUDGET_EXCEEDED");
                }
            }
            if bytes.len() + chunk.len() > SOURCE_BYTES {
                return Err("AUTHORITY_SOURCE_TOO_LARGE");
            }
            bytes.extend_from_slice(&chunk);
        }
        serde_json::from_slice::<crate::strict_json::StrictJson>(&bytes)
            .map(|value| (value.0, has_next))
            .map_err(|_| "AUTHORITY_SOURCE_INVALID")
    }

    async fn authority_collection(
        &self,
        repository: &str,
        path: &str,
        query: &[(&str, String)],
    ) -> Result<Vec<Value>, &'static str> {
        tokio::time::timeout(
            Duration::from_secs(60),
            self.authority_collection_pages(repository, path, query),
        )
        .await
        .unwrap_or(Err("AUTHORITY_COLLECTION_TIMEOUT"))
    }

    async fn authority_collection_pages(
        &self,
        repository: &str,
        path: &str,
        query: &[(&str, String)],
    ) -> Result<Vec<Value>, &'static str> {
        let mut records = Vec::new();
        let mut ids = HashSet::new();
        let mut transferred = 0;
        let mut page_size = 100;
        loop {
            // Every smaller size divides its predecessor. Previously acquired
            // records keep their offsets; an oversized page retries only the
            // unread range, without restarting, sorting or deduplicating it.
            let page = records.len() / page_size + 1;
            let response = self
                .authority_response(
                    repository,
                    self.client
                        .get(format!("{}/repos/{repository}/{path}", self.api))
                        .query(query)
                        .query(&[("per_page", page_size), ("page", page)]),
                    Some(&mut transferred),
                )
                .await;
            let (payload, has_next) = match response {
                Err("AUTHORITY_SOURCE_TOO_LARGE") if page_size > 1 => {
                    page_size = match page_size {
                        100 => 50,
                        50 => 25,
                        25 => 5,
                        _ => 1,
                    };
                    continue;
                }
                other => other?,
            };
            let items = payload.as_array().ok_or("AUTHORITY_SOURCE_INVALID")?;
            if items.len() > page_size {
                return Err("AUTHORITY_SOURCE_INVALID");
            }
            if records.len() + items.len() > COLLECTION_RECORDS {
                return Err("AUTHORITY_SOURCE_TRUNCATED");
            }
            for item in items {
                let id = item["id"]
                    .as_u64()
                    .filter(|id| *id > 0)
                    .ok_or("AUTHORITY_SOURCE_INVALID")?;
                if !ids.insert(id) {
                    return Err("AUTHORITY_SOURCE_INVALID");
                }
                records.push(item.clone());
            }
            if items.len() < page_size {
                return if has_next {
                    Err("AUTHORITY_SOURCE_TRUNCATED")
                } else {
                    Ok(records)
                };
            }
            // A full page at exactly 500 still needs an empty completion page.
            // At most 501 successful responses plus four size reductions fit
            // this reader; transfer and the enclosing 60s operation stay bounded.
        }
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
        self.authority_collection(repository, &format!("issues/{issue}/comments"), &[])
            .await
    }

    pub(crate) async fn authority_reviews(
        &self,
        repository: &str,
        pr: u64,
    ) -> Result<Vec<Value>, &'static str> {
        self.authority_collection(repository, &format!("pulls/{pr}/reviews"), &[])
            .await
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
        self.authority_collection(
            repository,
            "pulls",
            &[
                ("state", "all".to_string()),
                ("head", format!("{owner}:{branch}")),
                ("base", base.to_string()),
            ],
        )
        .await
    }

    pub(crate) async fn prepare_authority_comment(
        &self,
        repository: &str,
        issue: u64,
        body: &str,
    ) -> Result<PreparedMutation, MutationFailure> {
        self.prepare_mutation(
            repository,
            self.client
                .post(format!(
                    "{}/repos/{repository}/issues/{issue}/comments",
                    self.api
                ))
                .json(&json!({"body": body})),
            "AUTHORITY_PUBLICATION_UNCERTAIN",
        )
        .await
    }
}
