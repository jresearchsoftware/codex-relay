//! The Reviewer owns this wire format. The same bounded definition is read by
//! the Node consumer; cross-language publication tests guard their agreement.
use serde_json::{json, Value};
use std::{collections::HashSet, sync::OnceLock};
use unicode_normalization::UnicodeNormalization;

pub fn definition() -> &'static Value {
    static DEFINITION: OnceLock<Value> = OnceLock::new();
    DEFINITION.get_or_init(|| {
        serde_json::from_str(include_str!("executable-cr-v2.json")).expect("CR definition")
    })
}

// Deployment policy extends the historical v2 vocabulary without giving a CR
// authority to supply commands or change its own allowlist.
pub fn validation_names(config: &Value) -> Vec<String> {
    let Some(value) = config.get("validationNames") else {
        return Vec::new();
    };
    let names = value.as_array().expect("validationNames must be an array");
    assert!(names.len() <= 32, "Too many validation names");
    let mut unique = HashSet::new();
    names
        .iter()
        .map(|value| {
            let name = value.as_str().expect("Validation name must be a string");
            assert!(
                !name.is_empty()
                    && name.len() <= 64
                    && name.starts_with(|c: char| c.is_ascii_lowercase())
                    && name
                        .bytes()
                        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                    && unique.insert(name),
                "Invalid or duplicate validation name"
            );
            name.to_string()
        })
        .collect()
}

pub fn input_schema(validation_names: &[String]) -> Value {
    let mut schema = definition()["input_schema"].clone();
    let choices = schema["properties"]["required_validation"]["items"]["enum"]
        .as_array_mut()
        .unwrap();
    for name in validation_names {
        let value = json!(name);
        if !choices.contains(&value) {
            choices.push(value);
        }
    }
    schema
}

fn safe_text(s: &str) -> bool {
    !s.trim().is_empty()
        && s.nfc().eq(s.chars())
        && !s.to_ascii_lowercase().contains("filecite")
        && !s.chars().any(|c| {
            c.is_control()
                || matches!(c, '\u{fffd}' | '\u{200b}'..='\u{200f}' | '\u{2028}'..='\u{202e}' | '\u{2060}'..='\u{2069}' | '\u{feff}')
        })
        && !matches!(
            s.trim().to_ascii_lowercase().as_str(),
            "todo" | "tbd" | "unknown" | "pending" | "n/a"
        )
        && !(s.starts_with('<') && s.ends_with('>'))
}

fn format_matches(s: &str, format: &str) -> bool {
    match format {
        "stable-id" => {
            s.starts_with(|c: char| c.is_ascii_alphabetic())
                && s.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
        }
        "codex-argument" => {
            let secret = ["github_pat_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_"]
                .iter()
                .any(|prefix| {
                    s.match_indices(*prefix).any(|(start, _)| {
                        s[start + prefix.len()..]
                            .bytes()
                            .take_while(|b| b.is_ascii_alphanumeric() || *b == b'_')
                            .count()
                            >= 20
                    })
                });
            s.starts_with(|c: char| c.is_ascii_alphanumeric())
                && s.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
                && !secret
        }
        "completion-token" => {
            s.starts_with(|c: char| c.is_ascii_uppercase())
                && s.bytes()
                    .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
        }
        _ => false,
    }
}

// Deliberately only the keywords used by our source-controlled definition,
// not an interpreter for caller-supplied schemas. String bounds are UTF-8 bytes.
fn conforms(value: &Value, schema: &Value) -> bool {
    if let Some(choices) = schema["enum"].as_array() {
        if !choices.contains(value) {
            return false;
        }
    }
    match schema["type"].as_str() {
        Some("object") => value.as_object().is_some_and(|object| {
            let properties = schema["properties"].as_object().expect("properties");
            schema["required"]
                .as_array()
                .expect("required")
                .iter()
                .all(|key| object.contains_key(key.as_str().expect("key")))
                && object.iter().all(|(key, value)| {
                    properties
                        .get(key)
                        .is_some_and(|spec| conforms(value, spec))
                })
        }),
        Some("array") => value.as_array().is_some_and(|items| {
            items.len() >= schema["minItems"].as_u64().unwrap_or(0) as usize
                && items.len() <= schema["maxItems"].as_u64().expect("maxItems") as usize
                && items.iter().all(|item| conforms(item, &schema["items"]))
                && (schema["uniqueItems"] != true
                    || items
                        .iter()
                        .enumerate()
                        .all(|(i, item)| !items[..i].contains(item)))
        }),
        Some("string") => value.as_str().is_some_and(|s| {
            (schema.get("enum").is_some() || schema["format"] == "codex-argument" || safe_text(s))
                && s.len() <= schema["maxLength"].as_u64().unwrap_or(1000) as usize
                && schema["format"]
                    .as_str()
                    .is_none_or(|format| format_matches(s, format))
        }),
        Some("integer") => value.as_u64().is_some_and(|n| {
            n >= schema["minimum"].as_u64().expect("minimum")
                && n <= schema["maximum"].as_u64().expect("maximum")
        }),
        Some("boolean") => value.is_boolean(),
        _ => false,
    }
}

