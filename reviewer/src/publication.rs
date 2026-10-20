//! GitHub owns publication receipts. SQLite protects only unresolved effects,
//! immutable meaning and the single permitted auxiliary-check recovery send.
use crate::*;

pub(crate) struct CheckEvidence {
    pub check: Value,
    pub warnings: Vec<&'static str>,
}

pub(crate) struct CheckFailure {
    pub code: &'static str,
    pub diagnostics: Value,
}

impl CheckFailure {
    fn observed(code: &'static str) -> Self {
        Self {
            code,
            diagnostics: json!({"phase":"readback"}),
        }
    }

    pub fn result(&self, operation: &str) -> Value {
        let mut result = task_authority::error(self.code);
        result["structuredContent"] = json!({"operation":operation,"diagnostics":self.diagnostics,
        "operator_action":if self.code == "AUTHORITY_ORIGINAL_BINDING_REQUIRED" {
            "Recover the original protected authority binding for this historical operation. Do not attach its Review to current Task Decisions, reset its state or repeat the Review."
        } else if self.code == "CHECK_RETRY_EXHAUSTED" {
            "Inspect the original operation's native Review and filter=all Check Runs. Restore missing GitHub visibility or resolve conflicting evidence; do not repeat the Review or reset publication state."
        } else {
            "Repeat the identical tool input to reconcile the original native publication. At most one recovery Check Run POST is allowed; the decisive publication is never repeated."
        }});
        result
    }
}

fn verify_check(
    app: &RepositoryTarget<'_>,
    check: &Value,
    payload: &Value,
) -> Result<(), &'static str> {
    if ["name", "head_sha", "external_id", "status", "conclusion"]
        .iter()
        .any(|key| check[*key] != payload[*key])
        || check["app"]["slug"] != app.policy.slug
        || check["app"]["id"]
            .as_u64()
            .map(|id| id.to_string())
            .as_deref()
            != Some(app.policy.app_id.as_str())
        || check["id"].as_i64().is_none_or(|id| id <= 0)
        || check["html_url"].as_str().is_none_or(str::is_empty)
    {
        return Err("CHECK_VERIFICATION_FAILED");
    }
    Ok(())
}

async fn observed_check(
    app: &RepositoryTarget<'_>,
    operation: &str,
    payload: &Value,
) -> Result<Option<CheckEvidence>, &'static str> {
    let checks = app
        .github
        .find_checks(
            &app.repository,
            payload["head_sha"].as_str().unwrap(),
            operation,
        )
        .await?;
    for check in &checks {
        verify_check(app, check, payload)?;
    }
    // find_checks rejects conflicting or excessive duplicates, and sorts by ID.
    Ok(checks.first().cloned().map(|check| CheckEvidence {
        check,
        warnings: if checks.len() == 2 {
            vec!["IDENTICAL_CHECK_DUPLICATE_OBSERVED"]
        } else {
            vec![]
        },
    }))
}

pub(crate) async fn ensure_check(
    app: &RepositoryTarget<'_>,
    operation: &str,
    payload: &Value,
    allow_send: bool,
) -> Result<CheckEvidence, CheckFailure> {
    if let Some(check) = observed_check(app, operation, payload)
        .await
        .map_err(CheckFailure::observed)?
    {
        return Ok(check);
    }
    if !allow_send {
        return Err(CheckFailure::observed(
            "AUTHORITY_ORIGINAL_BINDING_REQUIRED",
        ));
    }
    // Authentication and request construction cannot spend a possible-send grant.
    let prepared = app
        .github
        .prepare_check(&app.repository, payload)
        .await
        .map_err(|failure| CheckFailure {
            code: failure.code,
            diagnostics: failure.diagnostics(),
        })?;
    let reservation = app
        .store
        .lock()
        .map_err(|_| CheckFailure::observed("INTERNAL_RELAY_ERROR"))?
        .reserve_check_send(operation)
        .map_err(|_| CheckFailure::observed("INTERNAL_RELAY_ERROR"))?
        .ok_or_else(|| CheckFailure::observed("CHECK_RETRY_EXHAUSTED"))?;
    let sent = app.github.send_mutation(prepared).await;
    if let Err(failure) = &sent {
        if failure.safe_to_retry {
            app.store
                .lock()
                .map_err(|_| CheckFailure::observed("INTERNAL_RELAY_ERROR"))?
                .restore_check_send(operation, reservation)
                .map_err(|_| CheckFailure::observed("INTERNAL_RELAY_ERROR"))?;
            return Err(CheckFailure {
                code: failure.code,
                diagnostics: failure.diagnostics(),
            });
        }
    }
    // Even a successful POST response needs complete native readback. A lost
    // response can already be a completed effect; never trust a local receipt.
    match observed_check(app, operation, payload)
        .await
        .map_err(CheckFailure::observed)?
    {
        Some(check) => Ok(check),
        None => Err(CheckFailure {
            code: if reservation.next == 2 {
                "CHECK_RETRY_EXHAUSTED"
            } else {
                "CHECK_PUBLICATION_UNCERTAIN"
            },
            diagnostics: sent
                .err()
                .map(|failure| failure.diagnostics())
                .unwrap_or_else(|| json!({"phase":"post_readback"})),
        }),
    }
}

