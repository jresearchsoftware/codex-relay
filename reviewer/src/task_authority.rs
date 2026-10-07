//! Trusted publication of opted-in, typed GitHub-native Task records.
//! This publisher never executes a Task, publishes a Writer Outcome or merges.
use crate::*;
use std::{collections::HashSet, sync::OnceLock};

pub(crate) fn definition() -> &'static Value {
    static SCHEMA: OnceLock<Value> = OnceLock::new();
    SCHEMA.get_or_init(|| {
        serde_json::from_str(include_str!("../../contracts/src/github-authority-v1.json"))
            .expect("source-controlled authority schema")
    })
}

pub(crate) fn hash(body: &str) -> String {
    format!("{:x}", Sha256::digest(body.as_bytes()))
}

fn safe_text(text: &str) -> bool {
    !text.trim().is_empty() && text.nfc().eq(text.chars())
        && !text.chars().any(|ch| {
            ch.is_control()
                || matches!(ch, '\u{fffd}' | '\u{200b}'..='\u{200f}' | '\u{2028}'..='\u{202e}' | '\u{2060}'..='\u{2069}' | '\u{feff}')
        })
}

fn format_matches(text: &str, format: &str) -> bool {
    match format {
        "repository" => valid_repository(text),
        "git-sha" | "sha256" => {
            text.len() == if format == "git-sha" { 40 } else { 64 }
                && text
                    .bytes()
                    .all(|ch| ch.is_ascii_digit() || (b'a'..=b'f').contains(&ch))
        }
        "argument" => {
            text.starts_with(|ch: char| ch.is_ascii_alphanumeric())
                && text
                    .bytes()
                    .all(|ch| ch.is_ascii_alphanumeric() || b"._-".contains(&ch))
                && !["github_pat_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_"]
                    .iter()
                    .any(|prefix| {
                        text.match_indices(prefix).any(|(at, _)| {
                            text[at + prefix.len()..]
                                .bytes()
                                .take_while(|ch| ch.is_ascii_alphanumeric() || *ch == b'_')
                                .count()
                                >= 20
                        })
                    })
        }
        "stable-id" => {
            text.starts_with(|ch: char| ch.is_ascii_alphabetic())
                && text
                    .bytes()
                    .all(|ch| ch.is_ascii_alphanumeric() || b"_-".contains(&ch))
        }
        "validation-id" => {
            text.starts_with(|ch: char| ch.is_ascii_lowercase())
                && text
                    .bytes()
                    .all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == b'-')
        }
        "branch" => {
            text.starts_with(|ch: char| ch.is_ascii_alphanumeric())
                && text
                    .bytes()
                    .all(|ch| ch.is_ascii_alphanumeric() || b"._-/".contains(&ch))
                && !text.contains("..")
                && text.split('/').all(|part| {
                    !part.is_empty() && !part.starts_with('.') && !part.ends_with(".lock")
                })
                && !text.ends_with('.')
        }
        _ => false,
    }
}

// Interpret only the small keyword vocabulary in the checked-in definition.
fn conforms(value: &Value, schema: &Value) -> bool {
    if let Some(variants) = schema["anyOf"].as_array() {
        return variants.iter().any(|spec| conforms(value, spec));
    }
    if schema["enum"]
        .as_array()
        .is_some_and(|variants| !variants.contains(value))
    {
        return false;
    }
    match schema["type"].as_str() {
        Some("object") => value.as_object().is_some_and(|object| {
            schema["required"].as_array().is_some_and(|required| {
                required
                    .iter()
                    .all(|key| key.as_str().is_some_and(|key| object.contains_key(key)))
            }) && object.iter().all(|(key, value)| {
                schema["properties"]
                    .get(key)
                    .is_some_and(|spec| conforms(value, spec))
            })
        }),
        Some("array") => value.as_array().is_some_and(|items| {
            items.len() >= schema["minItems"].as_u64().unwrap_or(0) as usize
                && items.len() <= schema["maxItems"].as_u64().unwrap_or(0) as usize
                && items.iter().all(|item| conforms(item, &schema["items"]))
                && (schema["uniqueItems"] != true
                    || items
                        .iter()
                        .enumerate()
                        .all(|(index, item)| !items[..index].contains(item)))
        }),
        Some("string") => value.as_str().is_some_and(|text| {
            text.len() >= schema["minLength"].as_u64().unwrap_or(0) as usize
                && text.len() <= schema["maxLength"].as_u64().unwrap_or(1000) as usize
                && safe_text(text)
                && schema["format"]
                    .as_str()
                    .is_none_or(|format| format_matches(text, format))
        }),
        Some("integer") => value.as_u64().is_some_and(|number| {
            number >= schema["minimum"].as_u64().unwrap_or(0)
                && number <= schema["maximum"].as_u64().unwrap_or(0)
        }),
        Some("boolean") => value.is_boolean(),
        Some("null") => value.is_null(),
        _ => false,
    }
}

pub(crate) fn validate_record(record: &Value) -> Result<(), &'static str> {
    let kind = record["kind"].as_str().ok_or("AUTHORITY_RECORD_INVALID")?;
    if !definition()["input_schemas"]
        .get(kind)
        .is_some_and(|schema| conforms(record, schema))
        || serde_json::to_string_pretty(record).map_or(true, |text| {
            text.len() > definition()["max_payload_bytes"].as_u64().unwrap() as usize
        })
    {
        return Err("AUTHORITY_RECORD_INVALID");
    }
    let task = record["task"].as_u64().unwrap();
    if kind == "decision" && record["amendments"].as_object().unwrap().is_empty() {
        return Err("AUTHORITY_DECISION_EMPTY");
    }
    if kind == "change-request" {
        if record["parent"]["kind"] != "pull_request"
            || record["existing_pr"] != record["parent"]["number"]
            || record["starting_head"] != record["reviewed_head_sha"]
            || !record["supersedes"].is_object()
        {
            return Err("CHANGE_REQUEST_BINDING_INVALID");
        }
    } else if !matches!(kind, "outcome" | "decision")
        && (record["parent"]["kind"] != "issue"
            || record["parent"]["number"].as_u64() != Some(task))
    {
        return Err("AUTHORITY_PARENT_INVALID");
    }
    if kind == "decision"
        && record["parent"]["kind"] == "issue"
        && record["parent"]["number"] != record["task"]
    {
        return Err("AUTHORITY_PARENT_INVALID");
    }
    if matches!(kind, "task-request" | "change-request") {
        if (kind == "change-request" || record["route"] == "auto")
            && ["branch", "base_sha", "starting_head"]
                .iter()
                .any(|key| !record[key].is_string())
        {
            return Err("AUTHORITY_EXECUTION_BINDING_INVALID");
        }
        let fields: Vec<_> = ["branch", "base_sha", "starting_head"]
            .iter()
            .map(|key| record[key].is_null())
            .collect();
        if fields.iter().any(|null| *null) && !fields.iter().all(|null| *null) {
            return Err("AUTHORITY_EXECUTION_BINDING_INVALID");
        }
        if !record["existing_pr"].is_null() && record["branch"].is_null() {
            return Err("AUTHORITY_EXECUTION_BINDING_INVALID");
        }
        let mut references = HashSet::new();
        for reference in record["context"]
            .as_array()
            .unwrap()
            .iter()
            .chain(record["decisions"].as_array().unwrap())
        {
            let key = json!([reference["kind"], reference["id"], reference["parent"]]).to_string();
            if !references.insert(key) {
                return Err("AUTHORITY_REFERENCE_DUPLICATE");
            }
        }
    }
    if matches!(kind, "change-request" | "task-review") {
        let mut ids = HashSet::new();
        if record["findings"]
            .as_array()
            .unwrap()
            .iter()
            .any(|finding| !ids.insert(&finding["id"]))
        {
            return Err("AUTHORITY_FINDINGS_DUPLICATE");
        }
    }
    if matches!(kind, "outcome" | "task-approval" | "task-review")
        && ((record["result"]["kind"] == "git"
            && record["result"]["revision"]
                .as_str()
                .is_none_or(|revision| !format_matches(revision, "git-sha")))
            || (record["result"]["revision"].is_null()
                && record["result"]["identities"]
                    .as_array()
                    .unwrap()
                    .is_empty()))
    {
        return Err("AUTHORITY_RESULT_IDENTITY_REQUIRED");
    }
    if matches!(kind, "outcome" | "task-approval" | "task-review") {
        let mut identities = HashSet::new();
        if record["result"]["identities"]
            .as_array()
            .unwrap()
            .iter()
            .any(|identity| {
                !identities.insert(json!([identity["kind"], identity["id"]]).to_string())
            })
        {
            return Err("AUTHORITY_RESULT_IDENTITY_DUPLICATE");
        }
        let mut warnings = HashSet::new();
        if record["warnings"]
            .as_array()
            .unwrap()
            .iter()
            .any(|warning| !warnings.insert(&warning["source"]))
        {
            return Err("AUTHORITY_WARNING_DUPLICATE");
        }
    }
    Ok(())
}

