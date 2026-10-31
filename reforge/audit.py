"""Configurable progressive commit-window analysis with cross-commit interaction evidence."""

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from reforge.detectors import detect_source, symbols_in_source
from reforge.textdetect import detect_text, is_text
from reforge.errors import ReforgeError
from reforge.git_history import (
    added_lines,
    changed_files,
    commit_count,
    commit_info,
    commit_window,
    file_at,
    is_git_repo,
)
from reforge.model import CommitInfo, Finding, StagePlan
from reforge.state import DEFAULT_START, DEFAULT_STEP, pending_reviews


def window_for_stage(stage: int, start: int = DEFAULT_START, step: int = DEFAULT_STEP,
                     stop: Optional[int] = None) -> int:
    """Window N: start + step*(N-1), capped by the run's stop (3,6,9 by default)."""
    if stage < 1:
        return 0
    wanted = start + step * (stage - 1)
    return min(wanted, stop) if stop is not None else wanted


def plan_next_stage(repo: Path, run: Dict[str, object]) -> StagePlan:
    """The next window for one run, its new commits and its already-audited overlap."""
    if not is_git_repo(repo):
        raise ReforgeError(
            f"{repo} is not a git repository.",
            "Reforge audits commits, so it needs a repository with at least one commit.",
            "run `git init` and commit the code first, or point the command at the repository root.",
        )
    if run.get("status") == "completed":
        raise ReforgeError(
            f"Audit run {run.get('id')} is complete at its stop of {run.get('stop')} commits.",
            "a completed run keeps its history and never advances past its configured stop.",
            "start a new audit run with `reforge start` when more history should be audited.",
        )
    if run.get("status") == "stopped":
        raise ReforgeError(
            f"Audit run {run.get('id')} is stopped.",
            "its next stage is waiting for an explicit resume or a new run.",
            f"resume it with `reforge resume <project> --run {run.get('id')}`, or start a new audit.",
        )
    pending = pending_reviews(run)
    if pending:
        first = pending[0]
        review = first.get("review") or {}
        raise ReforgeError(
            f"Audit run {run.get('id')} stage {first.get('stage')} is awaiting host review.",
            "Reforge only advances after the host answers every stage packet; a later stage "
            "does not excuse an earlier unreviewed one.",
            f"review `{review.get('packet') or 'the stage packet'}` and record the answer with "
            f"`reforge review <project> --run {run.get('id')} --stage {first.get('stage')} "
            f"--findings <file>`.",
        )
    total = commit_count(repo)
    if total == 0:
        raise ReforgeError(
            "The repository has no commits.",
            "an empty history has nothing to audit.",
            "commit the code, then run the audit again.",
        )
    start = int(run.get("start") or DEFAULT_START)
    step = int(run.get("step") or DEFAULT_STEP)
    stop = run.get("stop")
    stage = int(run.get("stage") or 0) + 1
    previous = int(run.get("window") or 0)
    wanted = window_for_stage(stage, start, step, stop if isinstance(stop, int) else None)
    if stop is not None and previous >= int(stop):
        raise ReforgeError(
            f"Audit run {run.get('id')} already reached its stop of {stop} commits.",
            "its stop is the largest window this run may audit.",
            "start a new audit run, or raise the stop with `reforge settings`.",
        )
    commits = commit_window(repo, min(wanted, total))
    audited = set(run.get("audited_commits") or [])
    new_shas = tuple(commit.sha for commit in commits if commit.sha not in audited)
    new_set = set(new_shas)
    prior_shas = tuple(sha for sha in (run.get("audited_commits") or []) if sha not in new_set)
    if not new_shas:
        raise ReforgeError(
            f"No new commits for stage {stage} of {run.get('id')}.",
            f"its window is the newest {min(wanted, total)} commits and every one was already audited.",
            "push or commit more work, raise the window with `reforge settings --step`/`--stop`, "
            "or stop this run and start a new audit.",
        )
    return StagePlan(stage=stage, window=min(wanted, total), commits=tuple(commits),
                     new_shas=new_shas, prior_shas=prior_shas,
                     run_id=str(run.get("id") or ""), start=start, step=step,
                     stop=stop if isinstance(stop, int) else None)


