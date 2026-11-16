"""Reproducible, descriptive GitHub PR engineering scorecard (public metadata only).

Samples the 20 latest PRs created+merged before #220 merged and the first
20 PRs created+merged afterward. Never describes PR metrics as agent accuracy
or evidence of causation. Runs with GITHUB_TOKEN in a read-only GitHub Action
or against an offline --input JSON fixture.

No sportsbook data, code snippets, personal data, secrets or bet records.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from statistics import median
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "bighauss/Sportsedge"
POLICY_PR = 220
POLICY_MERGED_UTC = "2026-11-16T04:52:14Z"
WINDOW = 20
MIN_MATURITY_DAYS = 14
API = "https://api.github.com/repos/" + REPOSITORY


def when(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_PR_TIMESTAMP")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NON_UTC_PR_TIMESTAMP")
    return d.astimezone(timezone.utc)


def select_windows(records, cutoff=POLICY_MERGED_UTC, size=WINDOW):
    border = when(cutoff)
    usable = [
        p for p in records
        if p.get("merged_at") and p.get("created_at")
        and isinstance(p.get("number"), int) and p["number"] != POLICY_PR
    ]
    earlier = [
        p for p in usable
        if when(p["created_at"]) < border and when(p["merged_at"]) < border
    ]
    later = [
        p for p in usable
        if when(p["created_at"]) >= border and when(p["merged_at"]) >= border
    ]
    # Freeze a deterministic historical baseline and a prospective first-N.
    earlier.sort(key=lambda p: (when(p["created_at"]), p["number"]), reverse=True)
    later.sort(key=lambda p: (when(p["created_at"]), p["number"]))
    return earlier[:size], later[:size]


def describe(cohort):
    counts = [p.get("commits") for p in cohort]
    sizes = [p.get("additions", 0) + p.get("deletions", 0) for p in cohort]
    files = [p.get("changed_files") for p in cohort]
    for name, values in (("commits", counts), ("changed_lines", sizes),
                         ("changed_files", files)):
        if any(type(v) is not int or v < 0 for v in values):
            raise ValueError("INVALID_" + name.upper() + "_METADATA")
    ci = [p.get("ci") for p in cohort]
    if any(not isinstance(v, dict) for v in ci):
        raise ValueError("MISSING_CI_OBSERVATION")
    covered = [v for v in ci if v.get("completed_workflows", 0) > 0]
    # Success rates use only PRs with observed completed checks.
    all_green = [v for v in covered if v.get("all_green") is True]
    observed_failure = sum(v.get("failed_workflows", 0) for v in ci)
    retries = sum(v.get("workflow_rerun_attempts", 0) for v in ci)
    changes_requested = sum(p.get("reviews_changes_requested", 0) for p in cohort)
    return {
        "merged_prs": len(cohort),
        "pr_numbers": [p["number"] for p in cohort],
        "median_changed_files": median(files) if files else None,
        "median_changed_lines": median(sizes) if sizes else None,
        "median_commits": median(counts) if counts else None,
        "prs_over_500_changed_lines": sum(s > 500 for s in sizes),
        "prs_over_10_changed_files": sum(f > 10 for f in files),
        "prs_with_completed_pr_head_workflows": len(covered),
        "prs_with_only_successful_completed_workflows": len(all_green),
        "all_green_rate_among_ci_observed": (
            round(len(all_green)/len(covered), 4) if covered else None),
        "failed_workflows_observed": observed_failure,
        "workflow_rerun_attempts_observed": retries,
        "review_changes_requested_submissions": changes_requested,
    }


def scorecard(records, *, as_of=None):
    now = when(as_of) if as_of else datetime.now(timezone.utc)
    base, after = select_windows(records)
    if len(base) < WINDOW:
        state = "BASELINE_INCOMPLETE"
    elif len(after) < WINDOW:
        state = "POST_SAMPLE_INCOMPLETE"
    elif max(when(p["merged_at"]) for p in after) > now - timedelta(days=MIN_MATURITY_DAYS):
        state = "POST_MATURITY_WINDOW_PENDING"
    else:
        state = "DESCRIPTIVE_WINDOWS_READY_NOT_CAUSAL"
    return {
        "schema": "sportsedge-coding-agent-pr-scorecard-v1",
        "repository": REPOSITORY,
        "policy_pr": POLICY_PR,
        "policy_pr_merged_at_utc": POLICY_MERGED_UTC,
        "as_of_utc": now.isoformat(),
        "state": state,
        "window_pr_count": WINDOW,
        "post_maturity_days_required": MIN_MATURITY_DAYS,
        "baseline": describe(base),
        "post": describe(after),
        "metrics_are_github_metadata_not_agent_accuracy": True,
        "causal_effect_established": False,
        "betting_source_validation": False,
        "official_counted": 0,
        "approved_stake_u": 0,
        "limitations": [
            "PR commit count is not a bug-fix count or rework rate",
            "Changed lines and files are scope proxies, not code quality",
            "CI conclusions are from currently visible completed PR-head workflow runs",
            "Unobserved and in-progress PR-head workflows are never counted green",
            "PR populations may differ in complexity, author and CI configuration",
            "No before/after delta establishes causality or model forecasting accuracy",
            "Missing historical check attempts and delayed defects require separate tracking",
        ],
    }


def markdown(report):
    b, p = report["baseline"], report["post"]
    fields = [
        ("Merged PRs", "merged_prs"),
        ("Median files changed", "median_changed_files"),
        ("Median lines changed", "median_changed_lines"),
        ("Median commits (not fix count)", "median_commits"),
        ("PRs above 500 changed lines", "prs_over_500_changed_lines"),
        ("PRs above 10 files", "prs_over_10_changed_files"),
        ("PRs with observed CI", "prs_with_completed_pr_head_workflows"),
        ("PRs all green among observed CI", "prs_with_only_successful_completed_workflows"),
        ("Green share among observed CI", "all_green_rate_among_ci_observed"),
        ("Failed workflow conclusions observed", "failed_workflows_observed"),
        ("Workflow retries observed", "workflow_rerun_attempts_observed"),
        ("CHANGES_REQUESTED review submissions", "review_changes_requested_submissions"),
    ]
    lines = [
        "# SportsEdge — Coding-agent PR quality scorecard",
        "",
        f"**State:** {report['state']}  ",
        f"**Cutoff:** [PR #{POLICY_PR}](https://github.com/{REPOSITORY}/pull/{POLICY_PR}) "
        f"merged {POLICY_MERGED_UTC}  ",
        f"**Generated:** {report['as_of_utc']}  ",
        "",
        "| Observed metric | Last 20 before | First 20 after |",
        "| --- | ---: | ---: |",
    ]
    for title,key in fields:
        lines.append(f"| {title} | {b[key] if b[key] is not None else 'N/A'} "
                     f"| {p[key] if p[key] is not None else 'N/A'} |")
    lines.extend([
        "",
        "**Baseline PRs:** " + ", ".join(f"#{n}" for n in b["pr_numbers"]),
        "",
        "**Post PRs:** " + ", ".join(f"#{n}" for n in p["pr_numbers"]),
        "",
        f"**Do not claim improvement yet.** Require {WINDOW} post-policy "
        f"merged PRs and {MIN_MATURITY_DAYS} days since the latest of those merges. "
        "Even then, these remain descriptive measures, not proof the agent rules caused a change.",
        "",
        "### Known limitations",
        "",
    ])
    lines.extend("- " + x for x in report["limitations"])
    return "\n".join(lines) + "\n"


def github_get(path):
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "SportsEdge-Public-PR-Scorecard/1.0",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    url = API + path
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
            return json.loads(response.read(8_000_000).decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        # Never echo Authorization values or any endpoint query parameters.
        raise RuntimeError("GITHUB_PUBLIC_METADATA_FETCH_FAILED") from None


def live_prs():
    merged = []
    for page in range(1, 11):
        prs = github_get(
            "/pulls?" + urllib.parse.urlencode(
                {"state":"closed", "sort":"created", "direction":"desc",
                 "per_page":100,"page":page}))
        if not isinstance(prs, list):
            raise RuntimeError("GITHUB_PR_RESPONSE_INVALID")
        merged.extend(p for p in prs if p.get("merged_at"))
        if len(prs) < 100:
            break
    before, after = select_windows(merged)
    selected = before + after
    details = []
    for p in selected:
        n = p["number"]
        item = github_get(f"/pulls/{n}")
        if item.get("number") != n or not item.get("merged_at"):
            raise RuntimeError("GITHUB_PR_METADATA_CHANGED")
        runs = github_get(
            "/actions/runs?" + urllib.parse.urlencode(
                {"head_sha":item["head"]["sha"],"event":"pull_request",
                 "per_page":100}))
        if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
            raise RuntimeError("GITHUB_WORKFLOW_RESPONSE_INVALID")
        relevant = [r for r in runs["workflow_runs"]
                    if r.get("head_sha") == item["head"]["sha"] and
                    r.get("event") == "pull_request"]
        completed = [r for r in relevant if r.get("status") == "completed"]
        counted = [r for r in completed if r.get("conclusion") not in ("skipped","neutral")]
        green = bool(counted) and all(r.get("conclusion")=="success" for r in counted)
        reviews = github_get(f"/pulls/{n}/reviews?per_page=100")
        if not isinstance(reviews, list):
            raise RuntimeError("GITHUB_REVIEW_RESPONSE_INVALID")
        details.append({
            "number": n,
            "created_at": item["created_at"],
            "merged_at": item["merged_at"],
            "additions": item["additions"],
            "deletions": item["deletions"],
            "changed_files": item["changed_files"],
            "commits": item["commits"],
            "reviews_changes_requested": sum(
                r.get("state")=="CHANGES_REQUESTED" for r in reviews),
            "ci": {
                "completed_workflows":len(counted),
                "all_green":green,
                "failed_workflows":sum(
                    r.get("conclusion") in ("failure","timed_out","action_required",
                                            "startup_failure") for r in counted),
                "workflow_rerun_attempts":sum(max(0,r.get("run_attempt",1)-1)
                                               for r in relevant),
            },
        })
    return details


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,
                        help="Offline JSON list of public PR facts; no API requests")
    parser.add_argument("--output-prefix",type=Path,required=True)
    parser.add_argument("--as-of",help="Override report clock for deterministic tests")
    a = parser.parse_args(argv)
    records = json.loads(a.input.read_text()) if a.input else live_prs()
    if not isinstance(records, list):
        parser.error("Input must be a JSON list of PR metadata")
    report = scorecard(records, as_of=a.as_of)
    a.output_prefix.parent.mkdir(parents=True,exist_ok=True)
    a.output_prefix.with_suffix(".json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n")
    a.output_prefix.with_suffix(".md").write_text(markdown(report))
    print(json.dumps({
        "state":report["state"],
        "baseline_prs":report["baseline"]["merged_prs"],
        "post_prs":report["post"]["merged_prs"],
        "causal_effect_established":False,
    },sort_keys=True))


if __name__=="__main__":
    main()
