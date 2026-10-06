//! Deterministic projection of this operation's already published native CR.
//! No externally selectable Issue, Step, labels or title enters this boundary.
use crate::*;

const MAX_STEP: u64 = 9_007_199_254_740_991;
const TITLE_LIMIT: usize = 56; // controller/src/run-name.mjs: 80 - validation prefix

pub(crate) fn current_step(subject: &Value) -> Result<u64, &'static str> {
    let labels = subject["labels"].as_array().ok_or("STEP_LABEL_MISSING")?;
    let names: Vec<&str> = labels
        .iter()
        .map(|l| l["name"].as_str().ok_or("STEP_LABEL_INVALID"))
        .collect::<Result<_, _>>()?;
    let steps: Vec<_> = names
        .into_iter()
        .filter(|s| s.to_ascii_lowercase().starts_with("step"))
        .collect();
    if steps.is_empty() {
        return Err("STEP_LABEL_MISSING");
    }
    if steps.len() != 1 {
        return Err("STEP_LABEL_MULTIPLE");
    }
    let step = steps[0]
        .strip_prefix("step-")
        .and_then(|s| s.parse::<u64>().ok())
        .filter(|s| *s > 0 && *s <= MAX_STEP)
        .ok_or("STEP_LABEL_INVALID")?;
    if steps[0] != format!("step-{step}") {
        return Err("STEP_LABEL_INVALID");
    }
    Ok(step)
}

pub(crate) fn linked_issue(pr: &Value) -> Result<u64, &'static str> {
    // Same recognized link vocabulary as controller/src/live-authority.mjs.
    let body = pr["body"].as_str().ok_or("CANONICAL_ISSUE_AMBIGUOUS")?;
    let lower = body.to_ascii_lowercase();
    let word = |c: char| c.is_ascii_alphanumeric() || c == '_';
    // Match JavaScript's ASCII word boundaries and whitespace vocabulary.
    let whitespace = |c: char| {
        matches!(
            c,
            '\t' | '\n'
                | '\u{000b}'
                | '\u{000c}'
                | '\r'
                | ' '
                | '\u{00a0}'
                | '\u{1680}'
                | '\u{2000}'
                ..='\u{200a}'
                    | '\u{2028}'
                    | '\u{2029}'
                    | '\u{202f}'
                    | '\u{205f}'
                    | '\u{3000}'
                    | '\u{feff}'
        )
    };
    let after_space = |text: &str| -> Option<usize> {
        let count = text
            .chars()
            .take_while(|c| whitespace(*c))
            .map(char::len_utf8)
            .sum();
        (count > 0).then_some(count)
    };
    let mut ids = Vec::new();
    for (at, _) in body.char_indices() {
        if at > 0 && body[..at].chars().next_back().is_some_and(word) {
            continue;
        }
        let suffix = &lower[at..];
        let Some(keyword) = ["closes", "fixes", "resolves", "related"]
            .into_iter()
            .find(|key| suffix.starts_with(key))
        else {
            continue;
        };
        let mut rest = &suffix[keyword.len()..];
        let Some(count) = after_space(rest) else {
            continue;
        };
        rest = &rest[count..];
        if keyword == "related" {
            let Some(after_to) = rest.strip_prefix("to") else {
                continue;
            };
            let Some(count) = after_space(after_to) else {
                continue;
            };
            rest = &after_to[count..];
        }
        let Some(value) = rest.strip_prefix('#') else {
            continue;
        };
        let count = value.bytes().take_while(u8::is_ascii_digit).count();
        if count == 0 || value.starts_with('0') || value[count..].chars().next().is_some_and(word) {
            continue;
        }
        if let Some(id) = value[..count]
            .parse::<u64>()
            .ok()
            .filter(|n| *n > 0 && *n <= MAX_STEP)
        {
            ids.push(id);
        }
    }
    ids.sort_unstable();
    ids.dedup();
    if ids.len() != 1 {
        return Err("CANONICAL_ISSUE_AMBIGUOUS");
    }
    Ok(ids[0])
}

fn hash(value: &Value) -> String {
    format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(value).unwrap_or_default())
    )
}

fn authority_binding(
    app: &App,
    pr: &Value,
    issue: &Value,
    next: u64,
) -> Result<Value, &'static str> {
    let issue_number = linked_issue(pr)?;
    if issue["body"].as_str().is_some_and(|body| {
        body.lines().any(|line| {
            line.trim_start_matches(|ch: char| ch.is_whitespace() || ch == '-' || ch == '*')
                .to_ascii_lowercase()
                .starts_with("authority model")
        })
    }) {
        return Err("TYPED_CHANGE_REQUEST_REQUIRED");
    }
    if issue["number"].as_u64() != Some(issue_number)
        || issue["state"] != "open"
        || issue.get("pull_request").is_some()
        || issue.pointer("/user/login").and_then(Value::as_str) != Some(app.policy.owner.as_str())
        || issue.pointer("/user/type").and_then(Value::as_str) != Some("User")
        || !issue["body"].is_string()
        || !pr.pointer("/head/ref").is_some_and(Value::is_string)
    {
        return Err("ISSUE_NOT_ADMITTED");
    }
    Ok(
        json!({"issue":issue_number,"step":next,"issue_authority":hash(&json!([issue["body"],issue["user"]])),
        "pr_authority":hash(&json!([pr["body"],pr["head"]["ref"],pr["base"]["ref"],pr["base"]["repo"]["full_name"]]))}),
    )
}