pub(crate) fn render(record: &Value) -> String {
    // serde_json's default map uses sorted keys, matching the Node canonicalizer.
    format!(
        "## Relay {}\n\nAuthority model: github-native-v1\n\n```relay-authority\n{}\n```\n",
        definition()["record_titles"][record["kind"].as_str().unwrap()]
            .as_str()
            .unwrap(),
        serde_json::to_string_pretty(record).expect("validated record")
    )
}

fn parse(body: &str) -> Result<Option<Value>, &'static str> {
    if body.len() > definition()["max_body_bytes"].as_u64().unwrap() as usize {
        return Err("AUTHORITY_BODY_TOO_LARGE");
    }
    let fence = "```relay-authority\n";
    let Some((_, rest)) = body.split_once(fence) else {
        return Ok(None);
    };
    if body
        .lines()
        .filter(|line| line.starts_with("```relay-authority"))
        .count()
        != 1
        || body.contains("```reviewer-executable-cr")
        || body.contains("```yaml")
        || body.contains("```yml")
    {
        return Err("AUTHORITY_RECORD_AMBIGUOUS");
    }
    let (payload, _) = rest.split_once("\n```").ok_or("AUTHORITY_RECORD_INVALID")?;
    let record = serde_json::from_str::<strict_json::StrictJson>(payload)
        .map_err(|_| "AUTHORITY_RECORD_INVALID")?
        .0;
    validate_record(&record)?;
    if serde_json::to_string_pretty(&record).unwrap() != payload {
        return Err("AUTHORITY_RECORD_NONCANONICAL");
    }
    Ok(Some(record))
}

pub(crate) fn tool(repositories: &BTreeSet<String>) -> Value {
    let variants: Vec<_> = [
        "decision",
        "task-request",
        "change-request",
        "task-approval",
        "task-review",
    ]
    .iter()
    .filter_map(|kind| definition()["input_schemas"].get(kind).cloned())
    .collect();
    json!({"name":"publish_task_authority",
        "description":"Publish owner-authorized typed Decisions, Task Requests, PR-only Change Requests, Task review evidence or independent Task Approvals. Re-read all native references and current authority; never execute, publish Writer Outcomes or merge.",
        "inputSchema":{"type":"object","additionalProperties":false,"required":["repository","record"],"properties":{
            "repository":repository_schema(repositories),"record":{"anyOf":variants}}},
        "annotations":{"readOnlyHint":false,"destructiveHint":true,"idempotentHint":true,"openWorldHint":true}})
}

pub(crate) fn valid_input(
    repositories: &BTreeSet<String>,
    args: &Value,
) -> Result<(), &'static str> {
    let object = args.as_object().ok_or("INVALID_PAYLOAD")?;
    if object.len() != 2 || !object.contains_key("record") || !object.contains_key("repository") {
        return Err("INVALID_PAYLOAD");
    }
    let repository = args["repository"]
        .as_str()
        .filter(|repository| repositories.contains(*repository))
        .ok_or("REPOSITORY_NOT_ALLOWED")?;
    if args["record"]["repository"] != repository {
        return Err("REPOSITORY_NOT_ALLOWED");
    }
    if args["record"]["kind"] == "outcome" {
        return Err("WRITER_OUTCOME_PUBLICATION_FORBIDDEN");
    }
    if serde_json::to_vec(args).map_or(true, |bytes| {
        bytes.len() > definition()["max_payload_bytes"].as_u64().unwrap() as usize
    }) {
        return Err("PAYLOAD_TOO_LARGE");
    }
    validate_record(&args["record"])?;
    if render(&args["record"]).len() > definition()["max_body_bytes"].as_u64().unwrap() as usize {
        return Err("AUTHORITY_BODY_TOO_LARGE");
    }
    Ok(())
}

fn trusted_user(native: &Value, expected: &Value) -> bool {
    native["login"] == expected["login"]
        && native["id"] == expected["id"]
        && native["type"] == expected["type"]
        && native["id"].as_u64().is_some_and(|id| id > 0)
}

fn normalized_author(user: &Value) -> Value {
    json!({"login":user["login"].as_str().filter(|login| login.len() <= 100),
        "id":user["id"].as_u64().filter(|id| *id > 0 && *id <= 9_007_199_254_740_991),
        "type":user["type"].as_str().filter(|kind| kind.len() <= 32)})
}

fn native_ref(native: &Value, kind: &str, parent: &Value) -> Result<Value, &'static str> {
    let body = native["body"].as_str().ok_or("AUTHORITY_SOURCE_INVALID")?;
    let id = native["id"]
        .as_u64()
        .filter(|id| *id > 0 && *id <= 9_007_199_254_740_991)
        .ok_or("AUTHORITY_SOURCE_INVALID")?;
    Ok(json!({"kind":kind,"id":id,"parent":parent,"sha256":hash(body)}))
}

