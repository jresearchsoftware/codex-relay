"""Disposable Task 75 qualification artifact; never a product entrypoint.

Reads public native GitHub evidence with owner gh GET transport. It checks only
this fixture's immutable bindings; shared Relay validators remain authority.
No publication, worker, lifecycle, credential or merge operation is available.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


REPOSITORY = "jresearchsoftware/codex-relay"
SOURCE = "5a4b787b288781eef430651d93059a155d9411ec"
CHARTER = "22182e3e9732fded4d8879dac035da836a1f9dcc0d962f6499ab4e8ba98d12dc"
REQUEST_DIGEST = "0805514881588985e33422ada4ebc2093170b81ff0b7cea549b5d671c375bf93"
REQUEST_ID = 6020522601
CONTEXT_ID = 6020491123
REVIEWER = ("jresearchsoftware-chatgpt-reviewer[bot]", 306850842, "Bot")
WRITER = ("jresearchsoftware-codex-writer[bot]", 306851591, "Bot")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def author(native):
    user = native["user"]
    return user["login"], user["id"], user["type"]


def typed(body):
    blocks = re.findall(r"^```relay-authority\n(.*?)\n```$", body, re.M | re.S)
    require(len(blocks) == 1, "TYPED_RECORD_COUNT")
    record = json.loads(blocks[0])
    require(record["schema_version"] == "3.0", "TYPED_VERSION")
    return record


def check(snapshot, expected_head, require_closed=False):
    require(re.fullmatch(r"[0-9a-f]{40}", expected_head), "EXPECTED_HEAD_FORMAT")
    issue, comments, pr = snapshot["issue"], snapshot["comments"], snapshot["pr"]
    candidates = snapshot["branch_prs"]
    require(len(candidates) < 100 and [candidate["number"] for candidate in candidates] == [pr["number"]],
            "PR_PUBLICATION_AMBIGUOUS")
    require(issue["number"] == 75 and issue["state"] == "open", "TASK_BINDING")
    require(digest(issue["body"]) == CHARTER, "CHARTER_CHANGED")
    require([line for line in issue["body"].splitlines() if line.startswith("Authority model:")]
            == ["Authority model: github-native-v1"], "MIGRATION_MARKER")
    require([label["name"] for label in issue["labels"] if label["name"].startswith("step-")]
            == ["step-1"], "STEP_PROJECTION")
    require(len(comments) < 100, "COMMENT_ACQUISITION_INCOMPLETE")
    current = [c for c in comments if author(c) == REVIEWER and "```relay-authority\n" in c["body"]
               and typed(c["body"])["kind"] in ("task-request", "change-request")]
    require(len(current) == 1 and current[0]["id"] == REQUEST_ID, "FIXTURE_REQUEST_CHANGED")
    native = current[0]
    require(digest(native["body"]) == REQUEST_DIGEST, "REQUEST_BYTES_CHANGED")
    require(native["issue_url"] == f"https://api.github.com/repos/{REPOSITORY}/issues/75", "REQUEST_PARENT")
    request = typed(native["body"])
    require(request["repository"] == REPOSITORY and request["task"] == 75
            and request["parent"] == {"kind": "issue", "number": 75}, "REQUEST_TARGET")
    require(request["charter_sha256"] == CHARTER and request["step"] == 1
            and request["route"] == "manual" and request["supersedes"] is None, "REQUEST_SNAPSHOT")
    require(request["branch"] == "codex/task-75" and request["starting_head"] == SOURCE
            and request["base_sha"] == SOURCE and request["existing_pr"] is None, "SOURCE_BINDING")
    selected = request["context"]
    require(len(selected) == 1 and selected[0]["id"] == CONTEXT_ID
            and selected[0]["kind"] == "issue-comment"
            and selected[0]["parent"] == {"kind": "issue", "number": 75}, "CONTEXT_REFERENCE")
    context = [c for c in comments if c["id"] == CONTEXT_ID]
    require(len(context) == 1 and author(context[0]) == WRITER
            and digest(context[0]["body"]) == selected[0]["sha256"], "CONTEXT_PROVENANCE")
    require(context[0]["issue_url"] == native["issue_url"], "CONTEXT_PARENT")
    require(pr["head"]["repo"]["full_name"] == REPOSITORY
            and pr["base"]["repo"]["full_name"] == REPOSITORY
            and pr["base"]["ref"] == "main" and pr["base"]["sha"] == SOURCE
            and pr["head"]["ref"] == request["branch"] and pr["head"]["sha"] == expected_head, "PR_TARGET_HEAD")
    require("Related to #75" in pr["body"].splitlines()
            and f"Execution request digest: {REQUEST_DIGEST}" in pr["body"].splitlines(), "PR_DURABLE_BINDING")
    require([l["name"] for l in pr["labels"] if l["name"].startswith("step-")] == ["step-1"]
            and pr["title"].startswith("Task 75 · Step 1 · "), "PR_STEP_PROJECTION")
    require(not pr["merged"] and (not require_closed or pr["state"] == "closed"), "PR_DISPOSITION")
    outcome_native = snapshot.get("outcome")
    if outcome_native:
        require(author(outcome_native) == WRITER and outcome_native["issue_url"]
                == f"https://api.github.com/repos/{REPOSITORY}/issues/{pr['number']}", "OUTCOME_NATIVE_PARENT")
        outcome = typed(outcome_native["body"])
        require(outcome["kind"] == "outcome" and outcome["repository"] == REPOSITORY
                and outcome["task"] == 75 and outcome["charter_sha256"] == CHARTER
                and outcome["parent"] == {"kind": "pull_request", "number": pr["number"]}, "OUTCOME_TARGET")
        require(outcome["request"] == {"kind": "issue-comment", "id": REQUEST_ID,
                "parent": {"kind": "issue", "number": 75}, "sha256": REQUEST_DIGEST}
                and outcome["status"] == "implemented" and outcome["result"]["revision"] == expected_head,
                "OUTCOME_REQUEST_RESULT")
    return {"status": "FIXTURE_BINDINGS_VERIFIED", "task": 75, "request_id": REQUEST_ID,
            "request_sha256": REQUEST_DIGEST, "selected_context_author": list(WRITER),
            "pr": pr["number"], "head": expected_head, "pr_state": pr["state"],
            "writer_outcome_verified": bool(outcome_native)}


def get(path):
    response = subprocess.run(["gh", "api", "--method", "GET", f"repos/{REPOSITORY}/{path}"],
                              capture_output=True, text=True, encoding="utf-8", check=False)
    require(response.returncode == 0, "PUBLIC_GITHUB_READ_FAILED")
    return json.loads(response.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Offline synthetic or captured native evidence")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--require-closed", action="store_true")
    parser.add_argument("--outcome-comment", type=int)
    args = parser.parse_args()
    require(args.snapshot or args.pr and args.pr > 0, "PR_REQUIRED")
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else {
        "issue": get("issues/75"), "comments": get("issues/75/comments?per_page=100"), "pr": get(f"pulls/{args.pr}"),
        "branch_prs": get("pulls?state=all&head=jresearchsoftware:codex/task-75&per_page=100")}
    if args.outcome_comment:
        snapshot["outcome"] = get(f"issues/comments/{args.outcome_comment}")
    print(json.dumps(check(snapshot, args.expected_head, args.require_closed), sort_keys=True))


if __name__ == "__main__":
    main()