fn binding(
    app: &App,
    pr: &Value,
    issue: &Value,
    next: u64,
    initial_title: &str,
) -> Result<Value, &'static str> {
    let mut value = authority_binding(app, pr, issue, next)?;
    value["initial_pr_title"] = json!(initial_title);
    Ok(value)
}

pub(crate) fn projection_title(issue: u64, arguments: &Value) -> Result<String, &'static str> {
    let cr = &arguments["change_request"];
    let step = cr["step"].as_u64().ok_or("CHANGE_REQUEST_STEP_INVALID")?;
    let id = cr["change_request_id"]
        .as_str()
        .ok_or("CHANGE_REQUEST_STEP_INVALID")?;
    let thread = cr["remediation_thread_title"]
        .as_str()
        .ok_or("STEP_DISPLAY_MISMATCH")?;
    let text = thread.split_whitespace().collect::<Vec<_>>().join(" ");
    // Display identity comes from the linked Issue and structured Step. Reuse
    // only the descriptive tail, never identity from historical title prose.
    let tail = if text.starts_with("Task ") {
        text.find("Step ")
            .and_then(|at| {
                let rest = &text[at + 5..];
                let count = rest.bytes().take_while(u8::is_ascii_digit).count();
                (count > 0).then(|| {
                    rest[count..]
                        .trim_start_matches(|c: char| c.is_whitespace() || "-–—:·|/".contains(c))
                })
            })
            .unwrap_or(&text)
    } else {
        &text
    };
    let tail = tail
        .strip_prefix(id)
        .map(|s| s.trim_start_matches(|c: char| c.is_whitespace() || "-–—:·|/".contains(c)))
        .unwrap_or(tail);
    let identity = format!("Task {issue} · Step {step}");
    if identity.chars().count() >= TITLE_LIMIT {
        return Err("LAUNCH_METADATA_TOO_LONG");
    }
    let full = format!("{identity} · {id} · {tail}");
    if full.chars().count() <= TITLE_LIMIT {
        return Ok(full);
    }
    Ok(format!(
        "{}…",
        full.chars().take(TITLE_LIMIT - 1).collect::<String>()
    ))
}

async fn state(app: &App, args: &Value) -> Result<(Value, Value), &'static str> {
    let pr = app
        .github
        .get_pr(&app.repository, args["pr_number"].as_i64().unwrap())
        .await?;
    if let Some(code) = target_binding_rejection(&app.policy, &pr, args)
        .or_else(|| publication_rejection(&pr, &args["expected_head_sha"]))
    {
        return Err(code);
    }
    let issue = app
        .github
        .get_issue(&app.repository, linked_issue(&pr)?)
        .await?;
    Ok((pr, issue))
}

fn validate_metadata(
    pr: &Value,
    issue: &Value,
    next: u64,
    repair: bool,
) -> Result<(), &'static str> {
    let previous = next
        .checked_sub(1)
        .filter(|n| *n > 0)
        .ok_or("CHANGE_REQUEST_STEP_INVALID")?;
    for subject in [pr, issue] {
        let current = current_step(subject)?;
        if current != previous && !(repair && current == next) {
            return Err("STEP_LABEL_MISMATCH");
        }
    }
    let issue_number = linked_issue(pr)?;
    let title = pr["title"].as_str().ok_or("STEP_DISPLAY_MISMATCH")?;
    if ![previous, next]
        .iter()
        .filter(|s| repair || **s == previous)
        .any(|s| {
            let prefix = format!("Task {issue_number} · Step {s}");
            title == prefix || title.starts_with(&format!("{prefix} · "))
        })
    {
        return Err("STEP_DISPLAY_MISMATCH");
    }
    Ok(())
}

fn save_binding(app: &App, operation: &str, fresh: &Value) -> Result<(), &'static str> {
    let store = app.store.lock().map_err(|_| "INTERNAL_RELAY_ERROR")?;
    let prior = store
        .step_binding(operation)
        .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    if let Some(prior) = prior {
        let prior = serde_json::from_str::<Value>(&prior).map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if !prior["initial_pr_title"].is_string() {
            return Err("LEGACY_STEP_BINDING_REQUIRED");
        }
        if prior != *fresh {
            return Err("AUTHORITY_CHANGED");
        }
    } else {
        store
            .bind_step(operation, &fresh.to_string())
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    }
    Ok(())
}

pub(crate) async fn prepare(app: &App, operation: &str, args: &Value) -> Result<(), &'static str> {
    if args["action"] != "REQUEST_CHANGES" {
        return Ok(());
    }
    let next = args["change_request"]["step"]
        .as_u64()
        .ok_or("CHANGE_REQUEST_STEP_INVALID")?;
    let (pr, issue) = state(app, args).await?;
    validate_metadata(&pr, &issue, next, false)?;
    projection_title(linked_issue(&pr)?, args)?;
    save_binding(
        app,
        operation,
        &binding(app, &pr, &issue, next, pr["title"].as_str().unwrap())?,
    )
}