def _prior_context(repo: Path, plan: StagePlan, history: Sequence[Dict[str, object]]
                   ) -> Tuple[Dict[str, CommitInfo], Dict[Tuple[str, str], str],
                              Dict[Tuple[str, str, str], str], Dict[Tuple[str, str], int]]:
    by_sha = {commit.sha: commit for commit in plan.commits}
    paths: Dict[str, CommitInfo] = {}
    symbols: Dict[Tuple[str, str], str] = {}
    findings: Dict[Tuple[str, str, str], str] = {}
    repairs: Dict[Tuple[str, str], int] = {}
    for sha in plan.prior_shas:
        info = by_sha.get(sha) or commit_info(repo, sha)
        if info is None:
            continue
        for status, path in changed_files(repo, sha):
            if status == "D" or not supports_source(path):
                continue
            paths[path] = info
            source = file_at(repo, sha, path)
            if not source:
                continue
            touched = added_lines(repo, sha, path)
            try:
                for name, start, end in symbols_in_source(source):
                    if touched.intersection(range(start, end + 1)):
                        symbols[(path, name)] = sha
            except SyntaxError:
                continue
    for entry in history:
        for item in entry.get("findings") or []:
            findings[(item.get("path", ""), item.get("symbol", ""),
                      item.get("code", ""))] = item.get("commit", "")
        for item in entry.get("repairs") or []:
            if item.get("applied"):
                key = (item.get("path", ""), item.get("code", ""))
                repairs[key] = max(repairs.get(key, 0), int(entry.get("stage") or 0))
    return paths, symbols, findings, repairs


def _interaction(finding: Finding, prior: Tuple[Dict[str, CommitInfo],
                                                Dict[Tuple[str, str], str],
                                                Dict[Tuple[str, str, str], str],
                                                Dict[Tuple[str, str], int]]) -> Tuple[str, bool]:
    paths, symbols, findings, repairs = prior
    if (finding.path, finding.symbol) in symbols:
        sha = symbols[(finding.path, finding.symbol)]
        return (f"{finding.symbol or 'the symbol'} was introduced or changed earlier by {sha[:12]}", True)
    if (finding.path, finding.symbol, finding.code) in findings:
        sha = findings[(finding.path, finding.symbol, finding.code)]
        return f"the same rule at the same symbol was already analysed in {sha[:12]}", True
    stage = repairs.get((finding.path, finding.code))
    if stage:
        return f"a repair for this rule in this file was applied at stage {stage}", True
    if finding.path in paths:
        sha = paths[finding.path].sha
        return f"the file was also changed earlier by {sha[:12]}", False
    return "", False


SUPPORTED_SUFFIXES = (".py",)
# Files Reforge itself writes, or AIKit's memory: reporting them as "not analysed" is noise, not
# coverage, because no language front end was ever going to read a ledger or an audit state.
LEDGER_PATHS = (".aikit/task_ledger.json", ".agents/task_ledger.json")


def supports_source(path: str) -> bool:
    """Whether Reforge's AST detectors can analyse this path."""
    return path.lower().endswith(SUPPORTED_SUFFIXES)


def is_bookkeeping(path: str) -> bool:
    """Reforge's own state, its backups and locks, and the task ledger it updates."""
    normal = path.replace("\\", "/")
    if normal.startswith(".aikit/reforge."):
        return True
    return any(normal == ledger or normal in {f"{ledger}.bak", f"{ledger}.lock"}
               for ledger in LEDGER_PATHS)


def audit_window(repo: Path, plan: StagePlan, history: Sequence[Dict[str, object]] = (),
                 skipped: Optional[List[str]] = None,
                 reviewed: Optional[List[str]] = None,
                 detections: bool = True) -> List[Finding]:
    """Walk the stage's files and optionally run the cheap rules over the lines it adds.

    Reforge is the planner: the review itself belongs to the host agent, and this rule pass is a
    deterministic pre-pass that runs by default (`--no-rules` skips it) for a machine that wants
    coverage. Either way the walk still classifies every changed path, so `reviewed` names what was
    inspected and `skipped` collects only binary files that cannot be read as text.
    """
    prior = _prior_context(repo, plan, history)
    by_sha = {commit.sha: commit for commit in plan.commits}
    findings: List[Finding] = []
    uncovered: set = set()
    inspected: set = set()
    for sha in reversed(plan.new_shas):
        info = by_sha[sha]
        for status, path in changed_files(repo, sha):
            if status == "D" or is_bookkeeping(path):
                continue
            source = file_at(repo, sha, path)
            if source is None:
                continue
            if supports_source(path):
                parsed = detect_source(path, source, sha) if detections else []
            elif is_text(source):
                parsed = detect_text(path, source, sha) if detections else []
            else:
                uncovered.add(path)
                continue
            inspected.add(path)
            touched = added_lines(repo, sha, path)
            for finding in parsed:
                if status != "A" and finding.line not in touched:
                    continue
                interaction, strong = _interaction(finding, prior)
                if interaction:
                    finding = Finding(
                        **{**finding.as_dict(), "interaction": interaction,
                           "category": "regression" if strong else finding.category}
                    )
                findings.append(finding)
    if skipped is not None:
        skipped.extend(sorted(uncovered))
    if reviewed is not None:
        reviewed.extend(sorted(inspected))
    return _ordered(findings)


def _ordered(findings: Iterable[Finding]) -> List[Finding]:
    return sorted(findings, key=lambda item: (item.commit, item.path, item.line, item.code))


def summarize(findings: Sequence[Finding]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for finding in findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    return counts