fn source_binding(repository: &str, source: &Value, reference: &Value) -> Result<(), &'static str> {
    if source["id"] != reference["id"]
        || source["body"]
            .as_str()
            .is_none_or(|body| hash(body) != reference["sha256"])
    {
        return Err("AUTHORITY_REFERENCE_CHANGED");
    }
    let parent = &reference["parent"];
    let number = parent["number"]
        .as_u64()
        .ok_or("AUTHORITY_PARENT_INVALID")?;
    let kind = reference["kind"].as_str().unwrap_or("");
    let api_parent = format!(
        "https://api.github.com/repos/{repository}/{}s/{number}",
        if parent["kind"] == "issue" {
            "issue"
        } else {
            "pull"
        }
    );
    let bound = match kind {
        "issue-body" => {
            parent["kind"] == "issue"
                && source["number"].as_u64() == Some(number)
                && source["repository_url"] == format!("https://api.github.com/repos/{repository}")
        }
        "issue-comment" => {
            source["issue_url"]
                == format!("https://api.github.com/repos/{repository}/issues/{number}")
        }
        "review" | "review-comment" => {
            parent["kind"] == "pull_request" && source["pull_request_url"] == api_parent
        }
        _ => false,
    };
    if !bound {
        return Err("AUTHORITY_PARENT_MISMATCH");
    }
    Ok(())
}

struct NativeAuthority {
    issue: Value,
    publisher: Value,
    writer: Value,
    comments: Vec<Value>,
}

async fn load(app: &RepositoryTarget<'_>, record: &Value) -> Result<NativeAuthority, &'static str> {
    let task = record["task"].as_u64().unwrap();
    let issue = app
        .github
        .authority_source(&app.repository, "issue-body", task, 0)
        .await?;
    let owner = app
        .github
        .authority_user(&app.repository, &app.policy.owner)
        .await?;
    let publisher = app
        .github
        .authority_user(&app.repository, &app.policy.actor)
        .await?;
    let writer = app
        .github
        .authority_user(&app.repository, &app.policy.writer_actor)
        .await?;
    for (native, login, kind) in [
        (&owner, app.policy.owner.as_str(), "User"),
        (&publisher, app.policy.actor.as_str(), "Bot"),
        (&writer, app.policy.writer_actor.as_str(), "Bot"),
    ] {
        if native["login"] != login
            || native["type"] != kind
            || native["id"].as_u64().is_none_or(|id| id == 0)
        {
            return Err("AUTHORITY_ACTOR_UNVERIFIED");
        }
    }
    let body = issue["body"].as_str().ok_or("ISSUE_NOT_ADMITTED")?;
    let markers: Vec<_> = body
        .lines()
        .filter(|line| {
            line.trim_start_matches(|ch: char| ch.is_whitespace() || ch == '-' || ch == '*')
                .to_ascii_lowercase()
                .starts_with("authority model")
        })
        .collect();
    if markers.len() != 1 || markers[0] != "Authority model: github-native-v1" {
        return Err("AUTHORITY_MODEL_NOT_ADMITTED");
    }
    if issue["number"].as_u64() != Some(task)
        || issue.get("pull_request").is_some()
        || issue["state"] != "open"
        || !trusted_user(&issue["user"], &owner)
        || issue["repository_url"] != format!("https://api.github.com/repos/{}", app.repository)
    {
        return Err("ISSUE_NOT_ADMITTED");
    }
    if record["charter_sha256"] != hash(body) {
        return Err("CHARTER_CHANGED");
    }
    let identity = app.github.app_identity().await?;
    if !identity_matches(&app.policy, &identity) {
        return Err("ACTOR_VERIFICATION_FAILED");
    }
    let comments = app.github.authority_comments(&app.repository, task).await?;
    Ok(NativeAuthority {
        issue,
        publisher,
        writer,
        comments,
    })
}

fn belongs(record: &Value, expected: &Value) -> bool {
    record["repository"] == expected["repository"]
        && record["task"] == expected["task"]
        && record["charter_sha256"] == expected["charter_sha256"]
}

async fn read_ref(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    reference: &Value,
) -> Result<Value, &'static str> {
    let parent = &reference["parent"];
    let number = parent["number"]
        .as_u64()
        .ok_or("AUTHORITY_PARENT_INVALID")?;
    if parent["kind"] == "issue" {
        if parent["number"] != record["task"] {
            return Err("AUTHORITY_PARENT_MISMATCH");
        }
    } else if parent["kind"] == "pull_request" {
        let pr = app.github.get_pr(&app.repository, number as i64).await?;
        if step_sync::linked_issue(&pr)? != record["task"].as_u64().unwrap()
            || pr.pointer("/base/repo/full_name") != Some(&record["repository"])
            || pr.pointer("/head/repo/full_name") != Some(&record["repository"])
            || pr.pointer("/base/ref").and_then(Value::as_str)
                != Some(app.policy.base_branch.as_str())
        {
            return Err("AUTHORITY_PARENT_MISMATCH");
        }
    } else {
        return Err("AUTHORITY_PARENT_INVALID");
    }
    let source = if reference["kind"] == "issue-body" {
        state.issue.clone()
    } else {
        app.github
            .authority_source(
                &app.repository,
                reference["kind"].as_str().unwrap_or(""),
                number,
                reference["id"]
                    .as_u64()
                    .ok_or("AUTHORITY_REFERENCE_INVALID")?,
            )
            .await?
    };
    source_binding(&app.repository, &source, reference)?;
    Ok(source)
}

async fn trusted_record(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    reference: &Value,
    writer: bool,
) -> Result<Value, &'static str> {
    let source = read_ref(app, state, record, reference).await?;
    if !trusted_user(
        &source["user"],
        if writer {
            &state.writer
        } else {
            &state.publisher
        },
    ) {
        return Err("AUTHORITY_SOURCE_UNTRUSTED");
    }
    let payload = parse(source["body"].as_str().unwrap())?.ok_or("AUTHORITY_RECORD_MISSING")?;
    if !belongs(&payload, record) || payload["parent"] != reference["parent"] {
        return Err("AUTHORITY_RECORD_BINDING_MISMATCH");
    }
    Ok(payload)
}

fn list_records(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    natives: &[Value],
    kind: &str,
    parent: &Value,
) -> Result<Vec<(Value, Value)>, &'static str> {
    let mut found = Vec::new();
    for native in natives {
        if !trusted_user(&native["user"], &state.publisher) {
            continue;
        }
        let Some(body) = native["body"].as_str() else {
            return Err("AUTHORITY_SOURCE_INVALID");
        };
        if let Some(payload) = parse(body)? {
            if payload["repository"] == record["repository"] && payload["task"] == record["task"] {
                let reference = native_ref(native, kind, parent)?;
                source_binding(&app.repository, native, &reference)?;
                if payload["parent"] != *parent {
                    return Err("AUTHORITY_PARENT_MISMATCH");
                }
                found.push((reference, payload));
            }
        }
    }
    Ok(found)
}