async fn verified_state(
    app: &App,
    operation: &str,
    review_id: i64,
    args: &Value,
) -> Result<(Value, Value), &'static str> {
    let (pr, issue) = state(app, args).await?;
    let review = app
        .github
        .decisive_review(
            &app.repository,
            args["pr_number"].as_i64().unwrap(),
            &app.policy.actor,
        )
        .await?
        .ok_or("CURRENT_CHANGE_REQUEST_MISSING")?;
    if review["id"].as_i64() != Some(review_id)
        || review["commit_id"] != args["expected_head_sha"]
        || review["state"] != "CHANGES_REQUESTED"
        || review["body"].as_str()
            != Some(native_review_body(&app.policy.validation_names, args, operation).as_str())
    {
        return Err("AUTHORITY_CHANGED");
    }
    let next = args["change_request"]["step"].as_u64().unwrap();
    validate_metadata(&pr, &issue, next, true)?;
    let anchor = app
        .store
        .lock()
        .map_err(|_| "INTERNAL_RELAY_ERROR")?
        .step_binding(operation)
        .map_err(|_| "INTERNAL_RELAY_ERROR")?;
    let title = projection_title(linked_issue(&pr)?, args)?;
    let authority = authority_binding(app, &pr, &issue, next)?;
    if let Some(prior_text) = anchor.as_ref() {
        let mut prior =
            serde_json::from_str::<Value>(prior_text).map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if let Some(initial_title) = prior["initial_pr_title"].as_str() {
            if pr["title"] != initial_title && pr["title"] != title {
                return Err("AUTHORITY_CHANGED");
            }
            save_binding(
                app,
                operation,
                &binding(app, &pr, &issue, next, initial_title)?,
            )?;
            return Ok((pr, issue));
        }
        // Older anchors bind Issue/PR authority but do not retain the exact
        // initial title. Never guess it from a partially transported projection.
        if prior != authority {
            return Err("AUTHORITY_CHANGED");
        }
        if current_step(&pr)? != next || current_step(&issue)? != next || pr["title"] != title {
            return Err("LEGACY_STEP_BINDING_REQUIRED");
        }
        prior["initial_pr_title"] = json!(title);
        let upgraded = app
            .store
            .lock()
            .map_err(|_| "INTERNAL_RELAY_ERROR")?
            .upgrade_step_binding(operation, prior_text, &prior.to_string())
            .map_err(|_| "INTERNAL_RELAY_ERROR")?;
        if !upgraded {
            return Err("INTERNAL_RELAY_ERROR");
        }
        return Ok((pr, issue));
    }
    // Historical publication records lack the pre-mutation Issue authority.
    // Adopt an already complete projection only; mixed-version partial state
    // needs explicit owner legacy reconciliation before this exact replay.
    if current_step(&pr)? != next || current_step(&issue)? != next || pr["title"] != title {
        return Err("LEGACY_STEP_BINDING_REQUIRED");
    }
    save_binding(app, operation, &binding(app, &pr, &issue, next, &title)?)?;
    Ok((pr, issue))
}

pub(crate) async fn synchronize(
    app: &App,
    operation: &str,
    review_id: i64,
    args: &Value,
) -> Result<(), &'static str> {
    if args["action"] != "REQUEST_CHANGES" {
        return Ok(());
    }
    let (pr, _) = verified_state(app, operation, review_id, args).await?;
    let next = args["change_request"]["step"].as_u64().unwrap();
    let issue_number = linked_issue(&pr)?;
    let title = projection_title(issue_number, args)?;
    app.github.ensure_step_label(&app.repository, next).await?;
    for is_pr in [false, true] {
        let (pr, issue) = verified_state(app, operation, review_id, args).await?;
        let subject = if is_pr { &pr } else { &issue };
        if current_step(subject)? != next {
            let mut labels: Vec<String> = subject["labels"]
                .as_array()
                .unwrap()
                .iter()
                .filter_map(|l| l["name"].as_str())
                .filter(|s| *s != format!("step-{}", next - 1))
                .map(ToOwned::to_owned)
                .collect();
            labels.push(format!("step-{next}"));
            app.github
                .project_step_labels(
                    &app.repository,
                    if is_pr {
                        args["pr_number"].as_u64().unwrap()
                    } else {
                        issue_number
                    },
                    &labels,
                )
                .await?;
        }
    }
    let (before, _) = verified_state(app, operation, review_id, args).await?;
    if before["title"] != title {
        app.github
            .project_step_title(&app.repository, args["pr_number"].as_i64().unwrap(), &title)
            .await?;
    }
    let (pr, issue) = verified_state(app, operation, review_id, args).await?;
    if current_step(&pr)? != next || current_step(&issue)? != next || pr["title"] != title {
        return Err("STEP_DISPLAY_MISMATCH");
    }
    Ok(())
}