pub fn normalized(validation_names: &[String], input: &Value) -> Result<Value, &'static str> {
    let schema = &input_schema(validation_names);
    if !conforms(
        &input["required_validation"],
        &schema["properties"]["required_validation"],
    ) {
        return Err("CR_VALIDATION_INVALID");
    }
    if !conforms(input, schema) {
        return Err("INVALID_CHANGE_REQUEST");
    }
    let mut cr = input.clone();
    let object = cr.as_object_mut().expect("validated object");
    object.entry("subagents_allowed").or_insert(json!(false));
    object
        .entry("owner_policy_reconciliation")
        .or_insert(json!([]));
    let mut ids = HashSet::new();
    for finding in object["findings"].as_array().expect("findings") {
        if !ids.insert(finding["id"].as_str().expect("id").to_string()) {
            return Err("CR_FINDING_IDS_INVALID");
        }
    }
    if object["success_token"] == object["blocked_token"]
        || object["success_outcome"] == object["blocked_outcome"]
    {
        return Err("CR_OUTCOMES_INVALID");
    }
    for finding in object.get_mut("findings").unwrap().as_array_mut().unwrap() {
        finding
            .as_object_mut()
            .unwrap()
            .entry("evidence")
            .or_insert(json!([]));
    }
    object
        .get_mut("required_validation")
        .unwrap()
        .as_array_mut()
        .unwrap()
        .sort_by(|a, b| a.as_str().cmp(&b.as_str()));
    Ok(cr)
}

fn human(value: &Value) -> String {
    value
        .as_str()
        .expect("text")
        .chars()
        .map(|c| match c {
            '&' => "&amp;".into(),
            '<' => "&lt;".into(),
            '>' => "&gt;".into(),
            '`' | '*' | '_' | '[' | ']' | '\\' | '#' | '~' | '!' | '|' => {
                format!("&#{};", c as u32)
            }
            _ => c.to_string(),
        })
        .collect()
}

fn list(body: &mut String, heading: &str, items: &Value) {
    body.push_str(&format!("\n## {heading}\n"));
    for item in items.as_array().expect("list") {
        body.push_str(&format!("\n- {}", human(item)));
    }
    body.push('\n');
}

pub fn render(validation_names: &[String], arguments: &Value) -> Result<String, &'static str> {
    let cr = normalized(validation_names, &arguments["change_request"])?;
    let wire = json!({
        "schema_version": definition()["schema_version"],
        "repository": arguments["repository"], "pull_request": arguments["pr_number"],
        "reviewed_head_sha": arguments["expected_head_sha"], "change_request": cr
    });
    let mut body = format!(
        "# Change Request {}\n\nExecutable REQUEST_CHANGES (contract {}).\n\n\
         Repository: {}\n\nPull request: #{}\n\nReviewed and required starting head: `{}`\n\n\
         ## Remediation profile\n\nThread name: {}\n\nSupplied Step: {}\n\n\
         Codex model: {}\n\nCodex reasoning effort: {}\n\nSubagents: {}\n\n## Findings\n",
        human(&cr["change_request_id"]),
        definition()["schema_version"].as_str().unwrap(),
        human(&arguments["repository"]),
        arguments["pr_number"],
        arguments["expected_head_sha"].as_str().unwrap(),
        human(&cr["remediation_thread_title"]),
        cr["step"],
        human(&cr["codex_model"]),
        human(&cr["codex_effort"]),
        if cr["subagents_allowed"] == true {
            "On"
        } else {
            "Off"
        }
    );
    for f in cr["findings"].as_array().unwrap() {
        body.push_str(&format!(
            "\n### {} — {}\n",
            f["id"].as_str().unwrap(),
            human(&f["severity"])
        ));
        for (key, label) in [
            ("problem", "Problem"),
            ("impact", "Impact"),
            ("remediation", "Remediation"),
        ] {
            body.push_str(&format!("\n{label}: {}\n", human(&f[key])));
        }
        for (key, label) in [
            ("acceptance_criteria", "Acceptance criteria"),
            ("evidence", "Evidence"),
        ] {
            if !f[key].as_array().unwrap().is_empty() {
                body.push_str(&format!("\n{label}:\n"));
                for item in f[key].as_array().unwrap() {
                    body.push_str(&format!("\n- {}", human(item)));
                }
                body.push('\n');
            }
        }
    }
    for (key, label) in [
        (
            "starting_state_requirements",
            "Additional starting-state requirements",
        ),
        ("required_validation", "Required validation"),
        (
            "completion_requirements",
            "Completion and publication requirements",
        ),
        ("protected_boundaries", "Protected boundaries"),
        ("owner_policy_reconciliation", "Owner-policy reconciliation"),
    ] {
        if !cr[key].as_array().unwrap().is_empty() {
            list(&mut body, label, &cr[key]);
        }
    }
    body.push_str(&format!(
        "\n## Completion outcomes\n\nSuccess: `{}` — {}\n\nBlocked: `{}` — {}\n\n\
         ## Reviewer-owned execution data\n\n```{}\n{}\n```",
        cr["success_token"].as_str().unwrap(),
        human(&cr["success_outcome"]),
        cr["blocked_token"].as_str().unwrap(),
        human(&cr["blocked_outcome"]),
        definition()["fence"].as_str().unwrap(),
        serde_json::to_string_pretty(&wire).unwrap()
    ));
    if body.len() > definition()["max_body_bytes"].as_u64().unwrap() as usize {
        return Err("CR_RENDER_TOO_LARGE");
    }
    Ok(body)
}