async fn execution_records(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
) -> Result<Vec<(Value, Value)>, &'static str> {
    let parent = json!({"kind":"issue","number":record["task"]});
    let mut records = list_records(
        app,
        state,
        record,
        &state.comments,
        "issue-comment",
        &parent,
    )?;
    let mut observed = state.comments.len();
    let mut prs: HashSet<u64> = records
        .iter()
        .filter_map(|(_, record)| record["existing_pr"].as_u64())
        .collect();
    if let Some(pr) = record["existing_pr"].as_u64() {
        prs.insert(pr);
    }
    if let Some(pr) = record["request"]["parent"]["number"]
        .as_u64()
        .filter(|_| record["request"]["parent"]["kind"] == "pull_request")
    {
        prs.insert(pr);
    }
    for key in ["supersedes", "outcome"] {
        if record[key]["parent"]["kind"] == "pull_request" {
            if let Some(pr) = record[key]["parent"]["number"].as_u64() {
                prs.insert(pr);
            }
        }
    }
    for (reference, payload) in &records {
        if payload["kind"] == "task-request" && payload["existing_pr"].is_null() {
            if let Some(branch) = payload["branch"].as_str() {
                let artifacts = app
                    .github
                    .authority_artifacts(&app.repository, &app.policy.base_branch, branch)
                    .await?;
                observed += artifacts.len();
                if observed > definition()["max_native_records"].as_u64().unwrap() as usize {
                    return Err("AUTHORITY_SOURCE_TRUNCATED");
                }
                let mut bound = Vec::new();
                for artifact in artifacts {
                    let Some(body) = artifact["body"].as_str() else {
                        return Err("AUTHORITY_SOURCE_INVALID");
                    };
                    if body.lines().any(|line| {
                        line == format!(
                            "Execution request digest: {}",
                            reference["sha256"].as_str().unwrap()
                        )
                    }) {
                        if artifact["head"]["ref"] != branch
                            || artifact["head"]["repo"]["full_name"] != app.repository
                            || artifact["base"]["repo"]["full_name"] != app.repository
                            || artifact["base"]["ref"] != app.policy.base_branch
                            || step_sync::linked_issue(&artifact)?
                                != record["task"].as_u64().unwrap()
                            || !body.lines().any(|line| {
                                line == format!("Execution request native ID: {}", reference["id"])
                            })
                        {
                            return Err("AUTHORITY_PR_BINDING_MISMATCH");
                        }
                        bound.push(
                            artifact["number"]
                                .as_u64()
                                .filter(|pr| *pr > 0)
                                .ok_or("AUTHORITY_SOURCE_INVALID")?,
                        );
                    }
                }
                if bound.len() > 1 {
                    return Err("AUTHORITY_PR_BINDING_AMBIGUOUS");
                }
                prs.extend(bound);
            }
        }
    }
    if prs.len() > 20 {
        return Err("AUTHORITY_SOURCE_TRUNCATED");
    }
    for pr in prs {
        let live = app.github.get_pr(&app.repository, pr as i64).await?;
        if step_sync::linked_issue(&live)? != record["task"].as_u64().unwrap()
            || live.pointer("/base/repo/full_name") != Some(&record["repository"])
            || live.pointer("/head/repo/full_name") != Some(&record["repository"])
        {
            return Err("AUTHORITY_PARENT_MISMATCH");
        }
        let reviews = app.github.authority_reviews(&app.repository, pr).await?;
        observed += reviews.len();
        if observed > definition()["max_native_records"].as_u64().unwrap() as usize {
            return Err("AUTHORITY_SOURCE_TRUNCATED");
        }
        let parent = json!({"kind":"pull_request","number":pr});
        for (reference, payload) in list_records(app, state, record, &reviews, "review", &parent)? {
            if payload["kind"] == "change-request" {
                let native = reviews
                    .iter()
                    .find(|review| review["id"] == reference["id"])
                    .unwrap();
                if native["commit_id"] != payload["reviewed_head_sha"] {
                    return Err("AUTHORITY_REVIEW_INVALID");
                }
                records.push((reference, payload));
            }
        }
    }
    records.retain(|(_, payload)| {
        matches!(
            payload["kind"].as_str(),
            Some("task-request" | "change-request")
        )
    });
    if records.len() > 500 {
        return Err("AUTHORITY_SOURCE_TRUNCATED");
    }
    Ok(records)
}

fn current(records: &[(Value, Value)]) -> Result<Option<&(Value, Value)>, &'static str> {
    if records.is_empty() {
        return Ok(None);
    }
    if records
        .iter()
        .filter(|(_, payload)| payload["supersedes"].is_null())
        .count()
        != 1
    {
        return Err("AUTHORITY_REQUEST_CHAIN_AMBIGUOUS");
    }
    for (reference, payload) in records {
        if !payload["supersedes"].is_null()
            && !records
                .iter()
                .any(|(prior, _)| *prior == payload["supersedes"])
        {
            return Err("AUTHORITY_REQUEST_PREDECESSOR_MISSING");
        }
        if records
            .iter()
            .filter(|(_, next)| next["supersedes"] == *reference)
            .count()
            > 1
        {
            return Err("AUTHORITY_REQUEST_CHAIN_AMBIGUOUS");
        }
        for (_, next) in records
            .iter()
            .filter(|(_, next)| next["supersedes"] == *reference)
        {
            let previous = payload["step"].as_u64().unwrap();
            let step = next["step"].as_u64().unwrap();
            if step < previous
                || step > previous.saturating_add(1)
                || (next["kind"] == "change-request"
                    && step != previous.saturating_add(1)
                    && !same_cr(payload, next))
            {
                return Err("AUTHORITY_STEP_INVALID");
            }
        }
    }
    let terminal: Vec<_> = records
        .iter()
        .filter(|(reference, _)| {
            !records
                .iter()
                .any(|(_, next)| next["supersedes"] == *reference)
        })
        .collect();
    if terminal.len() != 1 {
        return Err("AUTHORITY_REQUEST_CHAIN_AMBIGUOUS");
    }
    let mut seen = HashSet::new();
    let mut cursor = terminal[0];
    loop {
        if !seen.insert(cursor.0.to_string()) {
            return Err("AUTHORITY_REQUEST_CHAIN_AMBIGUOUS");
        }
        if cursor.1["supersedes"].is_null() {
            break;
        }
        cursor = records
            .iter()
            .find(|(reference, _)| *reference == cursor.1["supersedes"])
            .ok_or("AUTHORITY_REQUEST_PREDECESSOR_MISSING")?;
    }
    if seen.len() != records.len() {
        return Err("AUTHORITY_REQUEST_CHAIN_AMBIGUOUS");
    }
    Ok(Some(terminal[0]))
}

fn same_cr(prior: &Value, next: &Value) -> bool {
    prior["kind"] == "change-request"
        && next["kind"] == "change-request"
        && prior["change_request_id"] == next["change_request_id"]
        && prior["reviewed_head_sha"] == next["reviewed_head_sha"]
        && prior["parent"] == next["parent"]
}

fn closure_policy(body: &str) -> (&str, Vec<&str>) {
    let lines: Vec<_> = body
        .lines()
        .filter(|line| {
            line.trim_start_matches(|ch: char| ch.is_whitespace() || ch == '-' || ch == '*')
                .to_ascii_lowercase()
                .starts_with("issue closure policy")
        })
        .collect();
    if lines.len() == 1 {
        match lines[0] {
            "Issue closure policy: keep-open" => return ("keep-open", vec![]),
            "Issue closure policy: close-authorized" => return ("close-authorized", vec![]),
            _ => {}
        }
    }
    ("keep-open", vec!["ISSUE_CLOSURE_POLICY_INVALID"])
}

