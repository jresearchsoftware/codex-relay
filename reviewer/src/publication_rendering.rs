//! Deterministic presentation of validated records; canonical JSON is untouched.
use crate::*;

pub(crate) fn text(value: &Value) -> String {
    let input = match value {
        Value::String(text) => text.clone(),
        Value::Null => "null".into(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        _ => "[object Object]".into(),
    };
    input
        .chars()
        .map(|ch| match ch {
            '\u{0000}'..='\u{001f}' | '\u{007f}' => " ".into(),
            '&' => "&amp;".into(),
            '<' => "&lt;".into(),
            '>' => "&gt;".into(),
            ':' => "&#58;".into(),
            '@' => "&#64;".into(),
            '\\' | '`' | '*' | '_' | '{' | '}' | '[' | ']' | '(' | ')' | '#' | '+' | '.' | '!'
            | '|' | '~' | '-' => format!("\\{ch}"),
            _ => ch.to_string(),
        })
        .collect()
}

fn section(lines: &mut Vec<String>, title: &str, values: &Value) {
    let Some(values) = values.as_array().filter(|values| !values.is_empty()) else {
        return;
    };
    lines.extend([String::new(), format!("**{title}**"), String::new()]);
    lines.extend(values.iter().map(|value| format!("- {}", text(value))));
}

fn continuation(lines: &mut Vec<String>, value: &Value) {
    if !value.is_object() {
        return;
    }
    lines.extend([
        String::new(),
        format!(
            "Continuation hold: {}.",
            if value["hold"] == true { "yes" } else { "no" }
        ),
    ]);
    if value.get("task_complete").is_some() {
        lines.push(format!(
            "Task completion claim: {}.",
            if value["task_complete"] == true {
                "complete"
            } else {
                "incomplete"
            }
        ));
    }
    if value["next"].is_object() {
        let next = &value["next"];
        let step = next["step"]
            .as_u64()
            .map(|step| format!(", Step {step}"))
            .unwrap_or_default();
        let id = next["direction"]["id"]
            .as_u64()
            .or_else(|| next["request"]["id"].as_u64())
            .map(|id| id.to_string())
            .unwrap_or_else(|| "UNAVAILABLE".into());
        lines.push(format!(
            "Authorized next direction: Task {}{step}; native reference {id}.",
            next["task"]
        ));
    }
}

fn core(record: &Value, title: &str) -> Vec<String> {
    let mut identity = format!("Task {}", record["task"]);
    if let Some(step) = record["step"]
        .as_u64()
        .or_else(|| record["admission"]["step"].as_u64())
    {
        identity.push_str(&format!(" — Step {step}"));
    }
    if record["change_request_id"].is_string() {
        identity.push_str(&format!(" — {}", text(&record["change_request_id"])));
    }
    let mut lines = vec![
        format!("## Relay {title}"),
        String::new(),
        identity,
        String::new(),
        "Authority model: github-native-v1".into(),
    ];
    if record["purpose"].is_string() {
        lines.extend([
            String::new(),
            format!("Purpose: {}", text(&record["purpose"])),
        ]);
    }
    if record["status"].is_string() {
        lines.extend([
            String::new(),
            format!(
                "Status: {}{}",
                text(&record["status"]),
                if record["kind"] == "outcome" {
                    " (execution claim)"
                } else {
                    ""
                }
            ),
        ]);
    }
    if record["verdict"].is_string() || record["kind"] == "change-request" {
        lines.extend([
            String::new(),
            format!(
                "Verdict: {}",
                text(record.get("verdict").unwrap_or(&json!("REQUEST_CHANGES")))
            ),
        ]);
    }
    if record["summary"].is_string() {
        lines.extend([String::new(), text(&record["summary"])]);
    }
    lines
}

pub(crate) fn render(record: &Value, title: &str, canonical_json: &str) -> String {
    let mut lines = core(record, title);
    if let Some(attempt) = record
        .get("attempt")
        .or_else(|| record["admission"].get("attempt"))
    {
        lines.extend([String::new(), format!("Attempt: {}", text(attempt))]);
    }
    if record["reviewed_head_sha"].is_string() {
        lines.extend([
            String::new(),
            format!("Reviewed head: {}", text(&record["reviewed_head_sha"])),
        ]);
    }
    if record["result"].is_object() {
        let result = &record["result"];
        lines.extend([
            String::new(),
            format!(
                "Result: {}; revision: {}.",
                text(&result["kind"]),
                if result["revision"].is_null() {
                    "UNAVAILABLE".into()
                } else {
                    text(&result["revision"])
                }
            ),
        ]);
        let identities = json!(result["identities"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| format!(
                "{}: {}",
                value["kind"].as_str().unwrap(),
                value["id"].as_str().unwrap()
            ))
            .collect::<Vec<_>>());
        section(&mut lines, "Immutable result identities", &identities);
    }
    if record["outcome"].is_object() {
        lines.extend([
            String::new(),
            format!(
                "Accepted Outcome native ID: {}; digest: {}.",
                record["outcome"]["id"],
                record["outcome"]["sha256"].as_str().unwrap()
            ),
        ]);
    }
    for (key, title) in [
        ("scope", "Scope"),
        ("boundaries", "Boundaries"),
        ("validation", "Required validation"),
    ] {
        section(&mut lines, title, &record[key]);
    }
    if record["issue_closure_policy"].is_string() {
        lines.extend([String::new(), format!("Issue closure policy: {}; closure still requires the applicable completion and independent acceptance conditions.", text(&record["issue_closure_policy"]))]);
    }
    if record["route"].is_string() {
        lines.extend([
            String::new(),
            format!("Execution route: {}.", text(&record["route"])),
        ]);
    }
    if record["model"].is_string()
        || record["effort"].is_string()
        || record.get("subagents").is_some()
    {
        lines.extend([String::new(), format!("Requested profile: model {}; effort {}; Subagents {}. Actual runtime profile is not inferred.", text(record.get("model").unwrap_or(&json!("project default"))), text(record.get("effort").unwrap_or(&json!("project default"))), match record["subagents"].as_bool() { Some(true)=>"On",Some(false)=>"Off",None=>"project default" })]);
    }
    continuation(&mut lines, &record["continuation"]);
    if let Some(amendments) = record["amendments"].as_object() {
        lines.extend([String::new(), "**Decision amendments**".into()]);
        for (key, value) in amendments {
            if key == "continuation" {
                continuation(&mut lines, value);
            } else if value.is_array() {
                section(&mut lines, &key.replace('_', " "), value);
            } else {
                lines.extend([
                    String::new(),
                    format!("{}: {}.", key.replace('_', " "), text(value)),
                ]);
            }
        }
    }
    if let Some(overrides) = record["overrides"]
        .as_object()
        .filter(|overrides| !overrides.is_empty())
    {
        lines.extend([String::new(), "**Remediation execution overrides**".into()]);
        for (key, value) in overrides {
            if value.is_array() {
                section(&mut lines, &key.replace('_', " "), value);
            } else {
                lines.extend([
                    String::new(),
                    format!("{}: {}.", key.replace('_', " "), text(value)),
                ]);
            }
        }
        lines.extend([String::new(),"Overrides apply within Task authority; they do not grant unrelated scope or Task closure.".into()]);
    }
    if let Some(findings) = record["findings"].as_array() {
        for finding in findings {
            lines.extend([
                String::new(),
                format!(
                    "**Finding {} ({})**",
                    text(&finding["id"]),
                    text(&finding["severity"])
                ),
                String::new(),
                format!("Problem: {}", text(&finding["problem"])),
                String::new(),
                format!("Impact: {}", text(&finding["impact"])),
                String::new(),
                format!("Required correction: {}", text(&finding["remediation"])),
            ]);
            section(
                &mut lines,
                "Acceptance criteria",
                &finding["acceptance_criteria"],
            );
            section(&mut lines, "Finding evidence", &finding["evidence"]);
        }
    }
    if let Some(warnings) = record["warnings"].as_array() {
        for warning in warnings {
            lines.extend([
                String::new(),
                "**Warning**".into(),
                String::new(),
                format!("Source: {}", text(&warning["source"])),
                String::new(),
                format!("Impact: {}", text(&warning["impact"])),
                String::new(),
                format!("Disposition: {}", text(&warning["resolution"])),
                String::new(),
                format!("Next action: {}", text(&warning["next_action"])),
            ]);
            section(&mut lines, "Evidence gaps", &warning["evidence_gaps"]);
        }
    }
    section(&mut lines, "Limitations", &record["limitations"]);
    if record["kind"] == "outcome" {
        lines.extend([String::new(),"Next acceptance boundary: independent exact-result review; execution claims do not establish independent acceptance.".into()]);
    }
    if record["kind"] == "change-request" || record["kind"] == "task-review" {
        lines.extend([String::new(),"Next acceptance boundary: correct the findings within authorized scope, then obtain fresh independent review of the exact result.".into()]);
    }
    let wrap = |lines: Vec<String>, open: bool| {
        format!("{}\n\n<details{}>\n<summary>Machine-readable authority (JSON)</summary>\n\n```relay-authority\n{canonical_json}\n```\n\n</details>\n",lines.join("\n"),if open { " open" } else { "" })
    };
    let body = wrap(lines, false);
    if body.len() <= 100000 && body.chars().count() <= 65536 {
        return body;
    }
    let mut lines = core(record, title);
    lines.extend([String::new(),"Presentation size limit: canonical JSON is open below so all scope, findings, warnings and limitations remain visible.".into()]);
    wrap(lines, true)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn shared_node_rust_rendering_fixtures_and_canonical_blocks_match() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../contracts/fixtures/publication-rendering.json"
        ))
        .unwrap();
        for case in fixture["cases"].as_array().unwrap() {
            let record = &case["record"];
            let title = task_authority::definition()["record_titles"]
                [record["kind"].as_str().unwrap()]
            .as_str()
            .unwrap();
            assert_eq!(
                render(
                    record,
                    title,
                    &serde_json::to_string_pretty(record).unwrap()
                ),
                case["body"].as_str().unwrap(),
                "{}",
                case["name"]
            );
        }
    }

    #[test]
    fn expanded_safety_escaping_opens_complete_json_with_no_material_truncation() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../contracts/fixtures/publication-rendering.json"
        ))
        .unwrap();
        let mut record = fixture["cases"]
            .as_array()
            .unwrap()
            .iter()
            .find(|case| case["name"] == "outcome-v4")
            .unwrap()["record"]
            .clone();
        record["limitations"] = json!(vec!["<&>:@".repeat(600); 10]);
        task_authority::validate_record(&record).unwrap();
        let canonical = serde_json::to_string_pretty(&record).unwrap();
        let body = render(&record, "Codex Outcome", &canonical);
        assert!(body.contains("<details open>"));
        assert!(body.contains("Presentation size limit:"));
        assert!(body.contains(&format!("```relay-authority\n{canonical}\n```")));
        assert!(body.len() <= 100_000 && body.chars().count() <= 65_536);
        assert_eq!(body.matches("<summary>").count(), 1);
    }
}
