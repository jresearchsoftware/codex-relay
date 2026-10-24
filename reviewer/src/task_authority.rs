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

fn v4_definition() -> &'static Value {
    static SCHEMA: OnceLock<Value> = OnceLock::new();
    SCHEMA.get_or_init(|| {
        serde_json::from_str(include_str!("../../contracts/src/github-authority-v4.json"))
            .expect("source-controlled v4 authority schema")
    })
}

fn authority_digest(authority: &Value) -> String {
    hash(&serde_json::to_string_pretty(&json!({"charter":authority["charter"],"decisions":authority["decisions"],
        "change_request":authority["change_request"],"compatibility_request":authority["compatibility_request"]})).unwrap())
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
    let schema = if record["schema_version"] == "4.0" {
        v4_definition()
    } else {
        definition()
    };
    if !schema["input_schemas"]
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
    if kind == "change-request" && record["schema_version"] == "3.0" {
        if record["parent"]["kind"] != "pull_request"
            || record["existing_pr"] != record["parent"]["number"]
            || record["starting_head"] != record["reviewed_head_sha"]
            || !record["supersedes"].is_object()
        {
            return Err("CHANGE_REQUEST_BINDING_INVALID");
        }
    } else if !matches!(kind, "outcome" | "decision" | "change-request")
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
    if matches!(kind, "task-request" | "change-request") && record["schema_version"] == "3.0" {
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
    if record["schema_version"] == "4.0" {
        if kind == "decision"
            && record["parent"]["kind"] != "issue"
            && record["amendments"].get("issue_closure_policy").is_some()
        {
            return Err("AUTHORITY_DECISION_SCOPE_MISMATCH");
        }
        if kind == "change-request"
            && (record["parent"]["kind"] != "pull_request"
                || !record["branch"].is_string()
                || !record["base_sha"].is_string())
        {
            return Err("AUTHORITY_CR_BINDING_INVALID");
        }
        if let Some(authority) = record.get("authority") {
            if authority["charter"]["kind"] != "issue-body"
                || authority["charter"]["parent"]["kind"] != "issue"
                || authority["charter"]["parent"]["number"] != record["task"]
                || authority["charter"]["sha256"] != record["charter_sha256"]
                || authority["sha256"] != authority_digest(authority)
            {
                return Err("AUTHORITY_SOURCE_MISMATCH");
            }
        }
        if let Some(admission) = record.get("admission") {
            if record["step"] != admission["step"]
                || (kind == "outcome" && record["attempt"] != admission["attempt"])
            {
                return Err("AUTHORITY_ADMISSION_MISMATCH");
            }
        }
        if let Some(drift) = record.get("authority_drift") {
            let current = &drift["current_authority"];
            let fields = drift["changed_fields"]
                .as_array()
                .ok_or("AUTHORITY_SOURCE_MISMATCH")?;
            let gaps = drift["comparison_gaps"].as_array();
            if current["sha256"] != authority_digest(current)
                || ["charter", "change_request", "compatibility_request"]
                    .iter()
                    .any(|key| current[*key] != record["authority"][*key])
                || fields
                    .windows(2)
                    .any(|pair| pair[0].as_str() >= pair[1].as_str())
                || gaps.is_some_and(|gaps| {
                    gaps.windows(2)
                        .any(|pair| pair[0].as_str() >= pair[1].as_str())
                        || gaps.iter().any(|field| fields.contains(field))
                })
                || drift["review_required"]
                    != (!fields.is_empty() || gaps.is_some_and(|gaps| !gaps.is_empty()))
            {
                return Err("AUTHORITY_SOURCE_MISMATCH");
            }
        }
    }
    Ok(())
}

pub(crate) fn render_legacy(record: &Value) -> String {
    // serde_json's default map uses sorted keys, matching the Node canonicalizer.
    format!(
        "## Relay {}\n\nAuthority model: github-native-v1\n\n```relay-authority\n{}\n```\n",
        definition()["record_titles"][record["kind"].as_str().unwrap()]
            .as_str()
            .unwrap(),
        serde_json::to_string_pretty(record).expect("validated record")
    )
}

pub(crate) fn render(record: &Value) -> String {
    publication_rendering::render(
        record,
        definition()["record_titles"][record["kind"].as_str().unwrap()]
            .as_str()
            .unwrap(),
        &serde_json::to_string_pretty(record).unwrap(),
    )
}
pub(crate) fn parse(body: &str) -> Result<Option<Value>, &'static str> {
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
        || body.lines().any(|line| {
            line.starts_with("```reviewer-executable-cr")
                || line.starts_with("```yaml")
                || line.starts_with("```yml")
        })
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
    let mut variants: Vec<_> = [
        "decision",
        "task-request",
        "change-request",
        "task-approval",
        "task-review",
    ]
    .iter()
    .filter_map(|kind| definition()["input_schemas"].get(kind).cloned())
    .collect();
    variants.extend(
        ["decision", "change-request", "task-approval", "task-review"]
            .iter()
            .filter_map(|kind| v4_definition()["input_schemas"].get(kind).cloned()),
    );
    json!({"name":"publish_task_authority",
        "description":"Publish trusted Task Decisions, independent exact-head PR Change Requests or no-PR Task acceptance/findings. NEW work requires schema_version 4.0 and the qualified enabled typed capability; never downgrade to a fresh schema-v3 Decision/Request/CR or legacy CR. New Decisions and CRs allocate no Step and need no full public Request. Older schemas remain readable for preserved admitted histories, result acceptance and exact reserved-operation recovery. Re-read native authority; never execute, publish Writer Outcomes, merge or close.",
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
    let body = render(&args["record"]);
    if body.len() > definition()["max_body_bytes"].as_u64().unwrap() as usize
        || body.chars().count() > 65536
    {
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
        ) && payload["schema_version"] == "3.0"
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

fn closure_policy(body: &str) -> (&'static str, Vec<&'static str>) {
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

// Resolve source identities only. Execution/Step allocation belongs to Writer.
async fn effective_authority(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    existing_pr: Option<u64>,
    change_request: &Value,
    select_compatibility_request: bool,
) -> Result<(Value, Value, String, Vec<&'static str>), &'static str> {
    let parent = json!({"kind":"issue","number":record["task"]});
    let mut decisions = list_records(
        app,
        state,
        record,
        &state.comments,
        "issue-comment",
        &parent,
    )?;
    if let Some(pr) = existing_pr {
        let comments = app.github.authority_comments(&app.repository, pr).await?;
        if comments.len() + state.comments.len() > 500 {
            return Err("AUTHORITY_SOURCE_TRUNCATED");
        }
        decisions.extend(list_records(
            app,
            state,
            record,
            &comments,
            "issue-comment",
            &json!({"kind":"pull_request","number":pr}),
        )?);
    }
    decisions.retain(|(_, decision)| decision["kind"] == "decision" && belongs(decision, record));
    let mut superseded = HashSet::new();
    for (reference, decision) in &decisions {
        let predecessor = &decision["supersedes"];
        if predecessor.is_null() {
            continue;
        }
        let (prior, prior_record) = decisions
            .iter()
            .find(|(prior, _)| prior == predecessor)
            .ok_or("AUTHORITY_DECISION_SUPERSESSION_INVALID")?;
        if prior_record["parent"] != decision["parent"]
            || prior["id"].as_u64().unwrap() >= reference["id"].as_u64().unwrap()
            || !superseded.insert(prior.to_string())
        {
            return Err("AUTHORITY_DECISION_SUPERSESSION_INVALID");
        }
    }
    decisions.retain(|(reference, _)| !superseded.contains(&reference.to_string()));
    decisions.sort_by_key(|(reference, _)| reference["id"].as_u64().unwrap());
    let mut amendments = serde_json::Map::new();
    let (original_closure, warnings) = closure_policy(state.issue["body"].as_str().unwrap());
    let mut closure = original_closure.to_string();
    for (_, decision) in &decisions {
        for (key, value) in decision["amendments"].as_object().unwrap() {
            amendments.insert(key.clone(), value.clone());
        }
        if decision["parent"]["kind"] == "issue" {
            if let Some(policy) = decision["amendments"]["issue_closure_policy"].as_str() {
                closure = policy.to_string();
            }
        }
    }
    let compatibility = if select_compatibility_request {
        let mut hint = record.clone();
        hint["existing_pr"] = json!(existing_pr);
        let old = execution_records(app, state, &hint).await?;
        current(&old)?
            .map(|(reference, _)| reference.clone())
            .unwrap_or(Value::Null)
    } else {
        Value::Null
    };
    if !change_request.is_null() {
        let native = read_ref(app, state, record, change_request).await?;
        let payload = trusted_record(app, state, record, change_request, false).await?;
        if change_request["kind"] != "review"
            || payload["kind"] != "change-request"
            || native["commit_id"] != payload["reviewed_head_sha"]
            || !matches!(
                native["state"].as_str(),
                Some("CHANGES_REQUESTED" | "DISMISSED" | "APPROVED")
            )
        {
            return Err("AUTHORITY_REVIEW_INVALID");
        }
        let reviews = app
            .github
            .authority_reviews(
                &app.repository,
                change_request["parent"]["number"].as_u64().unwrap(),
            )
            .await?;
        if reviews.iter().any(|review| {
            trusted_user(&review["user"], &state.publisher)
                && review["id"]
                    .as_u64()
                    .is_some_and(|id| id > change_request["id"].as_u64().unwrap())
                && review["state"] == "CHANGES_REQUESTED"
        }) {
            return Err("AUTHORITY_APPROVAL_STALE_REQUEST");
        }
    }
    let mut authority = json!({"charter":native_ref(&state.issue,"issue-body",&parent)?,"decisions":decisions.iter().map(|(reference,_)| reference.clone()).collect::<Vec<_>>(),
        "change_request":change_request,"compatibility_request":compatibility});
    authority["sha256"] = json!(authority_digest(&authority));
    Ok((authority, Value::Object(amendments), closure, warnings))
}

fn validation_vocabulary(app: &RepositoryTarget<'_>, names: &Value) -> Result<(), &'static str> {
    let allowed = executable_cr::input_schema(&app.policy.validation_names)["properties"]
        ["required_validation"]["items"]["enum"]
        .clone();
    if names.as_array().is_some_and(|names| {
        names
            .iter()
            .any(|name| !allowed.as_array().unwrap().contains(name))
    }) {
        return Err("AUTHORITY_VALIDATION_UNKNOWN");
    }
    Ok(())
}

// Original execution authority remains immutable provenance. Acceptance resolves
// the delivered result against current Task semantics, without rewriting that
// admission or treating a superseded Decision as an execution request.
async fn outcome_authority(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    original: &Value,
    existing_pr: Option<u64>,
    resolution: &Value,
) -> Result<(Value, Value, String, Vec<&'static str>, Value), &'static str> {
    read_ref(app, state, record, &original["charter"]).await?;
    let mut original_amendments = serde_json::Map::new();
    let mut original_closure = closure_policy(state.issue["body"].as_str().unwrap())
        .0
        .to_string();
    for reference in original["decisions"]
        .as_array()
        .ok_or("AUTHORITY_SOURCE_MISMATCH")?
    {
        let decision = trusted_record(app, state, record, reference, false).await?;
        if decision["kind"] != "decision"
            || (decision["parent"]["kind"] == "pull_request"
                && decision["parent"]["number"].as_u64() != existing_pr)
        {
            return Err("AUTHORITY_DECISION_SCOPE_MISMATCH");
        }
        for (key, value) in decision["amendments"].as_object().unwrap() {
            original_amendments.insert(key.clone(), value.clone());
        }
        if decision["parent"]["kind"] == "issue" {
            if let Some(policy) = decision["amendments"]["issue_closure_policy"].as_str() {
                original_closure = policy.to_string();
            }
        }
    }
    let compatibility = if original["compatibility_request"].is_null() {
        Value::Null
    } else {
        trusted_record(
            app,
            state,
            record,
            &original["compatibility_request"],
            false,
        )
        .await?
    };
    let change = if original["change_request"].is_null() {
        Value::Null
    } else {
        trusted_record(app, state, record, &original["change_request"], false).await?
    };
    let (current, amendments, closure, warnings) = effective_authority(
        app,
        state,
        record,
        existing_pr,
        &original["change_request"],
        !original["compatibility_request"].is_null(),
    )
    .await?;
    if current["compatibility_request"] != original["compatibility_request"] {
        return Err("AUTHORITY_APPROVAL_STALE_REQUEST");
    }
    let semantics = |values: &Value, closure: &str| {
        let mut result = json!({"purpose":null,"scope":[],"boundaries":[],
            "validation":null,"model":null,"effort":null,"subagents":null,
            "branch":null,"base_sha":null,"starting_head":null,"existing_pr":null,
            "issue_closure_policy":closure,"continuation":{"hold":false,"next":null}});
        let mut unknown = BTreeSet::from(
            [
                "purpose",
                "validation",
                "model",
                "effort",
                "subagents",
                "branch",
                "base_sha",
                "starting_head",
                "existing_pr",
            ]
            .map(str::to_string),
        );
        if resolution.is_object() {
            result["purpose"] = resolution["purpose"].clone();
            unknown.remove("purpose");
        }
        for source in [
            &resolution["project_defaults"],
            &resolution["starting_state"],
            &compatibility,
            values,
        ] {
            for key in [
                "purpose",
                "scope",
                "boundaries",
                "validation",
                "model",
                "effort",
                "subagents",
                "branch",
                "base_sha",
                "starting_head",
                "existing_pr",
            ] {
                if let Some(value) = source.get(key) {
                    result[key] = value.clone();
                    unknown.remove(key);
                }
            }
        }
        let old = &compatibility["continuation"];
        result["continuation"] = values.get("continuation").cloned().unwrap_or_else(|| json!({"hold":old["hold"]==true,
            "next":if old["next"]["direction"].is_object() {json!({"task":old["next"]["task"],"direction":old["next"]["direction"]})} else {Value::Null}}));
        if !change.is_null() {
            result["purpose"] = change["purpose"].clone();
            result["branch"] = change["branch"].clone();
            result["base_sha"] = change["base_sha"].clone();
            result["starting_head"] = change["reviewed_head_sha"].clone();
            result["existing_pr"] = original["change_request"]["parent"]["number"].clone();
            for key in [
                "purpose",
                "branch",
                "base_sha",
                "starting_head",
                "existing_pr",
            ] {
                unknown.remove(key);
            }
            let overrides = if change["schema_version"] == "4.0" {
                &change["overrides"]
            } else {
                &change
            };
            for key in ["validation", "model", "effort", "subagents"] {
                if let Some(value) = overrides.get(key) {
                    result[key] = value.clone();
                    unknown.remove(key);
                }
            }
            if let Some(extra) = overrides["boundaries"].as_array() {
                let mut boundaries = result["boundaries"].as_array().unwrap().clone();
                for boundary in extra {
                    if !boundaries.contains(boundary) {
                        boundaries.push(boundary.clone());
                    }
                }
                result["boundaries"] = json!(boundaries);
            }
        }
        (result, unknown)
    };
    let (before, before_unknown) =
        semantics(&Value::Object(original_amendments), &original_closure);
    let (after, after_unknown) = semantics(&amendments, &closure);
    let mut changed_fields = Vec::new();
    let mut comparison_gaps = Vec::new();
    for key in before.as_object().unwrap().keys() {
        if before[key] != after[key] || before_unknown.contains(key) != after_unknown.contains(key)
        {
            if before_unknown.contains(key) || after_unknown.contains(key) {
                comparison_gaps.push(key.clone());
            } else {
                changed_fields.push(key.clone());
            }
        }
    }
    let mut drift = json!({"current_authority":current,"review_required":!changed_fields.is_empty() || !comparison_gaps.is_empty(),"changed_fields":changed_fields});
    if !comparison_gaps.is_empty() {
        drift["comparison_gaps"] = json!(comparison_gaps);
    }
    Ok((current, amendments, closure, warnings, drift))
}

async fn validate_v4_live(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    published: Option<&Value>,
) -> Result<Value, &'static str> {
    match record["kind"].as_str().unwrap() {
        "decision" => {
            validation_vocabulary(app, &record["amendments"]["validation"])?;
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
                let prior =
                    trusted_record(app, state, record, &record["supersedes"], false).await?;
                if prior["kind"] != "decision" || prior["parent"] != record["parent"] {
                    return Err("AUTHORITY_DECISION_SUPERSESSION_INVALID");
                }
                let natives = if record["parent"]["kind"] == "issue" {
                    state.comments.clone()
                } else {
                    app.github
                        .authority_comments(
                            &app.repository,
                            record["parent"]["number"].as_u64().unwrap(),
                        )
                        .await?
                };
                let decisions = list_records(
                    app,
                    state,
                    record,
                    &natives,
                    "issue-comment",
                    &record["parent"],
                )?;
                if decisions.iter().any(|(reference, decision)| {
                    published != Some(reference)
                        && decision["kind"] == "decision"
                        && decision["supersedes"] == record["supersedes"]
                }) {
                    return Err("AUTHORITY_DECISION_SUPERSEDED");
                }
            }
        }
        "change-request" => {
            validation_vocabulary(app, &record["overrides"]["validation"])?;
            let pr = app
                .github
                .get_pr(
                    &app.repository,
                    record["parent"]["number"].as_i64().unwrap(),
                )
                .await?;
            let args = json!({"repository":app.repository,"pr_number":record["parent"]["number"],"expected_head_sha":record["reviewed_head_sha"]});
            if target_binding_rejection(&app.policy, &pr, &args).is_some()
                || pr["head"]["ref"] != record["branch"]
                || pr["head"]["sha"] != record["reviewed_head_sha"]
                || (published.is_none() && pr["base"]["sha"] != record["base_sha"])
                || step_sync::linked_issue(&pr)? != record["task"].as_u64().unwrap()
            {
                return Err("AUTHORITY_PR_BINDING_MISMATCH");
            }
            let mut publication_pr = pr.clone();
            if published.is_some() {
                publication_pr["draft"] = json!(false);
            }
            if let Some(code) = publication_rejection(&publication_pr, &record["reviewed_head_sha"])
            {
                return Err(code);
            }
        }
        "task-approval" | "task-review" => {
            let outcome = trusted_record(app, state, record, &record["outcome"], true).await?;
            if record["outcome"]["kind"] != "issue-comment"
                || outcome["kind"] != "outcome"
                || outcome["schema_version"] != "4.0"
                || (record["kind"] == "task-approval" && outcome["status"] != "implemented")
                || outcome["result"] != record["result"]
                || outcome["admission"] != record["admission"]
                || outcome["step"] != record["step"]
            {
                return Err("AUTHORITY_APPROVAL_RESULT_MISMATCH");
            }
            let existing_pr = if outcome["parent"]["kind"] == "pull_request" {
                outcome["parent"]["number"].as_u64()
            } else {
                record["authority"]["change_request"]["parent"]["number"].as_u64()
            };
            if let Some(pr) = existing_pr {
                let pr = app.github.get_pr(&app.repository, pr as i64).await?;
                if record["kind"] == "task-approval"
                    && outcome["result"]["kind"] == "git"
                    && pr["state"] == "open"
                {
                    return Err("AUTHORITY_APPROVAL_PR_REVIEW_REQUIRED");
                }
            }
            outcome_authority(
                app,
                state,
                record,
                &outcome["authority"],
                existing_pr,
                &outcome["authority_resolution"],
            )
            .await?;
            if record["authority"]["change_request"] != outcome["authority"]["change_request"]
                || record["authority"]["compatibility_request"]
                    != outcome["authority"]["compatibility_request"]
            {
                return Err("AUTHORITY_APPROVAL_RESULT_MISMATCH");
            }
            let (_, _, _, _, accepted_drift) = outcome_authority(
                app,
                state,
                record,
                &record["authority"],
                existing_pr,
                &outcome["authority_resolution"],
            )
            .await?;
            if accepted_drift["current_authority"] != record["authority"] {
                return Err("AUTHORITY_APPROVAL_STALE_REQUEST");
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
            let mut outcomes = state.comments.clone();
            if let Some(pr) = existing_pr {
                outcomes.extend(app.github.authority_comments(&app.repository, pr).await?);
            }
            if outcomes.len() > 500 {
                return Err("AUTHORITY_SOURCE_TRUNCATED");
            }
            for native in outcomes {
                if trusted_user(&native["user"], &state.writer)
                    && native["id"]
                        .as_u64()
                        .is_some_and(|id| id > record["outcome"]["id"].as_u64().unwrap())
                {
                    if let Some(later) =
                        parse(native["body"].as_str().ok_or("AUTHORITY_SOURCE_INVALID")?)?
                    {
                        if later["kind"] == "outcome"
                            && belongs(&later, record)
                            && later["schema_version"] == "4.0"
                            && later["step"].as_u64().unwrap() > record["step"].as_u64().unwrap()
                        {
                            return Err("AUTHORITY_APPROVAL_STALE_REQUEST");
                        }
                    }
                }
            }
            if step_sync::current_step(&state.issue)? != record["step"].as_u64().unwrap() {
                return Err("AUTHORITY_STEP_MISMATCH");
            }
        }
        _ => return Err("AUTHORITY_RECORD_INVALID"),
    }
    Ok(json!({}))
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
    if record["schema_version"] == "4.0" {
        validate_v4_live(app, state, record, published).await?;
        return Ok(json!({"context_provenance":context}));
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
            let mut live = app.github.get_pr(&app.repository, pr as i64).await?;
            let args = json!({"repository":app.repository,"pr_number":pr,"expected_head_sha":record["starting_head"]});
            if target_binding_rejection(&app.policy, &live, &args).is_some()
                || live["head"]["ref"] != record["branch"]
                || live["head"]["sha"] != record["starting_head"]
                || step_sync::linked_issue(&live)? != record["task"].as_u64().unwrap()
            {
                return Err("AUTHORITY_PR_BINDING_MISMATCH");
            }
            if published.is_some() && kind == "change-request" {
                live["draft"] = json!(false);
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
    let previous = app
        .store
        .lock()
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
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
    } else {
        // With no original anchor, only an already complete deterministic
        // projection can be adopted. A partial title/label transition cannot
        // reconstruct its original initial title or authorize another write.
        if !prepare {
            let issue = app
                .github
                .get_issue(&app.repository, record["task"].as_u64().unwrap())
                .await?;
            let step = record["step"]
                .as_u64()
                .ok_or("AUTHORITY_PROJECTION_BINDING_MISSING")?;
            if crate::step_sync::current_step(&pr)? != step
                || crate::step_sync::current_step(&issue)? != step
                || pr["title"] != projection_title(record)
            {
                return Err("AUTHORITY_PROJECTION_BINDING_MISSING");
            }
        }
        let initial_title = pr["title"].as_str().ok_or("STEP_DISPLAY_MISMATCH")?;
        app.store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .bind_step(
                operation,
                &json!({"identity":identity,"initial_title":initial_title}).to_string(),
            )
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    }
    Ok(())
}

async fn project(
    app: &RepositoryTarget<'_>,
    record: &Value,
    reference: &Value,
    operation: &str,
) -> Result<(), &'static str> {
    if record["schema_version"] == "4.0" {
        return Ok(());
    }
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

pub(crate) fn error(code: &str) -> Value {
    let mut result = json!({"content":[{"type":"text","text":code}],"isError":true});
    let guidance = match code {
        "MANUAL_PR_TARGET_MISMATCH" => Some("Check result.parent.number against the intended PR and any immutable existing-PR admission. Correct an unreserved input in the same attempt; do not create a replacement PR or Step."),
        "MANUAL_PR_REPOSITORY_MISMATCH" => Some("The target PR must have both head and base in the admitted repository. Check repository and result.parent before resubmitting."),
        "MANUAL_PR_TASK_MISMATCH" => Some("The target PR needs one unambiguous link to the admitted Task, such as Related to #N. Check the intended target and Task link; no PR-body admission digest is required for v4."),
        "MANUAL_PR_BRANCH_MISMATCH" => Some("The target PR head branch must match the admitted branch. Check the intended PR and immutable admission; do not reset or replace the branch."),
        "MANUAL_PR_BASE_MISMATCH" => Some("The target PR must use the configured base branch. Check the intended PR and base before resubmitting."),
        "MANUAL_PR_HEAD_MISMATCH" => Some("Check result.result.revision against the exact published target PR head. Preserve uncertain or already reserved result claims; inspect publication state before any recovery."),
        "CURRENT_PROTOCOL_REQUIRED" => Some("Use publish_task_authority with a schema_version 4.0 Decision or Change Request for new work. Do not create a schema-v3 Decision/Request/CR or legacy CR as a fallback. Preserve the original payload for an already reserved operation."),
        "CURRENT_PROTOCOL_CAPABILITY_REQUIRED" => Some("Stop new authority publication until the paired Reviewer/controller installation is qualified and githubNativeAuthorityEnabled is enabled. Refresh the supported typed capability; do not fall back to schema-v3 or legacy publication."),
        "MANUAL_OUTCOME_CAPABILITY_DISABLED" | "WRITER_CAPABILITY_UNAVAILABLE" => Some("For a new schema-v4 result, stop publication until the qualified owner-connected submit_manual_outcome Writer capability is available. Preserve the admitted result and original operation; do not replace it with an owner-authored result comment or a legacy transport fallback. Already-admitted older attempts retain their exact original qualified transport and bindings."),
        _ => None,
    };
    if let Some(guidance) = guidance {
        result["structuredContent"] = json!({"error_code":code,"guidance":guidance});
    }
    result
}

async fn verify_publication_authority(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    record: &Value,
    operation: &str,
    prepare: bool,
) -> Result<Value, &'static str> {
    if record["schema_version"] != "4.0" || record["kind"] != "change-request" {
        return Ok(Value::Null);
    }
    // New v4 publication never infers an old execution chain. A recorded
    // publication binding retains its original compatibility policy on recovery.
    let select_compatibility_request = app
        .store
        .lock()
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
        .authority_binding(operation)
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
        .map(|binding| serde_json::from_str::<Value>(&binding).map_err(|_| "INTERNAL_RELAY_ERROR"))
        .transpose()?
        .is_some_and(|binding| !binding["compatibility_request"].is_null());
    let authority = effective_authority(
        app,
        state,
        record,
        record["parent"]["number"].as_u64(),
        &Value::Null,
        select_compatibility_request,
    )
    .await?
    .0;
    let store = app.store.lock().map_err(|_| "INTERNAL_RELAY_ERROR")?;
    if let Some(body) = store
        .publication_body(operation)
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
    {
        let prefix = "<!-- jresearchsoftware-reviewer-task-binding:v1 authority_sha256=";
        if body.contains(prefix)
            && !body.ends_with(&format!(
                "{prefix}{} -->",
                authority["sha256"].as_str().ok_or("AUTHORITY_CHANGED")?
            ))
        {
            return Err("AUTHORITY_CHANGED");
        }
    }
    if let Some(binding) = store
        .authority_binding(operation)
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
    {
        let original: Value = serde_json::from_str(&binding).map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if original != authority {
            return Err("AUTHORITY_CHANGED");
        }
    } else if prepare {
        store
            .bind_authority(operation, &authority.to_string())
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    }
    // Pre-upgrade reservations retain their original source/body checks. Never
    // fabricate an earlier effective-authority observation for a historical row.
    Ok(authority)
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
    if !trusted_user(&reread["user"], &state.publisher)
        || reread["body"] != body
        || (kind == "review"
            && (reread["state"] != "CHANGES_REQUESTED"
                || reread["commit_id"] != record["reviewed_head_sha"]))
    {
        return Err("AUTHORITY_PUBLICATION_VERIFICATION_FAILED");
    }
    // Resume only the original native operation after rechecking authority;
    // neither a retained native ID nor metadata already projected is authority.
    let fresh = load(app, record).await?;
    validate_live(app, &fresh, record, Some(&reference)).await?;
    verify_publication_authority(app, &fresh, record, operation, false).await?;
    if kind == "review" {
        let reviews = app
            .github
            .authority_reviews(
                &app.repository,
                record["parent"]["number"].as_u64().unwrap(),
            )
            .await?;
        let marker = format!("jresearchsoftware-task-authority:v1 operation={operation}");
        let matches: Vec<_> = reviews
            .iter()
            .filter(|review| {
                review["body"]
                    .as_str()
                    .is_some_and(|body| body.contains(&marker))
            })
            .collect();
        if matches.len() != 1 || matches[0]["id"] != reference["id"] {
            return Err("AUTHORITY_PUBLICATION_UNCERTAIN");
        }
        if reviews.iter().any(|review| {
            trusted_user(&review["user"], &fresh.publisher)
                && review["id"]
                    .as_u64()
                    .is_some_and(|id| id > reference["id"].as_u64().unwrap())
                && matches!(
                    review["state"].as_str(),
                    Some("APPROVED" | "CHANGES_REQUESTED")
                )
        }) {
            return Err("AUTHORITY_APPROVAL_STALE_REQUEST");
        }
    }
    let url = reread["html_url"]
        .as_str()
        .ok_or("AUTHORITY_PUBLICATION_VERIFICATION_FAILED")?;
    if let Err(code) = project(app, record, &reference, operation).await {
        return Ok(
            json!({"content":[{"type":"text","text":"AUTHORITY_PUBLISHED_METADATA_FAILED"}],"isError":true,
            "structuredContent":{"reference":reference,"native_url":url,"error_code":code}}),
        );
    }
    let mut check_reference = Value::Null;
    let mut check_warnings = Vec::new();
    if record["kind"] == "change-request" {
        let sha = record["reviewed_head_sha"].as_str().unwrap();
        let payload = json!({"name":app.policy.check_name,"head_sha":sha,"external_id":operation,
            "status":"completed","conclusion":"failure",
            "output":{"title":"Changes requested","summary":"Typed GitHub-native PR Change Request published for this exact head."}});
        let original_binding = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .authority_binding(operation)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        let allow_send = record["schema_version"] != "4.0"
            || original_binding.is_some()
            || body.contains("<!-- jresearchsoftware-reviewer-task-binding:v1 authority_sha256=");
        let evidence =
            match crate::publication::ensure_check(app, operation, &payload, allow_send).await {
                Ok(evidence) => evidence,
                Err(failure) => {
                    let mut result = failure.result(operation);
                    result["structuredContent"]["reference"] = reference;
                    result["structuredContent"]["native_url"] = json!(url);
                    return Ok(result);
                }
            };
        check_warnings = evidence.warnings;
        let check = evidence.check;
        check_reference = json!({"id":check["id"],"url":check["html_url"],"head_sha":sha});
    }
    let fresh = load(app, record).await?;
    let provenance = validate_live(app, &fresh, record, Some(&reference)).await?;
    verify_publication_authority(app, &fresh, record, operation, false).await?;
    let (mut closure, mut warnings) = {
        let (closure, warnings) = closure_policy(fresh.issue["body"].as_str().unwrap());
        (closure.to_string(), warnings)
    };
    warnings.extend(check_warnings);
    let mut acceptance = Value::Null;
    if record["schema_version"] == "4.0"
        && matches!(
            record["kind"].as_str(),
            Some("task-approval" | "task-review")
        )
    {
        let delivered = trusted_record(app, &fresh, record, &record["outcome"], true).await?;
        let existing_pr = if delivered["parent"]["kind"] == "pull_request" {
            delivered["parent"]["number"].as_u64()
        } else {
            delivered["authority"]["change_request"]["parent"]["number"].as_u64()
        };
        let (_, _, _, _, drift) = outcome_authority(
            app,
            &fresh,
            record,
            &delivered["authority"],
            existing_pr,
            &delivered["authority_resolution"],
        )
        .await?;
        acceptance = json!({"original_authority":delivered["authority"],"authority":record["authority"],"authority_drift":drift,"admission":delivered["admission"],"outcome":record["outcome"]});
    }
    if record["schema_version"] == "4.0" {
        let existing_pr = if record["parent"]["kind"] == "pull_request" {
            record["parent"]["number"].as_u64()
        } else {
            None
        };
        closure = effective_authority(app, &fresh, record, existing_pr, &Value::Null, false)
            .await?
            .2;
    }
    Ok(
        json!({"content":[{"type":"text","text":outcome}],"structuredContent":{
        "reference":reference,"native_url":url,"actor":normalized_author(&reread["user"]),"record":record,
        "context_provenance":provenance["context_provenance"],"issue_closure_policy":closure,
        "task_acceptance":acceptance,
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
        return error("CURRENT_PROTOCOL_CAPABILITY_REQUIRED");
    }
    let record = &args["record"];
    // Keep the original canonical operation identity through renderer upgrades.
    let operation = hash(&format!("task-authority-v1\n{}", render_legacy(record)));
    let current_body = format!(
        "{}\n<!-- jresearchsoftware-task-authority:v1 operation={operation} -->",
        render(record)
    );
    let legacy_body = format!(
        "{}\n<!-- jresearchsoftware-task-authority:v1 operation={operation} -->",
        render_legacy(record)
    );
    let future = async {
        let known = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .known(&operation)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        let state = load(app, record).await?;
        let original_authority =
            verify_publication_authority(app, &state, record, &operation, false).await?;
        let unmarked_body = current_body.clone();
        let mut current_body = current_body.clone();
        if !original_authority.is_null() {
            current_body.push_str(&format!(
                "\n<!-- jresearchsoftware-reviewer-task-binding:v1 authority_sha256={} -->",
                original_authority["sha256"]
                    .as_str()
                    .ok_or("AUTHORITY_CHANGED")?
            ));
        }
        let retained = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .publication_body(&operation)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        let body = retained.unwrap_or_else(|| {
            if known.is_some() {
                legacy_body.clone()
            } else {
                current_body.clone()
            }
        });
        // Always observe GitHub first: stale or absent local receipts cannot
        // negate an independently verified publication, including old schemas.
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
        let marker = format!("jresearchsoftware-task-authority:v1 operation={operation}");
        let matches: Vec<_> = natives
            .iter()
            .filter(|native| {
                native["body"]
                    .as_str()
                    .is_some_and(|body| body.contains(&marker))
            })
            .collect();
        if matches.len() > 1 {
            return Err("AUTHORITY_PUBLICATION_UNCERTAIN");
        }
        if let Some(native) = matches.first() {
            let original = native["body"]
                .as_str()
                .ok_or("AUTHORITY_PUBLICATION_VERIFICATION_FAILED")?;
            if original != body
                && !(known.is_none() && (original == legacy_body || original == unmarked_body))
            {
                return Err("AUTHORITY_PUBLICATION_VERIFICATION_FAILED");
            }
            let (_, frozen) = app
                .store
                .lock()
                .map_err(|_| "INTERNAL_RELAY_ERROR")?
                .recover_publication(&operation, original, &legacy_body)
                .map_err(|_| "INTERNAL_RELAY_ERROR")?;
            if frozen != original {
                return Err("AUTHORITY_PUBLICATION_VERIFICATION_FAILED");
            }
            return published_native(
                app,
                &state,
                record,
                &operation,
                original,
                (*native).clone(),
                "AUTHORITY_RECOVERED",
            )
            .await;
        }
        if known.is_none()
            && record["schema_version"] == "3.0"
            && matches!(
                record["kind"].as_str(),
                Some("decision" | "task-request" | "change-request")
            )
        {
            return Err("CURRENT_PROTOCOL_REQUIRED");
        }
        validate_live(app, &state, record, None).await?;
        let (reserved, body) = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .reserve_publication(&operation, &current_body, &legacy_body)
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if !reserved {
            return Err("AUTHORITY_PUBLICATION_UNCERTAIN");
        }
        let before_post = async {
            verify_publication_authority(app, &state, record, &operation, true).await?;
            let final_state = load(app, record).await?;
            validate_live(app, &final_state, record, None).await?;
            verify_publication_authority(app, &final_state, record, &operation, false).await?;
            if record["schema_version"] == "3.0"
                && matches!(
                    record["kind"].as_str(),
                    Some("task-request" | "change-request")
                )
            {
                bind_projection(app, record, &operation, true).await?;
            }
            Ok::<_, &'static str>(final_state)
        }
        .await;
        let final_state = match before_post {
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
        let prepared = if record["kind"] == "change-request" {
            app.github.prepare_review(&app.repository, record["parent"]["number"].as_i64().unwrap(),
                &json!({"commit_id":record["reviewed_head_sha"],"body":body,"event":"REQUEST_CHANGES"})).await
        } else {
            app.github
                .prepare_authority_comment(
                    &app.repository,
                    record["parent"]["number"].as_u64().unwrap(),
                    &body,
                )
                .await
        };
        let mutation = match prepared {
            Ok(prepared) => app.github.send_mutation(prepared).await,
            Err(failure) => Err(failure),
        };
        match mutation {
            Ok(native) => {
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
            }
            Err(failure) => {
                if failure.safe_to_retry {
                    app.store
                        .lock()
                        .map_err(|_| "INTERNAL_RELAY_ERROR")?
                        .retryable_failure(&operation)
                        .map_err(|_| "INTERNAL_RELAY_ERROR")?;
                }
                let mut result = error(failure.code);
                result["structuredContent"] = json!({"operation":operation,"diagnostics":failure.diagnostics(),
                    "operator_action":"Repeat the identical input to reconcile the original publication; an uncertain decisive POST is never repeated."});
                Ok(result)
            }
        }
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
    v4_only: bool,
) -> Result<Value, &'static str> {
    if !app.policy.github_native_authority_enabled {
        return Err("GITHUB_NATIVE_AUTHORITY_NOT_ENABLED");
    }
    let hint = json!({"repository":app.repository,"task":issue["number"],"charter_sha256":hash(issue["body"].as_str().ok_or("ISSUE_NOT_ADMITTED")?),"existing_pr":pr["number"]});
    let state = load(app, &hint).await?;
    let mut native_outcomes = state.comments.clone();
    native_outcomes.extend(
        app.github
            .authority_comments(&app.repository, pr["number"].as_u64().unwrap())
            .await?,
    );
    if native_outcomes.len() > 500 {
        return Err("AUTHORITY_SOURCE_TRUNCATED");
    }
    let mut v4_outcomes = Vec::new();
    let mut has_v4_outcome = false;
    for native in &native_outcomes {
        if !trusted_user(&native["user"], &state.writer) {
            continue;
        }
        let Some(outcome) = parse(native["body"].as_str().ok_or("AUTHORITY_SOURCE_INVALID")?)?
        else {
            continue;
        };
        if outcome["kind"] == "outcome"
            && outcome["schema_version"] == "4.0"
            && belongs(&outcome, &hint)
        {
            has_v4_outcome = true;
        }
        if outcome["kind"] == "outcome"
            && outcome["schema_version"] == "4.0"
            && belongs(&outcome, &hint)
            && outcome["status"] == "implemented"
            && outcome["result"]["kind"] == "git"
            && outcome["result"]["revision"] == *approved_head
            && outcome["step"].as_u64() == Some(step_sync::current_step(&state.issue)?)
            && outcome["step"].as_u64() == Some(step_sync::current_step(pr)?)
        {
            let reference = native_ref(native, "issue-comment", &outcome["parent"])?;
            source_binding(&app.repository, native, &reference)?;
            trusted_record(app, &state, &hint, &reference, true).await?;
            let (authority, amendments, closure, warnings, drift) = outcome_authority(
                app,
                &state,
                &hint,
                &outcome["authority"],
                pr["number"].as_u64(),
                &outcome["authority_resolution"],
            )
            .await?;
            let compatibility = if authority["compatibility_request"].is_null() {
                Value::Null
            } else {
                trusted_record(
                    app,
                    &state,
                    &hint,
                    &authority["compatibility_request"],
                    false,
                )
                .await?
            };
            let old_continuation = &compatibility["continuation"];
            let continuation=amendments.get("continuation").cloned().unwrap_or_else(|| json!({"hold":old_continuation["hold"]==true,"next": if old_continuation["next"]["direction"].is_object() {json!({"task":old_continuation["next"]["task"],"direction":old_continuation["next"]["direction"]})} else {Value::Null}}));
            v4_outcomes.push(json!({"schema_version":"4.0","authority":authority,"original_authority":outcome["authority"],"authority_drift":drift,"admission":outcome["admission"],"outcome":reference,"continuation":continuation,
                "issue_closure_policy":closure,"warnings":warnings,"completion_conditions":"trusted-owner-canonical-state-required"}));
        }
    }
    if v4_outcomes.len() > 1 {
        return Err("AUTHORITY_EXACT_OUTCOME_REQUIRED");
    }
    if let Some(outcome) = v4_outcomes.pop() {
        return Ok(outcome);
    }
    let records = execution_records(app, &state, &hint).await?;
    if let Some(source) = source_pr_continuation(
        app,
        &state,
        &hint,
        pr,
        approved_head,
        &records,
        &native_outcomes,
    )
    .await?
    {
        return Ok(source);
    }
    if v4_only {
        if has_v4_outcome || records.is_empty() {
            return Err("AUTHORITY_EXACT_OUTCOME_REQUIRED");
        }
        return Ok(Value::Null);
    }
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

// Native source facts are not an execution receipt or owner authorization.
// The owner continuation adapter must independently establish explicit
// standalone permission and exclude an admitted attempt before any effect.
// Missing Writer evidence alone never selects this path.
async fn source_pr_continuation(
    app: &RepositoryTarget<'_>,
    state: &NativeAuthority,
    hint: &Value,
    pr: &Value,
    head: &Value,
    records: &[(Value, Value)],
    outcomes: &[Value],
) -> Result<Option<Value>, &'static str> {
    if !trusted_user(&pr["user"], &state.issue["user"]) {
        return Ok(None);
    }
    if pr["head"]["repo"]["full_name"] != app.repository
        || pr["base"]["repo"]["full_name"] != app.repository
        || pr["head"]["sha"] != *head
        || pr["head"]["ref"].as_str().is_none_or(str::is_empty)
    {
        return Err("AUTHORITY_SOURCE_PR_BINDING_INVALID");
    }
    let body = pr["body"]
        .as_str()
        .ok_or("AUTHORITY_SOURCE_PR_BINDING_INVALID")?;
    if body.contains("<!-- relay:")
        || body.lines().any(|line| {
            let line = line.trim();
            line.starts_with("Execution admission digest:")
                || line.starts_with("Execution request digest:")
                || line.starts_with("Attempt:")
        })
    {
        return Ok(None);
    }
    // An unrelated historical Request is not authority for a fresh v4 source
    // candidate. Retained Requests stay bound to their own PR/branch.
    let selected = current(records)?.filter(|(_, request)| {
        if request["existing_pr"].is_null() {
            request["branch"] == pr["head"]["ref"]
        } else {
            request["existing_pr"] == pr["number"]
        }
    });
    if let Some((_, request)) = selected {
        if request["route"] != "manual"
            || request["branch"] != pr["head"]["ref"]
            || (!request["existing_pr"].is_null() && request["existing_pr"] != pr["number"])
            || step_sync::current_step(&state.issue)? != request["step"].as_u64().unwrap()
            || step_sync::current_step(pr)? != request["step"].as_u64().unwrap()
        {
            return Ok(None);
        }
    }
    for native in outcomes {
        if !trusted_user(&native["user"], &state.writer) {
            continue;
        }
        let body = native["body"].as_str().ok_or("AUTHORITY_SOURCE_INVALID")?;
        if native["issue_url"]
            == format!(
                "https://api.github.com/repos/{}/issues/{}",
                app.repository, pr["number"]
            )
            && (body
                .lines()
                .any(|line| line.starts_with("## Codex Outcome"))
                || body.contains("<!-- relay:"))
        {
            return Ok(None);
        }
        let Some(outcome) = parse(body)? else {
            continue;
        };
        if outcome["kind"] == "outcome"
            && outcome["repository"] == hint["repository"]
            && outcome["task"] == hint["task"]
            && ((outcome["parent"]["kind"] == "pull_request"
                && outcome["parent"]["number"] == pr["number"])
                || outcome["result"]["revision"] == *head
                || selected.is_some_and(|(reference, _)| {
                    outcome["request"] == *reference
                        || outcome["authority"]["compatibility_request"] == *reference
                })
                || (outcome["authority"]["change_request"]["parent"]["kind"] == "pull_request"
                    && outcome["authority"]["change_request"]["parent"]["number"] == pr["number"]))
        {
            // Includes blocked, stale-head and otherwise incomplete admitted
            // results. They retain their original Writer recovery path.
            return Ok(None);
        }
    }
    let mut change = Value::Null;
    // Retain originating CR lineage after APPROVE, just as an admitted Outcome
    // does. A newer applicable CR changes the acceptance digest.
    for native in app
        .github
        .authority_reviews(&app.repository, pr["number"].as_u64().unwrap())
        .await?
    {
        if !trusted_user(&native["user"], &state.publisher)
            || native["state"] != "CHANGES_REQUESTED"
        {
            continue;
        }
        let payload = parse(native["body"].as_str().ok_or("AUTHORITY_SOURCE_INVALID")?)?
            .ok_or("AUTHORITY_REVIEW_INVALID")?;
        if payload["kind"] != "change-request" || !belongs(&payload, hint) {
            return Err("AUTHORITY_REVIEW_INVALID");
        }
        if payload["branch"] != pr["head"]["ref"] {
            return Err("AUTHORITY_SOURCE_PR_BINDING_INVALID");
        }
        if change.is_null() || native["id"].as_u64() > change["id"].as_u64() {
            change = native_ref(&native, "review", &payload["parent"])?;
        }
    }
    let (authority, amendments, closure, warnings) = effective_authority(
        app,
        state,
        hint,
        pr["number"].as_u64(),
        &change,
        selected.is_some(),
    )
    .await?;
    if let Some(branch) = amendments.get("branch") {
        if *branch != pr["head"]["ref"] {
            return Err("AUTHORITY_SOURCE_PR_BINDING_INVALID");
        }
    }
    if let Some(number) = amendments.get("existing_pr") {
        if !number.is_null() && *number != pr["number"] {
            return Err("AUTHORITY_SOURCE_PR_BINDING_INVALID");
        }
    }
    let old = selected
        .map(|(_, request)| &request["continuation"])
        .unwrap_or(&Value::Null);
    let continuation = amendments.get("continuation").cloned().unwrap_or_else(|| {
        json!({
            "hold":old["hold"] == true,
            "next":if old["next"]["direction"].is_object() {
                json!({"task":old["next"]["task"],"direction":old["next"]["direction"]})
            } else { old["next"].clone() }
        })
    });
    Ok(Some(json!({
        "schema_version":"4.0","authority":authority,"original_authority":authority,
        "source_pr":{"repository":app.repository,"number":pr["number"],"head_sha":head,
            "branch":pr["head"]["ref"],"author":{"login":pr["user"]["login"],
                "id":pr["user"]["id"],"type":pr["user"]["type"]}},
        "owner_authorization":"explicit-standalone-required",
        "continuation":continuation,"issue_closure_policy":closure,"warnings":warnings,
        "completion_conditions":"trusted-owner-canonical-state-required"
    })))
}