async fn validate_live(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    published: Option<&Value>,
) -> Result<Value, &'static str> {
    let kind = record["kind"].as_str().unwrap();
    let continuation = record
        .get("continuation")
        .or_else(|| record["amendments"].get("continuation"));
    if let Some(next) = continuation
        .and_then(|plan| plan.get("next"))
        .filter(|next| !next.is_null())
    {
        let reference = next
            .get("request")
            .or_else(|| next.get("direction"))
            .ok_or("AUTHORITY_NEXT_REFERENCE_INVALID")?;
        if next.get("direction").is_some()
            && (next["task"] != record["task"]
                || reference["parent"]["kind"] != "issue"
                || reference["parent"]["number"] != record["task"]
                || (matches!(kind, "task-request" | "change-request")
                    && (!record["decisions"].as_array().unwrap().contains(reference)
                        || next["step"].as_u64().unwrap() < record["step"].as_u64().unwrap()
                        || next["step"].as_u64().unwrap() > record["step"].as_u64().unwrap() + 1)))
        {
            return Err("AUTHORITY_NEXT_REFERENCE_INVALID");
        }
        let target = json!({"repository":app.repository,"task":next["task"]});
        let source = read_ref(app, state, &target, reference).await?;
        if !trusted_user(&source["user"], &state.publisher) {
            return Err("AUTHORITY_NEXT_REFERENCE_UNTRUSTED");
        }
        let payload = parse(source["body"].as_str().unwrap())?.ok_or("AUTHORITY_RECORD_MISSING")?;
        if payload["repository"] != app.repository
            || payload["task"] != next["task"]
            || payload["parent"] != reference["parent"]
            || (next.get("request").is_some() && payload["kind"] != "task-request")
            || (next.get("direction").is_some() && payload["kind"] != "decision")
        {
            return Err("AUTHORITY_NEXT_REFERENCE_INVALID");
        }
        let next_state = load(app, &payload).await?;
        if next.get("request").is_some() {
            let next_records = execution_records(app, &next_state, &payload).await?;
            if current(&next_records)?.is_none_or(|(current, _)| current != reference) {
                return Err("AUTHORITY_NEXT_REFERENCE_SUPERSEDED");
            }
            if step_sync::current_step(&next_state.issue)? != payload["step"].as_u64().unwrap() {
                return Err("AUTHORITY_NEXT_STEP_MISMATCH");
            }
        } else {
            let natives = if payload["parent"]["kind"] == "pull_request" {
                app.github
                    .authority_comments(
                        &app.repository,
                        payload["parent"]["number"].as_u64().unwrap(),
                    )
                    .await?
            } else {
                next_state.comments.clone()
            };
            let decisions = list_records(
                app,
                &next_state,
                &payload,
                &natives,
                "issue-comment",
                &payload["parent"],
            )?;
            if decisions.iter().any(|(_, decision)| {
                decision["kind"] == "decision" && decision["supersedes"] == *reference
            }) {
                return Err("AUTHORITY_NEXT_REFERENCE_SUPERSEDED");
            }
        }
    }
    let mut context = Vec::new();
    let mut context_bytes = 0;
    if let Some(refs) = record["context"].as_array() {
        for reference in refs {
            let source = read_ref(app, state, record, reference).await?;
            context_bytes += source["body"].as_str().unwrap().len();
            if context_bytes > definition()["max_context_bytes"].as_u64().unwrap() as usize {
                return Err("AUTHORITY_CONTEXT_TOO_LARGE");
            }
            context.push(json!({"reference":reference,"author":normalized_author(&source["user"]),"body_sha256":reference["sha256"]}));
        }
    }
    if kind == "decision" {
        if record["parent"]["kind"] == "pull_request" {
            let pr = app
                .github
                .get_pr(
                    &app.repository,
                    record["parent"]["number"].as_i64().unwrap(),
                )
                .await?;
            if step_sync::linked_issue(&pr)? != record["task"].as_u64().unwrap()
                || pr["base"]["repo"]["full_name"] != app.repository
                || pr["head"]["repo"]["full_name"] != app.repository
                || pr["base"]["ref"] != app.policy.base_branch
            {
                return Err("AUTHORITY_PARENT_MISMATCH");
            }
        }
        if !record["supersedes"].is_null() {
            let prior = trusted_record(app, state, record, &record["supersedes"], false).await?;
            if prior["kind"] != "decision" || prior["parent"] != record["parent"] {
                return Err("AUTHORITY_DECISION_SUPERSESSION_INVALID");
            }
        }
        return Ok(json!({"context_provenance":context}));
    }
    let records = execution_records(app, state, record).await?;
    let selected = current(&records)?;
    if matches!(kind, "task-request" | "change-request") {
        let active = if selected.is_some_and(|(reference, _)| published == Some(reference)) {
            if record["supersedes"].is_null() {
                None
            } else {
                Some(
                    records
                        .iter()
                        .find(|(reference, _)| *reference == record["supersedes"])
                        .ok_or("AUTHORITY_REQUEST_PREDECESSOR_MISSING")?,
                )
            }
        } else {
            selected
        };
        match active {
            Some((reference, prior)) => {
                if record["supersedes"] != *reference {
                    return Err("AUTHORITY_REQUEST_SUPERSESSION_REQUIRED");
                }
                trusted_record(app, state, record, reference, false).await?;
                let previous = prior["step"].as_u64().unwrap();
                let next = record["step"].as_u64().unwrap();
                if next < previous
                    || next > previous.saturating_add(1)
                    || (kind == "change-request"
                        && next != previous.saturating_add(1)
                        && !same_cr(prior, record))
                {
                    return Err("AUTHORITY_STEP_INVALID");
                }
            }
            None if !record["supersedes"].is_null() || kind == "change-request" => {
                return Err("AUTHORITY_REQUEST_PREDECESSOR_MISSING")
            }
            None => {}
        }
        let step = record["step"].as_u64().unwrap();
        let current_step = step_sync::current_step(&state.issue)?;
        let allowed = active
            .map(|(_, prior)| prior["step"].as_u64().unwrap())
            .unwrap_or(step);
        if current_step != allowed && !(published.is_some() && current_step == step) {
            return Err("AUTHORITY_STEP_MISMATCH");
        }
        let (closure, _) = closure_policy(state.issue["body"].as_str().unwrap());
        if record["issue_closure_policy"] != closure {
            return Err("AUTHORITY_CLOSURE_MISMATCH");
        }
        let parent = json!({"kind":"issue","number":record["task"]});
        let mut decisions = list_records(
            app,
            state,
            record,
            &state.comments,
            "issue-comment",
            &parent,
        )?;
        let mut decision_prs = HashSet::new();
        for reference in record["decisions"].as_array().unwrap() {
            if reference["parent"]["kind"] == "pull_request" {
                decision_prs.insert(reference["parent"]["number"].as_u64().unwrap());
            }
        }
        for pr in decision_prs {
            let natives = app.github.authority_comments(&app.repository, pr).await?;
            decisions.extend(list_records(
                app,
                state,
                record,
                &natives,
                "issue-comment",
                &json!({"kind":"pull_request","number":pr}),
            )?);
        }
        let mut normalized = serde_json::Map::new();
        for reference in record["decisions"].as_array().unwrap() {
            if reference["kind"] != "issue-comment" {
                return Err("AUTHORITY_DECISION_UNTRUSTED");
            }
            let decision = trusted_record(app, state, record, reference, false).await?;
            if decision["kind"] != "decision" {
                return Err("AUTHORITY_DECISION_UNTRUSTED");
            }
            if decision["parent"]["kind"] == "pull_request"
                && record["existing_pr"] != decision["parent"]["number"]
            {
                return Err("AUTHORITY_DECISION_SCOPE_MISMATCH");
            }
            if decisions.iter().any(|(_, decision)| {
                decision["kind"] == "decision" && decision["supersedes"] == *reference
            }) {
                return Err("AUTHORITY_DECISION_SUPERSEDED");
            }
            if !decision["supersedes"].is_null() {
                let prior =
                    trusted_record(app, state, record, &decision["supersedes"], false).await?;
                if prior["kind"] != "decision" || prior["parent"] != decision["parent"] {
                    return Err("AUTHORITY_DECISION_SUPERSESSION_INVALID");
                }
            }
            for (key, value) in decision["amendments"].as_object().unwrap() {
                normalized.insert(key.clone(), value.clone());
            }
        }
        for (key, value) in normalized {
            if record[&key] != value {
                return Err("AUTHORITY_DECISION_NOT_NORMALIZED");
            }
        }
        // The configured validation vocabulary is the same one used by CR2.
        let allowed = executable_cr::input_schema(&app.policy.validation_names)["properties"]
            ["required_validation"]["items"]["enum"]
            .clone();
        if record["validation"]
            .as_array()
            .unwrap()
            .iter()
            .any(|name| !allowed.as_array().unwrap().contains(name))
        {
            return Err("AUTHORITY_VALIDATION_UNKNOWN");
        }
        if let Some(pr) = record["existing_pr"].as_u64() {
            let live = app.github.get_pr(&app.repository, pr as i64).await?;
            let args = json!({"repository":app.repository,"pr_number":pr,"expected_head_sha":record["starting_head"]});
            if target_binding_rejection(&app.policy, &live, &args).is_some()
                || live["head"]["ref"] != record["branch"]
                || live["head"]["sha"] != record["starting_head"]
                || step_sync::linked_issue(&live)? != record["task"].as_u64().unwrap()
            {
                return Err("AUTHORITY_PR_BINDING_MISMATCH");
            }
            if let Some(code) = publication_rejection(&live, &record["starting_head"]) {
                return Err(code);
            }
            let pr_step = step_sync::current_step(&live)?;
            if pr_step != current_step
                && !(published.is_some() && [allowed_step(active, step), step].contains(&pr_step))
            {
                return Err("AUTHORITY_STEP_MISMATCH");
            }
        }
    } else if matches!(kind, "task-approval" | "task-review") {
        let (reference, request) = selected.ok_or("AUTHORITY_REQUEST_MISSING")?;
        if request["kind"] != "task-request" || record["request"] != *reference {
            return Err("AUTHORITY_APPROVAL_STALE_REQUEST");
        }
        if record["step"] != request["step"] {
            return Err("AUTHORITY_APPROVAL_STEP_MISMATCH");
        }
        trusted_record(app, state, record, &record["request"], false).await?;
        let outcome = trusted_record(app, state, record, &record["outcome"], true).await?;
        if record["outcome"]["kind"] != "issue-comment"
            || outcome["kind"] != "outcome"
            || outcome["request"] != record["request"]
            || (kind == "task-approval" && outcome["status"] != "implemented")
            || outcome["result"] != record["result"]
        {
            return Err("AUTHORITY_APPROVAL_RESULT_MISMATCH");
        }
        for warning in outcome["warnings"].as_array().unwrap() {
            if !record["warnings"]
                .as_array()
                .unwrap()
                .iter()
                .any(|disposition| {
                    disposition["source"] == warning["source"]
                        && disposition["impact"] == warning["impact"]
                })
            {
                return Err("AUTHORITY_APPROVAL_WARNING_MISSING");
            }
        }
        if outcome["limitations"]
            .as_array()
            .unwrap()
            .iter()
            .any(|limitation| {
                !record["limitations"]
                    .as_array()
                    .unwrap()
                    .contains(limitation)
            })
        {
            return Err("AUTHORITY_APPROVAL_LIMITATIONS_MISSING");
        }
        if step_sync::current_step(&state.issue)? != request["step"].as_u64().unwrap() {
            return Err("AUTHORITY_STEP_MISMATCH");
        }
    }
    Ok(json!({"context_provenance":context}))
}