pub(crate) async fn publish_review(app: &RepositoryTarget<'_>, arguments: &Value) -> Value {
    let future = async {
        let operation = operation_id(&app.policy.validation_names, arguments);
        let marker = format!("jresearchsoftware-reviewer-relay:v1 operation={operation}");
        let known = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .known(&operation)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        let identity = app.github.app_identity().await?;
        if !identity_matches(&app.policy, &identity) {
            return Err("ACTOR_VERIFICATION_FAILED");
        }
        let native = app
            .github
            .find_review(
                &app.repository,
                arguments["pr_number"].as_i64().unwrap(),
                &marker,
            )
            .await?;
        let pr = app
            .github
            .get_pr(&app.repository, arguments["pr_number"].as_i64().unwrap())
            .await?;
        let mut publication_pr = pr.clone();
        if native.is_some() && arguments["action"] == "REQUEST_CHANGES" {
            publication_pr["draft"] = json!(false);
        }
        if let Some(code) = target_binding_rejection(&app.policy, &pr, arguments)
            .or_else(|| publication_rejection(&publication_pr, &arguments["expected_head_sha"]))
        {
            return Err(code);
        }
        let binding = current_approval_authority(app, arguments).await?;
        verify_approval_authority(app, &operation, binding.as_ref(), false)?;
        let mut current_body =
            native_review_body(&app.policy.validation_names, arguments, &operation);
        if let Some(binding) = &binding {
            current_body.push_str(&format!(
                "\n<!-- jresearchsoftware-reviewer-acceptance:v1 authority_sha256={} -->",
                binding["authority"]["sha256"].as_str().unwrap()
            ));
            if binding["source_pr"].is_object() {
                current_body.push_str("\n<!-- jresearchsoftware-reviewer-source-pr:v1 -->");
            }
        }
        let legacy_body = if arguments["action"] == "REQUEST_CHANGES" {
            format!(
                "{}\n\n<!-- jresearchsoftware-reviewer-relay:v1 operation={operation} -->",
                executable_cr::render_legacy(&app.policy.validation_names, arguments)
                    .expect("validated CR")
            )
        } else {
            current_body.clone()
        };
        let retained = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .publication_body(&operation)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        let expected = retained.unwrap_or_else(|| {
            if known.is_some() {
                legacy_body.clone()
            } else {
                current_body.clone()
            }
        });
        if let Some(native) = native {
            let body = native["body"]
                .as_str()
                .ok_or("REVIEW_CONTRACT_VERIFICATION_FAILED")?;
            // Missing local state permits recovery of recognized original
            // renderer bytes, never caller adoption of arbitrary remote prose.
            if body != expected && !(known.is_none() && body == legacy_body) {
                return Err("REVIEW_CONTRACT_VERIFICATION_FAILED");
            }
            let (_, frozen) = app
                .store
                .lock()
                .map_err(|_| "INTERNAL_RELAY_ERROR")?
                .recover_publication(&operation, body, &legacy_body)
                .map_err(|_| "INTERNAL_RELAY_ERROR")?;
            if frozen != body {
                return Err("REVIEW_CONTRACT_VERIFICATION_FAILED");
            }
            verify_approval_authority(app, &operation, binding.as_ref(), true)?;
            return Ok(
                record_review(app, &operation, &native, "DUPLICATE_SUPPRESSED", arguments).await,
            );
        }
        if app.policy.github_native_authority_enabled
            && arguments["action"] == "REQUEST_CHANGES"
            && known.is_none()
        {
            return Err("CURRENT_PROTOCOL_REQUIRED");
        }
        let (reserved, body) = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .reserve_publication(&operation, &current_body, &legacy_body)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if !reserved {
            return Err("PUBLICATION_UNCERTAIN");
        }
        let before_post = async {
            verify_approval_authority(app, &operation, binding.as_ref(), true)?;
            if let Some(code) = new_cr_step_rejection(&pr, arguments) {
                return Err(code);
            }
            step_sync::prepare(app, &operation, arguments).await?;
            let fresh = app
                .github
                .get_pr(&app.repository, arguments["pr_number"].as_i64().unwrap())
                .await?;
            if let Some(code) = target_binding_rejection(&app.policy, &fresh, arguments)
                .or_else(|| publication_rejection(&fresh, &arguments["expected_head_sha"]))
            {
                return Err(code);
            }
            let latest = current_approval_authority(app, arguments).await?;
            verify_approval_authority(app, &operation, latest.as_ref(), false)
        }
        .await;
        if let Err(code) = before_post {
            app.store
                .lock()
                .map_err(|_| "INTERNAL_RELAY_ERROR")?
                .retryable_failure(&operation)
                .map_err(|_| "INTERNAL_RELAY_ERROR")?;
            return Err(code);
        }
        let payload = json!({"commit_id":arguments["expected_head_sha"],"event":arguments["action"],"body":body});
        let mutation = match app
            .github
            .prepare_review(
                &app.repository,
                arguments["pr_number"].as_i64().unwrap(),
                &payload,
            )
            .await
        {
            Ok(prepared) => app.github.send_mutation(prepared).await,
            Err(failure) => Err(failure),
        };
        match mutation {
            Ok(review) => Ok(record_review(app, &operation, &review, "PUBLISHED", arguments).await),
            Err(failure) => {
                if failure.safe_to_retry {
                    app.store
                        .lock()
                        .map_err(|_| "INTERNAL_RELAY_ERROR")?
                        .retryable_failure(&operation)
                        .map_err(|_| "INTERNAL_RELAY_ERROR")?;
                }
                let mut result = task_authority::error(failure.code);
                result["structuredContent"] = json!({"operation":operation,"diagnostics":failure.diagnostics(),"operator_action":"Repeat the identical input to reconcile this original operation; an uncertain decisive POST is never repeated."});
                Ok(result)
            }
        }
    };
    tokio::time::timeout(std::time::Duration::from_secs(60), future)
        .await
        .unwrap_or(Err("PUBLICATION_UNCERTAIN"))
        .unwrap_or_else(task_authority::error)
}