fn allowed_step(active: Option<&(Value, Value)>, step: u64) -> u64 {
    active
        .map(|(_, prior)| prior["step"].as_u64().unwrap())
        .unwrap_or(step)
}

fn projection_title(record: &Value) -> String {
    let identity = format!("Task {} · Step {}", record["task"], record["step"]);
    let cr = record["change_request_id"]
        .as_str()
        .map(|id| format!(" · {id}"))
        .unwrap_or_default();
    let title = format!("{identity}{cr} · {}", record["purpose"].as_str().unwrap());
    if title.chars().count() <= 56 {
        title
    } else {
        format!("{}…", title.chars().take(55).collect::<String>())
    }
}

async fn bind_projection(
    app: &RepositoryTarget<'_>,
    record: &Value,
    operation: &str,
    prepare: bool,
) -> Result<(), &'static str> {
    let Some(pr_number) = record["existing_pr"].as_i64() else {
        return Ok(());
    };
    let pr = app.github.get_pr(&app.repository, pr_number).await?;
    let store = app.store.lock().map_err(|_| "INTERNAL_RELAY_ERROR")?;
    let previous = store
        .step_binding(operation)
        .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    let identity = json!({"charter":record["charter_sha256"],"pr_body_sha256":hash(pr["body"].as_str().ok_or("AUTHORITY_PR_BINDING_MISMATCH")?),
        "branch":pr["head"]["ref"],"head":pr["head"]["sha"],"base":pr["base"]["ref"]});
    if let Some(previous) = previous {
        let previous: Value =
            serde_json::from_str(&previous).map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if previous["identity"] != identity
            || (pr["title"] != previous["initial_title"] && pr["title"] != projection_title(record))
        {
            return Err("AUTHORITY_CHANGED");
        }
    } else if prepare {
        let initial_title = pr["title"].as_str().ok_or("STEP_DISPLAY_MISMATCH")?;
        store
            .bind_step(
                operation,
                &json!({"identity":identity,"initial_title":initial_title}).to_string(),
            )
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    } else {
        return Err("AUTHORITY_PROJECTION_BINDING_MISSING");
    }
    Ok(())
}

async fn project(
    app: &RepositoryTarget<'_>,
    record: &Value,
    reference: &Value,
    operation: &str,
) -> Result<(), &'static str> {
    if !matches!(
        record["kind"].as_str(),
        Some("task-request" | "change-request")
    ) {
        return Ok(());
    }
    let step = record["step"].as_u64().unwrap();
    let state = load(app, record).await?;
    validate_live(app, &state, record, Some(reference)).await?;
    bind_projection(app, record, operation, false).await?;
    app.github.ensure_step_label(&app.repository, step).await?;
    let mut targets = vec![record["task"].as_u64().unwrap()];
    if let Some(pr) = record["existing_pr"].as_u64() {
        targets.push(pr);
    }
    for target in targets {
        let state = load(app, record).await?;
        validate_live(app, &state, record, Some(reference)).await?;
        bind_projection(app, record, operation, false).await?;
        let subject = if target == record["task"].as_u64().unwrap() {
            state.issue
        } else {
            app.github.get_pr(&app.repository, target as i64).await?
        };
        if step_sync::current_step(&subject)? != step {
            let mut labels: Vec<_> = subject["labels"]
                .as_array()
                .unwrap()
                .iter()
                .filter_map(|label| label["name"].as_str())
                .filter(|name| !name.starts_with("step-"))
                .map(ToOwned::to_owned)
                .collect();
            labels.push(format!("step-{step}"));
            app.github
                .project_step_labels(&app.repository, target, &labels)
                .await?;
        }
    }
    if let Some(pr) = record["existing_pr"].as_i64() {
        let state = load(app, record).await?;
        validate_live(app, &state, record, Some(reference)).await?;
        bind_projection(app, record, operation, false).await?;
        let live = app.github.get_pr(&app.repository, pr).await?;
        let title = projection_title(record);
        if live["title"] != title {
            app.github
                .project_step_title(&app.repository, pr, &title)
                .await?;
        }
        let live = app.github.get_pr(&app.repository, pr).await?;
        if live["title"] != title || step_sync::current_step(&live)? != step {
            return Err("STEP_DISPLAY_MISMATCH");
        }
    }
    let state = load(app, record).await?;
    validate_live(app, &state, record, Some(reference)).await?;
    if step_sync::current_step(&state.issue)? != step {
        return Err("STEP_DISPLAY_MISMATCH");
    }
    Ok(())
}

fn error(code: &str) -> Value {
    json!({"content":[{"type":"text","text":code}],"isError":true})
}

async fn published_native(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    operation: &str,
    body: &str,
    native: Value,
    outcome: &str,
) -> Result<Value, &'static str> {
    let kind = if record["kind"] == "change-request" {
        "review"
    } else {
        "issue-comment"
    };
    let reference = native_ref(&native, kind, &record["parent"])?;
    source_binding(&app.repository, &native, &reference)?;
    if !trusted_user(&native["user"], &state.publisher)
        || native["body"] != body
        || (kind == "review"
            && (native["state"] != "CHANGES_REQUESTED"
                || native["commit_id"] != record["reviewed_head_sha"]))
    {
        return Err("AUTHORITY_PUBLICATION_VERIFICATION_FAILED");
    }
    // Re-read by native identity; a POST response alone does not prove durability.
    let reread = app
        .github
        .authority_source(
            &app.repository,
            kind,
            record["parent"]["number"].as_u64().unwrap(),
            reference["id"].as_u64().unwrap(),
        )
        .await?;
    source_binding(&app.repository, &reread, &reference)?;
    if !trusted_user(&reread["user"], &state.publisher) || reread["body"] != body {
        return Err("AUTHORITY_PUBLICATION_VERIFICATION_FAILED");
    }
    let url = reread["html_url"]
        .as_str()
        .ok_or("AUTHORITY_PUBLICATION_VERIFICATION_FAILED")?;
    app.store
        .lock()
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
        .authority_published(
            operation,
            reference["id"].as_i64().unwrap(),
            url,
            &app.policy.actor,
        )
        .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    if let Err(code) = project(app, record, &reference, operation).await {
        return Ok(
            json!({"content":[{"type":"text","text":"AUTHORITY_PUBLISHED_METADATA_FAILED"}],"isError":true,
            "structuredContent":{"reference":reference,"native_url":url,"error_code":code}}),
        );
    }
    let mut check_reference = Value::Null;
    if record["kind"] == "change-request" {
        let sha = record["reviewed_head_sha"].as_str().unwrap();
        let check = match app.github.find_check(&app.repository, sha, operation).await? {
            Some(check) => check,
            None => app.github.create_check(&app.repository, &json!({
                "name":app.policy.check_name,"head_sha":sha,"external_id":operation,
                "status":"completed","conclusion":"failure",
                "output":{"title":"Changes requested","summary":"Typed GitHub-native PR Change Request published for this exact head."}
            })).await?,
        };
        if check["name"] != app.policy.check_name
            || check["head_sha"] != sha
            || check["app"]["slug"] != app.policy.slug
            || check["id"].as_i64().is_none_or(|id| id <= 0)
            || !check["html_url"].is_string()
        {
            return Err("CHECK_VERIFICATION_FAILED");
        }
        app.store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .published(
                operation,
                check["id"].as_i64().unwrap(),
                check["html_url"].as_str().unwrap(),
            )
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        check_reference = json!({"id":check["id"],"url":check["html_url"],"head_sha":sha});
    }
    app.store
        .lock()
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
        .authority_complete(operation)
        .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    let fresh = load(app, record).await?;
    let provenance = validate_live(app, &fresh, record, Some(&reference)).await?;
    let (closure, warnings) = closure_policy(fresh.issue["body"].as_str().unwrap());
    Ok(
        json!({"content":[{"type":"text","text":outcome}],"structuredContent":{
        "reference":reference,"native_url":url,"actor":normalized_author(&reread["user"]),"record":record,
        "context_provenance":provenance["context_provenance"],"issue_closure_policy":closure,
        "warnings":warnings,"check":check_reference,"issue_closure_performed":false,"merge_performed":false,
        "pr_lifecycle": if record["kind"] == "change-request" {
            crate::remediation_lifecycle_action(&json!({"action":"REQUEST_CHANGES","pr_number":record["parent"]["number"],
                "expected_head_sha":record["reviewed_head_sha"]}), reference["id"].as_i64())
        } else {Value::Null}}}),
    )
}

pub(crate) async fn publish(app: &RepositoryTarget<'_>, args: &Value) -> Value {
    if !app.enabled {
        return error("RELAY_DISABLED");
    }
    if !app.policy.github_native_authority_enabled {
        return error("GITHUB_NATIVE_AUTHORITY_NOT_ENABLED");
    }
    let record = &args["record"];
    let operation = hash(&format!("task-authority-v1\n{}", render(record)));
    let body = format!(
        "{}\n<!-- jresearchsoftware-task-authority:v1 operation={operation} -->",
        render(record)
    );
    let future = async {
        let state = load(app, record).await?;
        let known = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .known(&operation)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if let Some(known) = &known {
            if known
                .actor_login
                .as_deref()
                .is_some_and(|actor| actor != app.policy.actor)
            {
                return Err("AUTHORITY_ACTOR_UNVERIFIED");
            }
            if let Some(id) = known.native_id {
                let kind = if record["kind"] == "change-request" {
                    "review"
                } else {
                    "issue-comment"
                };
                let native = app
                    .github
                    .authority_source(
                        &app.repository,
                        kind,
                        record["parent"]["number"].as_u64().unwrap(),
                        id as u64,
                    )
                    .await?;
                if known.status == "PUBLISHED" {
                    let reference = native_ref(&native, kind, &record["parent"])?;
                    source_binding(&app.repository, &native, &reference)?;
                    if native["body"] != body || !trusted_user(&native["user"], &state.publisher) {
                        return Err("AUTHORITY_PUBLICATION_VERIFICATION_FAILED");
                    }
                    return Ok(
                        json!({"content":[{"type":"text","text":"DUPLICATE_SUPPRESSED"}],"structuredContent":{"reference":reference,"native_url":known.native_url,"actor":normalized_author(&native["user"]),"merge_performed":false,"issue_closure_performed":false,
                        "pr_lifecycle":if record["kind"] == "change-request" {
                            crate::remediation_lifecycle_action(&json!({"action":"REQUEST_CHANGES","pr_number":record["parent"]["number"],
                                "expected_head_sha":record["reviewed_head_sha"]}), Some(id))
                        } else {Value::Null}}}),
                    );
                }
                return published_native(
                    app,
                    &state,
                    record,
                    &operation,
                    &body,
                    native,
                    "AUTHORITY_RECOVERED",
                )
                .await;
            }
            if known.status == "RESERVED" {
                let natives = if record["kind"] == "change-request" {
                    app.github
                        .authority_reviews(
                            &app.repository,
                            record["parent"]["number"].as_u64().unwrap(),
                        )
                        .await?
                } else if record["parent"]["kind"] == "pull_request" {
                    app.github
                        .authority_comments(
                            &app.repository,
                            record["parent"]["number"].as_u64().unwrap(),
                        )
                        .await?
                } else {
                    state.comments.clone()
                };
                let matches: Vec<_> = natives
                    .iter()
                    .filter(|native| {
                        native["body"] == body && trusted_user(&native["user"], &state.publisher)
                    })
                    .collect();
                if matches.len() != 1 {
                    return Err("AUTHORITY_PUBLICATION_UNCERTAIN");
                }
                return published_native(
                    app,
                    &state,
                    record,
                    &operation,
                    &body,
                    matches[0].clone(),
                    "AUTHORITY_RECOVERED",
                )
                .await;
            }
        }
        validate_live(app, &state, record, None).await?;
        if !app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .reserve(&operation, &hash(&body))
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
        {
            return Err("AUTHORITY_PUBLICATION_UNCERTAIN");
        }
        // Reservation precedes the final source re-read and every non-idempotent POST.
        let final_state = match load(app, record).await {
            Ok(state) => state,
            Err(code) => {
                app.store
                    .lock()
                    .map_err(|_| "INTERNAL_RELAY_ERROR")?
                    .retryable_failure(&operation)
                    .map_err(|_| "INTERNAL_RELAY_ERROR")?;
                return Err(code);
            }
        };
        if let Err(code) = validate_live(app, &final_state, record, None).await {
            app.store
                .lock()
                .map_err(|_| "INTERNAL_RELAY_ERROR")?
                .retryable_failure(&operation)
                .map_err(|_| "INTERNAL_RELAY_ERROR")?;
            return Err(code);
        }
        if matches!(
            record["kind"].as_str(),
            Some("task-request" | "change-request")
        ) {
            if let Err(code) = bind_projection(app, record, &operation, true).await {
                app.store
                    .lock()
                    .map_err(|_| "INTERNAL_RELAY_ERROR")?
                    .retryable_failure(&operation)
                    .map_err(|_| "INTERNAL_RELAY_ERROR")?;
                return Err(code);
            }
        }
        let native = if record["kind"] == "change-request" {
            app.github.create_review(&app.repository, record["parent"]["number"].as_i64().unwrap(),
                &json!({"commit_id":record["reviewed_head_sha"],"body":body,"event":"REQUEST_CHANGES"})).await?
        } else {
            app.github
                .create_authority_comment(
                    &app.repository,
                    record["parent"]["number"].as_u64().unwrap(),
                    &body,
                )
                .await?
        };
        published_native(
            app,
            &final_state,
            record,
            &operation,
            &body,
            native,
            "AUTHORITY_PUBLISHED",
        )
        .await
    };
    let result: Result<Value, &'static str> =
        tokio::time::timeout(std::time::Duration::from_secs(60), future)
            .await
            .unwrap_or(Err("AUTHORITY_PUBLICATION_UNCERTAIN"));
    result.unwrap_or_else(error)
}

pub(crate) async fn approved_continuation(
    app: &RepositoryTarget<'_>,
    issue: &Value,
    pr: &Value,
    approved_head: &Value,
) -> Result<Value, &'static str> {
    if !app.policy.github_native_authority_enabled {
        return Err("GITHUB_NATIVE_AUTHORITY_NOT_ENABLED");
    }
    let hint = json!({"repository":app.repository,"task":issue["number"],"charter_sha256":hash(issue["body"].as_str().ok_or("ISSUE_NOT_ADMITTED")?),"existing_pr":pr["number"]});
    let state = load(app, &hint).await?;
    let records = execution_records(app, &state, &hint).await?;
    let (reference, request) = current(&records)?.ok_or("AUTHORITY_REQUEST_MISSING")?;
    if !belongs(request, &hint)
        || request["branch"] != pr["head"]["ref"]
        || step_sync::current_step(&state.issue)? != request["step"].as_u64().unwrap()
        || step_sync::current_step(pr)? != request["step"].as_u64().unwrap()
    {
        return Err("AUTHORITY_APPROVAL_STALE_REQUEST");
    }
    let mut exact_outcomes = Vec::new();
    let mut outcomes = state.comments.clone();
    outcomes.extend(
        app.github
            .authority_comments(&app.repository, pr["number"].as_u64().unwrap())
            .await?,
    );
    if outcomes.len() > definition()["max_native_records"].as_u64().unwrap() as usize {
        return Err("AUTHORITY_SOURCE_TRUNCATED");
    }
    for native in &outcomes {
        if !trusted_user(&native["user"], &state.writer) {
            continue;
        }
        let Some(outcome) = parse(native["body"].as_str().ok_or("AUTHORITY_SOURCE_INVALID")?)?
        else {
            continue;
        };
        if outcome["kind"] == "outcome"
            && belongs(&outcome, &hint)
            && outcome["request"] == *reference
            && outcome["status"] == "implemented"
            && outcome["result"]["kind"] == "git"
            && outcome["result"]["revision"] == *approved_head
        {
            let source = native_ref(native, "issue-comment", &outcome["parent"])?;
            source_binding(&app.repository, native, &source)?;
            trusted_record(app, &state, &hint, &source, true).await?;
            exact_outcomes.push(source);
        }
    }
    if exact_outcomes.len() != 1 {
        return Err("AUTHORITY_EXACT_OUTCOME_REQUIRED");
    }
    let continuation = request
        .get("continuation")
        .cloned()
        .unwrap_or(json!({"hold":false,"task_complete":false,"next":null}));
    Ok(json!({"request":reference,"outcome":exact_outcomes[0],"continuation":continuation}))
}
