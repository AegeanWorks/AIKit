"""
Integration & Operational Dogfooding Tier (PRINCIPLE-014, PRINCIPLE-015).

This module holds the tests that must spawn real processes: multi-process concurrency
reproductions, real-binary CLI contracts, and real `git` output grounding. They cannot be
sub-millisecond by nature, so they are budgeted separately from the unit tier in
`test_kit.py`, which carries the <=20ms per-test budget.

Both tiers run under the single canonical command (`python -m unittest discover tests`);
nothing here is hidden or opt-in. Every spawned process is bounded by an explicit timeout
(PRINCIPLE-010 R3, PRINCIPLE-015 R2) so a hung child can never stall the suite.
"""

import ast
import contextlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.check_secrets import run_scan  # noqa: E402
from scripts.check_reachability import (  # noqa: E402
    PUBLIC_API_ALLOWLIST,
    collect_definitions,
    find_phantom_keys,
    find_unreachable,
    production_modules,
)
from scripts.update_knowledge_base import check_codebase_map_freshness, check_workspace, parse_source  # noqa: E402
from scripts.project_gates import Gate, run_gates  # noqa: E402
from scripts.aikit_cli import main as aikit_main  # noqa: E402
from scripts import ui_contract  # noqa: E402
from scripts.check_project_hygiene import scan_artifacts, scan_tree  # noqa: E402
from scripts.project_registry import create_project, render_project_readme  # noqa: E402
from scripts.disruption_recovery import (  # noqa: E402
    load_ledger,
    record_checkpoint,
    run_disruption_audit,
    git_porcelain_status,
    format_audit_report,
    format_resume_report,
    classify_git_status,
    classify_track,
    collect_working_changes,
    UNMERGED_CODES,
)


def review_attestations(packet: str) -> list:
    """One valid quote and note per packet hunk, for tests that need a complete answer."""
    added: dict = {}
    removed: dict = {}
    current = None
    for line in packet.splitlines():
        match = re.match(r"^hunk (\S+:\S+#\d+) ", line)
        if match:
            current = match.group(1)
            added.setdefault(current, "")
            removed.setdefault(current, "")
        elif current and line.startswith("+") and not line.startswith("+++"):
            body = line[1:]
            if body.strip() and not added[current]:
                added[current] = body
        elif current and line.startswith("-") and not line.startswith("---"):
            body = line[1:]
            if body.strip() and not removed[current]:
                removed[current] = body
    attestations = []
    for hunk_id in added:
        quote = added[hunk_id] or removed[hunk_id]
        if quote:
            attestations.append({"id": hunk_id, "quote": quote,
                                 "note": f"checked the hunk {hunk_id}"})
    return attestations

# Hard ceiling for any single spawned process in this tier (PRINCIPLE-015 R1).
PROC_TIMEOUT = 10


def complete_readme(project_root: Path) -> None:
    """Fill a seed README's `<FILL:` marker the way a project's first commit must (ADR-138)."""
    path = project_root / "README.md"
    path.write_text(re.sub(r"<FILL:[^>]*>", "Python 3.10+ and git", path.read_text(encoding="utf-8")),
                    encoding="utf-8")


def remove_tree(path: Path) -> None:
    """Remove a test tree even when copied `.git` objects kept their read-only bit (Windows)."""
    def clear_and_retry(function, target, _error):
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except OSError:  # hygiene: allow locked cleanup is reported by the leftover-dir check
            pass
    # A transient antivirus or indexer lock can survive the first rmtree; retry briefly rather
    # than leave a repository behind (the integration tier only, so no unit-tier sleep).
    for _ in range(3):
        shutil.rmtree(path, onerror=clear_and_retry)
        if not path.exists():
            return
        time.sleep(0.05)


TEMPLATE_KIT = None
TEMPLATE_PROJECT = None


def setUpModule():
    """Create one committed project template; repo copies are cheaper than git init+commit.

    `complete_readme` fills the seed README after `create_project` committed it, so the template
    intentionally carries that one ` M README.md`; a test that needs a clean tree must commit it.
    """
    global TEMPLATE_KIT, TEMPLATE_PROJECT
    identity = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    with mock.patch.dict(os.environ, identity):
        TEMPLATE_KIT = Path(tempfile.mkdtemp(prefix="test_project_template_"))
        TEMPLATE_PROJECT = create_project(
            "app", test_command=f'"{sys.executable}" -c "pass"', workspace=TEMPLATE_KIT)
        complete_readme(TEMPLATE_PROJECT)


def tearDownModule():
    if TEMPLATE_KIT is not None:
        remove_tree(TEMPLATE_KIT)


def copy_project(kit: Path) -> Path:
    """A fresh copy of the committed template at `<kit>/projects/app`."""
    target = kit / "projects" / "app"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE_PROJECT, target, symlinks=True)
    return target


class TestParallelAgentSafety(unittest.TestCase):
    """
    Multi-process reproduction of the lost-update race (PRINCIPLE-013 R3).

    The advisory lock existed, was exported and was unit-tested, but had zero production call
    sites, so parallel subagents interleaved load/save cycles and silently erased each other's
    checkpoints. This requires genuinely separate processes: an in-process thread test would not
    reproduce what "parallel subagents" means.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="test_parallel_"))
        self.addCleanup(remove_tree, self.dir)
        self.ledger = self.dir / ".agents" / "task_ledger.json"

    def test_parallel_checkpoints_do_not_lose_updates(self):
        code = (
            "import sys;sys.path.insert(0,r'" + str(ROOT_DIR) + "');"
            "from pathlib import Path;"
            "from scripts.disruption_recovery import record_checkpoint;"
            "record_checkpoint('agent-{}','phase 3','concurrent',"
            "ledger_file=Path(r'" + str(self.ledger) + "'))"
        )
        record_checkpoint("agent-SEED", "phase 3", "seed", ledger_file=self.ledger)
        agents = "ABC"
        procs = [subprocess.Popen([sys.executable, "-c", code.format(a)]) for a in agents]  # hygiene: allow comprehension spawn; every proc.wait below is bounded
        for p in procs:
            self.assertEqual(
                p.wait(timeout=PROC_TIMEOUT), 0, "a concurrent checkpoint process failed"
            )

        persisted = {c["task_id"] for c in load_ledger(self.ledger)["checkpoints"]}
        expected = {"agent-SEED"} | {f"agent-{a}" for a in agents}
        self.assertEqual(
            persisted, expected,
            f"Lost update detected: {expected - persisted} vanished under concurrent writes",
        )

    def test_no_lock_artifacts_survive_concurrent_writes(self):
        # PRINCIPLE-013: locks and temp buffers must not leak after contention resolves.
        record_checkpoint("t", "phase 1", "cp", ledger_file=self.ledger)
        leftovers = [
            p.name for p in self.ledger.parent.iterdir()
            if p.name.endswith(".lock") or ".tmp_" in p.name or ".steal_" in p.name
        ]
        self.assertEqual(leftovers, [], f"lock/temp artifacts leaked: {leftovers}")


class TestGitStatusGrounding(unittest.TestCase):
    """
    Empirical grounding of the porcelain parser against real `git` output (PRINCIPLE-003 R1).
    Exhaustive per-state classification is covered without subprocesses in the unit tier.
    """

    def test_parser_offsets_match_real_git_output(self):
        # The parser slices raw_line[:2] and raw_line[3:]; verify those offsets against output
        # produced by the actual git binary rather than a hand-written fixture.
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=str(ROOT_DIR), capture_output=True, text=True, timeout=PROC_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git unavailable")
        if res.returncode != 0:
            self.skipTest("not a git worktree")

        classified = classify_git_status(res.stdout)
        for raw in res.stdout.splitlines():
            if len(raw) < 4 or raw[:2] == "!!":
                continue
            path = raw[3:].strip()
            bucket = (
                classified["untracked"] if raw[:2] == "??"
                else classified["conflicted"] if raw[:2] in UNMERGED_CODES
                else classified["modified"]
            )
            self.assertTrue(
                any(path in entry for entry in bucket),
                f"real git line {raw!r} was not classified into {bucket}",
            )

    def test_conflict_audit_reports_block_rather_than_clean(self):
        # The contract an agent actually reads: a conflicted tree must never render "Clean state"
        # and must carry a remediation command (PRINCIPLE-011 R6). A throwaway workspace keeps
        # this report test from walking the repository's ignored bulk trees.
        workspace = Path(tempfile.mkdtemp(prefix="test_audit_conflict_"))
        self.addCleanup(remove_tree, workspace)
        audit = run_disruption_audit(workspace, git_status=lambda _: (0, "UU merged.txt\0", ""))
        self.assertTrue(audit["has_conflicts"])
        report = format_audit_report(audit)
        self.assertNotIn("Clean state", report)
        self.assertIn("UNRESOLVED MERGE CONFLICTS", report)
        self.assertIn("UU merged.txt", report)
        self.assertIn("merge --abort", report, "conflict report lacks a remediation command")

        resume = format_resume_report(audit)
        self.assertIn("BLOCKED", resume)
        self.assertIn("rebase --abort", resume)


class TestCommitValidatorCli(unittest.TestCase):
    """Conventional Commit validator exercised as a real binary (PRINCIPLE-018 R1)."""

    def _run(self, message):
        return subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "disruption_recovery.py"),
             "--validate-commit", message],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
        )

    def test_valid_message_exits_zero(self):
        res = self._run("feat(cli): add valid flag")
        self.assertEqual(res.returncode, 0)
        self.assertIn("[OK]", res.stdout)

    def test_invalid_message_exits_one_with_reason(self):
        res = self._run("invalid commit")
        self.assertEqual(res.returncode, 1)
        self.assertIn("[INVALID]", res.stderr)


class TestOperationalDogfooding(unittest.TestCase):
    """
    Dual-Track CLI Dogfooding & Zero-Blast-Radius Chaos Test (PRINCIPLE-015).
    Executes every entrypoint as a real subshell binary from an ephemeral sandbox cwd with
    stdin closed, asserting the CLI contract and zero host mutation. The subshell matrix runs
    once in a bounded thread pool (PRINCIPLE-010 R3) to keep this tier's cost flat.
    """

    SCRIPTS = (
        "sync_principles.py", "disruption_recovery.py", "update_knowledge_base.py",
        "dogfood.py", "check_reachability.py", "check_secrets.py",
    )

    @staticmethod
    def _porcelain():
        """Return the working-tree state, or None when git is unavailable."""
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=PROC_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return res.stdout if res.returncode == 0 else None

    @classmethod
    def setUpClass(cls):
        cls.sandbox = Path(tempfile.mkdtemp(prefix="dogfood_jail_"))
        cls.addClassCleanup(remove_tree, cls.sandbox)

        def invoke(job):
            script, flag = job
            return job, subprocess.run(
                [sys.executable, str(ROOT_DIR / "scripts" / script), flag],
                capture_output=True, text=True, cwd=str(cls.sandbox),
                stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
            )

        # Track 1 (golden path): --help. Track 2 (hostile chaos): a malformed flag.
        jobs = [(s, f) for f in ("--help", "--not-a-real-flag") for s in cls.SCRIPTS]
        cls.tree_before = cls._porcelain()
        with ThreadPoolExecutor(max_workers=min(len(jobs), (os.cpu_count() or 2))) as pool:
            cls.results = dict(pool.map(invoke, jobs))
        cls.tree_after = cls._porcelain()

    def test_ephemeral_sandbox_isolation(self):
        # Blast-radius guard: the jail must be ephemeral and never the repo or a host user dir
        self.assertTrue(self.sandbox.exists())
        resolved = self.sandbox.resolve()
        self.assertNotEqual(resolved, ROOT_DIR.resolve())
        self.assertNotIn(
            str(ROOT_DIR.resolve()), str(resolved),
            f"Sandbox {resolved} must live outside the repository tree",
        )

    def test_golden_path_help_contract(self):
        # PRINCIPLE-011 R5/R6 + PRINCIPLE-015 R1: --help on every entrypoint exits 0 and
        # prints a usage block to stdout with clean stderr.
        for script in self.SCRIPTS:
            with self.subTest(script=script):
                res = self.results[(script, "--help")]
                self.assertEqual(res.returncode, 0, f"{script} --help must exit 0, got {res.returncode}")
                self.assertEqual(res.stderr, "", f"{script} --help wrote to stderr: {res.stderr!r}")
                self.assertIn("Usage:", res.stdout, f"{script} --help printed no usage block")
                self.assertIn("--help", res.stdout, f"{script} --help did not document --help")
                self.assertNotIn("Traceback", res.stdout + res.stderr)

    def test_chaos_unknown_flag_rejected_with_remediation_triad(self):
        # PRINCIPLE-015 R5 hostile perturbation: a malformed flag must abort with exit 2 and the
        # What/Why/Fix triad rather than silently performing the default action.
        for script in self.SCRIPTS:
            with self.subTest(script=script):
                res = self.results[(script, "--not-a-real-flag")]
                self.assertEqual(
                    res.returncode, 2,
                    f"{script} must exit 2 on CLI misuse, got {res.returncode}",
                )
                self.assertIn("[INVALID USAGE]", res.stderr, f"{script} misuse lacks a What clause")
                self.assertIn("Why:", res.stderr, f"{script} misuse lacks a Why clause")
                self.assertIn("Fix:", res.stderr, f"{script} misuse lacks a Fix clause")
                self.assertNotIn("Traceback", res.stderr)

    def test_dogfood_matrix_leaves_zero_blast_radius(self):
        # PRINCIPLE-015 R4 + PRINCIPLE-014 R4: the whole subshell matrix (golden + chaos)
        # must leave the working tree bit-for-bit unchanged.
        if self.tree_before is None or self.tree_after is None:
            self.skipTest("git unavailable; blast-radius assertion requires a git worktree")
        self.assertEqual(
            self.tree_before, self.tree_after,
            "PRINCIPLE-015 violation: the golden-path + chaos CLI matrix mutated the working tree",
        )


class TestWorkspaceIsolation(unittest.TestCase):
    """
    `disruption_recovery.py` anchors its ledger to the repository, not the working directory, so
    without `--workspace` a sandboxed dogfood run writes straight into the real ledger. The first
    dogfood run did exactly that, clobbering the active task (PRINCIPLE-015 R4).
    """

    def setUp(self):
        self.jail = Path(tempfile.mkdtemp(prefix="test_workspace_"))
        self.addCleanup(remove_tree, self.jail)

    def _ledger_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "disruption_recovery.py"), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
        )

    def test_workspace_flag_redirects_the_ledger(self):
        real_ledger = ROOT_DIR / ".agents" / "task_ledger.json"
        before = real_ledger.read_bytes() if real_ledger.exists() else None

        res = self._ledger_cli("--workspace", str(self.jail),
                               "--checkpoint", "isolated", "--phase", "planning",
                               "--desc", "workspace isolation probe")
        self.assertEqual(res.returncode, 0, f"checkpoint failed: {res.stderr[:200]}")

        sandbox_ledger = self.jail / ".agents" / "task_ledger.json"
        self.assertTrue(sandbox_ledger.exists(), "--workspace did not write into the sandbox")
        data = json.loads(sandbox_ledger.read_text(encoding="utf-8"))
        self.assertEqual(data["active_task"]["task_id"], "isolated")

        after = real_ledger.read_bytes() if real_ledger.exists() else None
        self.assertEqual(before, after, "--workspace run mutated the repository ledger")

    def test_workspace_without_value_is_refused(self):
        # PRINCIPLE-011 R5/R6: a flag that silently defaults to the real ledger would be worse
        # than an error, so a missing value must exit 2 with the remediation triad.
        res = self._ledger_cli("--workspace")
        self.assertEqual(res.returncode, 2, f"expected exit 2, got {res.returncode}")
        self.assertIn("[INVALID USAGE]", res.stderr)
        self.assertIn("Fix:", res.stderr)

    def test_audit_and_resume_honour_the_workspace(self):
        self._ledger_cli("--workspace", str(self.jail),
                         "--checkpoint", "scoped", "--phase", "verification",
                         "--phase-num", "4", "--desc", "scoped task")
        res = self._ledger_cli("--workspace", str(self.jail), "--resume")
        self.assertEqual(res.returncode, 0)
        self.assertIn("scoped", res.stdout)
        self.assertIn("Phase 4", res.stdout, "resume lost the phase recorded in the sandbox")

    def test_resume_and_checkpoint_refuse_a_newer_ledger(self):
        ledger = self.jail / ".agents" / "task_ledger.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"version": 2, "active_task": {"task_id": "future"},
                                      "checkpoints": []}), encoding="utf-8")
        before = ledger.read_bytes()

        resume = self._ledger_cli("--workspace", str(self.jail), "--resume")
        self.assertEqual(resume.returncode, 1)
        self.assertIn("BLOCKED", resume.stdout)
        self.assertIn("schema version 2", resume.stdout)
        self.assertNotIn("Traceback", resume.stderr)
        self.assertEqual(ledger.read_bytes(), before)

        checkpoint = self._ledger_cli("--workspace", str(self.jail),
                                      "--checkpoint", "blocked", "--phase-num", "1",
                                      "--desc", "must not write")
        self.assertEqual(checkpoint.returncode, 1)
        self.assertIn("VERSION REFUSED", checkpoint.stderr)
        self.assertNotIn("Traceback", checkpoint.stderr)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual(list(ledger.parent.glob("*.corrupt_*")), [])


class TestDogfoodRunner(unittest.TestCase):
    """
    The operational dogfood runner is itself a shipped surface (PRINCIPLE-015), so it carries
    regression coverage like any other entrypoint.
    """

    RUNNER = ROOT_DIR / "scripts" / "dogfood.py"

    @classmethod
    def setUpClass(cls):
        cls.result = subprocess.run(
            [sys.executable, str(cls.RUNNER)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT_DIR), stdin=subprocess.DEVNULL, timeout=60,
        )

    def test_dogfood_run_passes_every_track(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"dogfood gate failed. stdout: {self.result.stdout[-900:]} "
            f"stderr: {self.result.stderr[-400:]}",
        )
        self.assertNotIn("[FAIL]", self.result.stdout)
        self.assertIn("tracks passed", self.result.stdout)

    def test_dogfood_reports_tersely(self):
        # PRINCIPLE-015 R7: the console dashboard stays readable at a glance.
        lines = [l for l in self.result.stdout.splitlines() if l.strip()]
        self.assertLessEqual(len(lines), 18, f"dashboard too verbose ({len(lines)} lines)")

    def test_dogfood_covers_golden_and_chaos_tracks(self):
        # PRINCIPLE-015 R5: testing --help alone is explicitly forbidden.
        for track in ("golden lifecycle", "chaos perturbation", "blast radius"):
            with self.subTest(track=track):
                self.assertIn(track, self.result.stdout, f"dogfood omits the {track} track")

    def test_dogfood_emits_no_unhandled_traceback(self):
        # A reader-thread UnicodeDecodeError previously surfaced here on a cp1254 locale.
        self.assertNotIn("Traceback", self.result.stderr)
        self.assertNotIn("UnicodeDecodeError", self.result.stderr)

    def test_dogfood_writes_its_declared_log(self):
        log = ROOT_DIR / ".agents" / "dogfood_last_run.log"
        self.assertTrue(log.exists(), "PRINCIPLE-015 R7 log was not written")
        self.assertIn("track:", log.read_text(encoding="utf-8"))

    def test_dogfood_leaves_tracked_content_untouched(self):
        # The runner's own blast-radius claim, verified independently of the runner.
        self.assertIn("zero host mutation", self.result.stdout)

    def test_dogfood_cli_contract(self):
        help_res = subprocess.run(
            [sys.executable, str(self.RUNNER), "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
        )
        self.assertEqual(help_res.returncode, 0)
        self.assertIn("Usage:", help_res.stdout)
        self.assertEqual(help_res.stderr, "")

        bad_res = subprocess.run(
            [sys.executable, str(self.RUNNER), "--nope"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
        )
        self.assertEqual(bad_res.returncode, 2)
        self.assertIn("[INVALID USAGE]", bad_res.stderr)


class TestInvolvedCli(unittest.TestCase):
    """`sync_principles.py --involved` is the authoritative answer to PRINCIPLE-001 R3."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "sync_principles.py"), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
        )

    def test_lists_involved_principles_one_per_line(self):
        res = self._run("--involved", "FAIL:", "python", "scripts/dogfood.py", "exited", "1")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.split(), ["PRINCIPLE-015"])

    def test_text_after_involved_is_never_parsed_as_options(self):
        # Failing output often contains flags; they are text here, not --help or misuse.
        res = self._run("--involved", "--help", "--not-a-real-flag")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("Usage:", res.stdout)
        self.assertEqual(res.stdout.split(), ["PRINCIPLE-010"])  # its capsule names `--help`

    def test_missing_text_is_misuse(self):
        res = self._run("--involved")
        self.assertEqual(res.returncode, 2)
        self.assertIn("Fix:", res.stderr)

    def test_citing_lists_the_cross_principle_set_and_rejects_unknown_ids(self):
        # PRINCIPLE-000 R3: one computed list per changed principle, one ID per line.
        res = self._run("--citing", "PRINCIPLE-019")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.split(), ["PRINCIPLE-000", "PRINCIPLE-009", "PRINCIPLE-011", "PRINCIPLE-012", "PRINCIPLE-018"])
        bad = self._run("--citing", "PRINCIPLE-999")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("Fix:", bad.stderr)


class TestTrackCli(unittest.TestCase):
    """`disruption_recovery.py --track` reads real git state (PRINCIPLE-002 R3)."""

    def test_track_follows_the_actual_diff(self):
        kit = Path(tempfile.mkdtemp(prefix="test_track_"))
        self.addCleanup(remove_tree, kit)
        repo = copy_project(kit)
        git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=T",
               "-c", "commit.gpgsign=false"]
        code = "def f(x):\n    return x + 1\n"
        (repo / "m.py").write_text(code, encoding="utf-8")
        (repo / "modül.py").write_text(code, encoding="utf-8")  # git quotes this path without -z
        subprocess.run([*git, "add", "-A"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        subprocess.run([*git, "commit", "-qm", "base"], cwd=repo, check=True, timeout=PROC_TIMEOUT)

        def track():
            res = subprocess.run(
                [sys.executable, str(ROOT_DIR / "scripts" / "disruption_recovery.py"),
                 "--workspace", str(repo), "--track"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            return res.stdout.splitlines()[0]

        # The CLI spawn proves --track's real-git path, including the non-ASCII name git quotes
        # without -z. The surrounding A/C states use the same collector in-process, so the tier
        # does not pay for three nearly identical interpreter startups.
        def classify():
            return classify_track(collect_working_changes(repo))[0]

        (repo / ".agents").mkdir()
        (repo / ".agents" / "task_ledger.json").write_text("{}", encoding="utf-8")
        self.assertEqual(classify(), "A")
        (repo / "modül.py").write_text("# comment only\n" + code, encoding="utf-8")
        (repo / "README.md").write_text("# r, typo fixed\n", encoding="utf-8")
        self.assertEqual(track(), "Track B")
        (repo / "m.py").write_text(code.replace("+ 1", "+ 2"), encoding="utf-8")
        self.assertEqual(classify(), "C")


class TestCallSiteCommand(unittest.TestCase):
    """PRINCIPLE-003 R2's exact command must work for every name kind it covers, flags included."""

    def test_command_finds_a_flag(self):
        res = subprocess.run(["git", "grep", "-n", "-w", "-e", "--track"], cwd=str(ROOT_DIR),
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=PROC_TIMEOUT)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("disruption_recovery.py", res.stdout)


class TestAstGateCli(unittest.TestCase):
    """PRINCIPLE-003 R7: the gate halts with file and line, never a raw traceback."""

    def test_syntax_error_halts_cleanly(self):
        probe = ROOT_DIR / "scripts" / "_ast_gate_probe.py"
        probe.write_text("def broken(:\n", encoding="utf-8")
        self.addCleanup(probe.unlink, missing_ok=True)
        res = subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "update_knowledge_base.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("_ast_gate_probe.py", res.stderr)
        self.assertIn("line 1", res.stderr)
        self.assertIn("Fix:", res.stderr)
        self.assertNotIn("Traceback", res.stderr)

    def test_workspace_cli_check_detects_violations_and_passes_when_clean(self):
        sandbox = Path(tempfile.mkdtemp(prefix="kb_ws_cli_"))
        self.addCleanup(remove_tree, sandbox)
        # 1. Failing case: has stub
        (sandbox / "app.py").write_text("def bad(): pass\n", encoding="utf-8")
        res_fail = subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "update_knowledge_base.py"),
             "--workspace", str(sandbox), "--check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=PROC_TIMEOUT,
        )
        self.assertEqual(res_fail.returncode, 1)
        self.assertIn("function 'bad' is a stub", res_fail.stdout)
        self.assertIn("README.md does not exist", res_fail.stdout, "projects get PRINCIPLE-005 too (ADR-128)")

        # 2. Passing case: clean function, a completed README, and valid ADRs in .aikit/decisions.md
        (sandbox / "app.py").write_text("def ok() -> int:\n    return 42\n", encoding="utf-8")
        (sandbox / ".gitignore").write_text(".aikit/*.lock\n", encoding="utf-8")
        seed = render_project_readme("ws")
        (sandbox / "README.md").write_text(re.sub(r"<FILL:[^>]*>", "Python 3.10+ and git", seed),
                                           encoding="utf-8")
        (sandbox / ".aikit").mkdir(parents=True)
        (sandbox / ".aikit" / "decisions.md").write_text(
            "# Decisions\n\n### ADR-001: Init\n\n### ADR-002: Next\n", encoding="utf-8"
        )
        # The first CLI invocation proves the --workspace wiring; the remaining cases exercise the
        # same checker in-process, so the tier does not pay for three nearly identical spawns.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(check_workspace(sandbox))
        self.assertIn("ADR IDs are unique and consecutive", out.getvalue())

        # 3. The unfilled seed keeps the gate red: its `<FILL:` prerequisite is a fact only the
        #    project can state (PRINCIPLE-005 R1, ADR-138).
        (sandbox / "README.md").write_text(seed, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(check_workspace(sandbox))
        self.assertIn("unfilled '<FILL:' placeholder", out.getvalue())


class TestRepositoryCodebaseMap(unittest.TestCase):
    """PRINCIPLE-016 live invariant. Integration tier with the other whole-repository scans: mapping
    every file, the test modules included, costs ~0.1s cold, which the unit tier's 1s cannot carry
    (ADR-128)."""

    def test_codebase_map_freshness_gate(self):
        # Enforces PRINCIPLE-016: codebase_map.md must be 100% synchronized with physical codebase AST
        self.assertTrue(
            check_codebase_map_freshness(strict=True),
            "knowledge/codebase_map.md must be fresh and match current AST"
        )


class TestProofGate(unittest.TestCase):
    """IDEA-956: a declared test must fail on the base tree and pass on the current tree."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="proof_gate_"))
        self.addCleanup(shutil.rmtree, str(self.repo), True)
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test")
        (self.repo / "tests").mkdir()
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repo / "tests" / "test_app.py").write_text(
            "import unittest\n"
            "from app import VALUE\n\n"
            "class TestApp(unittest.TestCase):\n"
            "    def test_value(self):\n"
            "        self.assertEqual(VALUE, 2)\n",
            encoding="utf-8",
        )
        self._git("add", "app.py", "tests/test_app.py")
        self._git("commit", "-qm", "base")
        (self.repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    def _git(self, *args):
        subprocess.run(
            ["git", *args], cwd=self.repo, check=True, timeout=30,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    def _proof(self, base="HEAD", tests=("tests/test_app.py",)):
        return subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "proof_gate.py"),
             "--repo", str(self.repo), "--base", base, "--tests", *tests, "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )

    def test_a_test_that_fails_on_base_and_passes_now_is_proof(self):
        result = self._proof()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["proof"])
        self.assertTrue(payload["fail_to_pass"])
        self.assertEqual(payload["results"][0]["base"]["verdict"], "assertion")
        self.assertEqual(payload["results"][0]["current"]["verdict"], "passed")

    def test_a_mutation_killed_by_the_declared_test_counts(self):
        (self.repo / "app.py").write_text(
            "def add(a, b):\n    return a - b\n", encoding="utf-8"
        )
        (self.repo / "tests" / "test_app.py").write_text(
            "import unittest\n"
            "from app import add\n\n"
            "class TestApp(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n",
            encoding="utf-8",
        )
        self._git("add", "app.py", "tests/test_app.py")
        self._git("commit", "-qm", "mutation base")
        (self.repo / "app.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / "proof_gate.py"),
             "--repo", str(self.repo), "--base", "HEAD",
             "--tests", "tests/test_app.py", "--sources", "app.py",
             "--mutants", "1", "--min-killed", "1", "--require-mutation", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["proof"])
        self.assertEqual(payload["mutation"]["generated"], 1)
        self.assertEqual(payload["mutation"]["killed"], 1)
        self.assertEqual(payload["mutation"]["threshold"], 1)

    def test_a_test_that_already_passed_on_base_is_not_proof(self):
        self._git("add", "app.py")
        self._git("commit", "-qm", "current")
        result = self._proof(base="HEAD")
        # HEAD is now the current tree, so the copied test passes on both sides.
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["proof"])
        self.assertEqual(payload["results"][0]["base"]["verdict"], "passed")

class TestSuiteHygiene(unittest.TestCase):
    """PRINCIPLE-014 R3 and R5 made mechanical (ADR-099). Integration tier: it parses the
    test modules themselves, a whole-repository scan (ADR-128)."""

    NETWORK_MODULES = {"socket", "http", "urllib", "requests", "httpx", "aiohttp"}
    MODULES = ("test_kit.py", "test_integration.py")

    @classmethod
    def setUpClass(cls):
        # Shared, content-keyed parse cache: the codebase-map test parses these files too.
        cls.trees = {name: parse_source((ROOT_DIR / "tests" / name).read_text(encoding="utf-8"), name)
                     for name in cls.MODULES}

    def test_every_test_method_asserts(self):
        silent = []
        for name, tree in self.trees.items():
            for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
                for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")):
                    calls = {c.func.attr for c in ast.walk(fn)
                             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
                    if not any(a.startswith("assert") or a == "fail" for a in calls) and \
                            not any(isinstance(n, ast.Assert) for n in ast.walk(fn)):
                        silent.append(f"{name}:{fn.lineno} {cls.name}.{fn.name}")
        self.assertEqual(silent, [], "a test without an assertion proves nothing (PRINCIPLE-014 R5)")

    def test_no_test_module_imports_a_network_library(self):
        found = []
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                found += [f"{name}: {n}" for n in names if n.split(".")[0] in self.NETWORK_MODULES]
        self.assertEqual(found, [], "tests make no network call (PRINCIPLE-014 R3)")


class TestRepositoryReachability(unittest.TestCase):
    """PRINCIPLE-014 R7 live invariant over the whole repository. Integration tier with the other
    whole-repository scans; the shield's behaviour on fixtures stays in the unit tier (ADR-129)."""

    def test_this_repository_passes_the_shield(self):
        # The live invariant: AIKit's own production modules must stay reachable.
        files = production_modules()
        self.assertGreaterEqual(len(files), 4, "no production modules discovered")
        unreachable = find_unreachable(files)
        self.assertEqual(
            unreachable, [],
            f"Unwired capabilities in scripts/: {unreachable}. Wire them into the path they "
            f"protect, delete them, or allowlist them as deliberate public API.",
        )
        phantom = find_phantom_keys(files)
        self.assertEqual(phantom, [], f"State keys read with no producer: {phantom}")

    def test_allowlist_entries_still_exist(self):
        # An allowlist that outlives its symbols silently stops shielding anything.
        defined = set(collect_definitions(production_modules()))
        stale = sorted(name for name in PUBLIC_API_ALLOWLIST if name not in defined)
        self.assertEqual(
            stale, [],
            f"PUBLIC_API_ALLOWLIST names symbols that no longer exist: {stale}",
        )


class TestRepositorySecretHygiene(unittest.TestCase):
    """PRINCIPLE-019 live invariant. Integration tier: the scan shells out to `git ls-files`."""

    def test_this_repository_is_clean(self):
        # No tracked file or agent memory in AIKit carries a credential.
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = run_scan(mode="all")
        self.assertEqual(exit_code, 0, "secret scan found potential credentials in the repository")


class TestReadmeDriftShield(unittest.TestCase):
    """PRINCIPLE-005 live invariant. Integration tier: completeness shells out to `git ls-files`."""

    def test_this_readme_matches_the_tracked_tree(self):
        from scripts.update_knowledge_base import check_readme
        self.assertEqual(check_readme(ROOT_DIR), [])


class TestTierBudgetDiscipline(unittest.TestCase):
    """
    Structural enforcement of the two-tier test budget (PRINCIPLE-010 R6, PRINCIPLE-014 R3).

    A wall-clock assertion on a 1s budget would itself be flaky on a loaded machine, and flaky
    tests are blocking defects under PRINCIPLE-014 R3. The budget is therefore enforced
    structurally: the unit tier may not spawn processes or sleep on the wall clock, which is
    what keeps it fast by construction. This tier, in turn, must bound every spawn.
    """

    UNIT_MODULE = ROOT_DIR / "tests" / "test_kit.py"

    def test_unit_tier_spawns_no_processes_and_never_sleeps(self):
        source = self.UNIT_MODULE.read_text(encoding="utf-8")
        # Calls, not the module name: test_kit imports subprocess solely to guard against spawns.
        forbidden = {
            "subprocess.run call": r"\bsubprocess\.run\(",
            "Popen call": r"\bPopen\(",
            "os.system call": r"\bos\.system\(",
            "time.sleep call": r"\btime\.sleep\(",
        }
        offenders = [name for name, pat in forbidden.items() if re.search(pat, source)]
        self.assertEqual(
            offenders, [],
            f"{self.UNIT_MODULE.name} is the spawn-free unit tier but references {offenders}; "
            f"move process-spawning or sleeping tests into tests/test_integration.py",
        )

    def test_unit_tier_guards_itself_against_spawns(self):
        # Supersedes a ~1s full re-run of the unit tier under a detector: test_kit now installs a
        # module-level guard that fails any unit test the moment it starts a process, by name.
        source = self.UNIT_MODULE.read_text(encoding="utf-8")
        self.assertIn("def setUpModule():\n    subprocess.Popen.__init__ = _refuse_spawn", source)
        self.assertIn("def tearDownModule():\n    subprocess.Popen.__init__ = _REAL_POPEN_INIT",
                      source)

    def test_integration_tier_bounds_every_spawn(self):
        source = Path(__file__).read_text(encoding="utf-8")
        spawns = len(re.findall(r"subprocess\.(?:run|Popen)\(", source))
        timeouts = len(re.findall(r"timeout=(?:PROC_TIMEOUT|\d+)", source))
        self.assertGreater(spawns, 0, "integration tier should actually spawn processes")
        self.assertGreaterEqual(
            timeouts, spawns,
            "every subprocess in the integration tier must declare an explicit timeout "
            "(PRINCIPLE-010 R3)",
        )


class TestGateCommandLineBreaks(unittest.TestCase):
    """A trailing newline is not a second step, so it still runs (ADR-183)."""

    def test_a_trailing_newline_still_runs_the_command(self):
        from scripts.project_gates import run_shell
        code, output = run_shell("exit 3\n", ROOT_DIR, PROC_TIMEOUT)
        self.assertEqual(code, 3, output)


class TestReportedPathsAreRealPaths(unittest.TestCase):
    """Git quotes spaces and non-ASCII letters; what AIKit reports must name real files (ADR-189)."""

    NAMES = ("şifre_notları.txt", "with space.txt", "plain.txt")

    def test_the_audit_reports_paths_that_exist(self):
        repo = Path(tempfile.mkdtemp(prefix="test_audit_paths_"))
        self.addCleanup(remove_tree, repo)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        for name in self.NAMES:
            (repo / name).write_text("x\n", encoding="utf-8")
        reported = run_disruption_audit(workspace_dir=repo)["untracked_files"]
        self.assertEqual(sorted(reported), sorted(self.NAMES))
        self.assertTrue(all((repo / name).exists() for name in reported))

    def test_the_audit_reads_nul_separated_status_and_a_real_rename(self):
        repo = Path(tempfile.mkdtemp(prefix="test_audit_rename_"))
        self.addCleanup(remove_tree, repo)
        for args in (["init", "-q"], ["config", "user.name", "t"], ["config", "user.email", "t@example.invalid"]):
            subprocess.run(["git", *args], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        (repo / "old name.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        subprocess.run(["git", "mv", "old name.txt", "new name.txt"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        code, stdout, _ = git_porcelain_status(repo)
        self.assertEqual(code, 0)
        self.assertIn("\0", stdout, "the audit must ask git for NUL-separated output")
        self.assertEqual(run_disruption_audit(workspace_dir=repo)["modified_files"],
                         ["old name.txt -> new name.txt"])

    def test_a_project_gate_prints_a_non_ascii_path_as_utf8(self):
        # `aikit check` reads gate output as UTF-8; the hygiene scan wrote the console code page,
        # so şifre_araç.py arrived as replacement characters on Windows.
        folder = Path(tempfile.mkdtemp(prefix="test_hygiene_utf8_"))
        self.addCleanup(remove_tree, folder)
        name = "şifre_araç.py"
        (folder / name).write_text("import os\nos.system('x')\n", encoding="utf-8")
        res = subprocess.run([sys.executable, str(ROOT_DIR / "scripts" / "check_project_hygiene.py"),
                              "--workspace", str(folder)], capture_output=True, timeout=PROC_TIMEOUT,
                             stdin=subprocess.DEVNULL)
        self.assertEqual(res.returncode, 1)
        self.assertIn(name, res.stdout.decode("utf-8", "replace"))


class TestSecretScanSeesNonAsciiPaths(unittest.TestCase):
    """
    git quotes a non-ASCII path ("\\305\\237ifre.txt") unless told otherwise, so `--all` read a
    `.txt"` suffix and skipped the file silently, and diff findings lost their file name (ADR-182).
    """

    # Built at run time so no credential-shaped literal sits in this source file.
    GITHUB = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"
    GITLAB = "glpat-" + "aB3dE5gH7jK9mN1pQ3rS"
    TURKISH = "şifre_notları.txt"

    def make_repo(self) -> Path:
        repo = Path(tempfile.mkdtemp(prefix="test_qpath_"))
        self.addCleanup(remove_tree, repo)
        for args in (["init", "-q"], ["config", "user.name", "t"],
                     ["config", "user.email", "t@example.invalid"]):
            subprocess.run(["git", *args], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        return repo

    def scan(self, repo: Path, mode: str) -> str:
        res = subprocess.run([sys.executable, str(ROOT_DIR / "scripts" / "check_secrets.py"),
                              mode, "--workspace", str(repo)],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=PROC_TIMEOUT, stdin=subprocess.DEVNULL)
        self.assertEqual(res.returncode, 1, res.stdout[-600:])
        return res.stdout

    def test_all_scans_a_tracked_file_whose_name_is_not_ascii(self):
        repo = self.make_repo()
        (repo / "notes.txt").write_text(f'token = "{self.GITHUB}"\n', encoding="utf-8")
        (repo / self.TURKISH).write_text(f'token = "{self.GITHUB}"\n', encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        out = self.scan(repo, "--all")
        self.assertIn("2 potential secret", out, "the non-ASCII file was skipped")
        self.assertIn(self.TURKISH, out)

    def test_staged_findings_name_a_non_ascii_file(self):
        repo = self.make_repo()
        (repo / self.TURKISH).write_text(f'key = "{self.GITLAB}"\n', encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=PROC_TIMEOUT)
        out = self.scan(repo, "--staged")
        self.assertIn(f"{self.TURKISH}:1", out, "the finding lost its file name")


class TestAikitHelpFastPath(unittest.TestCase):
    """`python aikit.py --help` must not load the command layer (PRINCIPLE-010 R5, ADR-180)."""

    def test_help_uses_only_the_generated_help_module(self):
        # -X importtime lists every module the process imported on stderr; usage goes to stdout.
        res = subprocess.run([sys.executable, "-X", "importtime", str(ROOT_DIR / "aikit.py"), "--help"],
                             capture_output=True, text=True, timeout=PROC_TIMEOUT,
                             stdin=subprocess.DEVNULL)
        self.assertEqual(res.returncode, 0, res.stderr[-400:])
        self.assertIn("usage: python aikit.py", res.stdout)
        imported = {line.rsplit("|", 1)[-1].strip() for line in res.stderr.splitlines()
                    if line.startswith("import time:")}
        self.assertIn("scripts.aikit_help", imported)
        self.assertNotIn("scripts.aikit_parser", imported,
                         "--help built the grammar instead of printing the generated text")
        self.assertNotIn("scripts.aikit_cli", imported,
                         "--help loaded the command layer, which imports every AIKit module")

    def test_a_real_command_still_loads_the_command_layer(self):
        res = subprocess.run([sys.executable, "-X", "importtime", str(ROOT_DIR / "aikit.py"), "list"],
                             capture_output=True, text=True, timeout=PROC_TIMEOUT,
                             stdin=subprocess.DEVNULL)
        self.assertEqual(res.returncode, 0, res.stderr[-400:])
        self.assertIn("scripts.aikit_cli", res.stderr)


class TestProjectCreation(unittest.TestCase):
    """`aikit new` makes a separate git repository with its memory (ADR-119)."""

    def test_new_project_is_its_own_clean_repository_with_its_own_ledger(self):
        kit = Path(tempfile.mkdtemp(prefix="test_project_new_"))
        self.addCleanup(remove_tree, kit)
        identity = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        # Commit identity for this test only; git reads it from the environment.
        patcher = mock.patch.dict(os.environ, identity)
        patcher.start()
        self.addCleanup(patcher.stop)
        root = create_project("app", workspace=kit)
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True,
                             text=True, timeout=PROC_TIMEOUT).stdout.strip()
        self.assertEqual(Path(top).resolve(), root.resolve(), "the project is its own repository")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True,
                                text=True, timeout=PROC_TIMEOUT).stdout
        self.assertEqual(status, "", "a new project starts with its memory committed")
        self.assertTrue((root / "README.md").is_file())
        self.assertTrue((root / ".aikit" / "project.json").is_file())
        self.assertTrue((root / ".aikit" / "task_ledger.json").is_file())
        self.assertTrue((root / ".aikit" / "decisions.md").is_file())
        # Clean isolation: no duplicated instruction targets in project repository
        for clutter in ("AGENTS.md", "GEMINI.md", "CLAUDE.md", ".cursorrules", ".github",
                        ".windsurfrules", ".clinerules", ".agents", ".claude"):
            self.assertFalse((root / clutter).exists(), f"redundant clutter found in project: {clutter}")
        # A real CLI process proves `--workspace` wiring; the track is then classified in-process.
        cli = [sys.executable, str(ROOT_DIR / "scripts" / "disruption_recovery.py"), "--workspace", str(root)]
        subprocess.run(cli + ["--checkpoint", "t", "--phase-num", "1", "--desc", "grounding"],
                       capture_output=True, text=True, timeout=PROC_TIMEOUT, check=True)
        self.assertTrue((root / ".aikit" / "task_ledger.json").is_file())
        self.assertFalse((root / ".agents" / "task_ledger.json").exists())
        self.assertEqual(classify_track(collect_working_changes(root))[0], "A",
                         "the project's checkpoint is bookkeeping, not a change")


class TestProjectSelfCheck(unittest.TestCase):
    """`aikit fix` repairs what it can, `aikit check` applies AIKit's guidelines (ADR-124, ADR-128)."""

    def test_fix_then_check_and_the_guidelines_gate_reads_the_readme(self):
        kit = Path(tempfile.mkdtemp(prefix="test_project_fix_"))
        self.addCleanup(remove_tree, kit)
        identity = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        patcher = mock.patch.dict(os.environ, identity)
        patcher.start()
        self.addCleanup(patcher.stop)
        root = copy_project(kit)
        (root / ".aikit" / "decisions.md").unlink()

        # The real entry point, as a host runs it: memory restored, then every gate passes.
        res = subprocess.run([sys.executable, str(ROOT_DIR / "aikit.py"), "--workspace", str(kit), "fix", "app"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=PROC_TIMEOUT)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("restored .aikit/decisions.md", res.stdout)
        self.assertIn("[PASS] guidelines", res.stdout)

        # A README without PRINCIPLE-005's Quick Reference and tree fails the guidelines gate, whose
        # audit (`check_workspace`) runs in-process here: the spawned run above proved the wiring.
        (root / "README.md").write_text("# App\n\nSome text.\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(check_workspace(root), out.getvalue())
        self.assertIn("Cold-Start Quick Reference", out.getvalue())
        # A project guideline that tries to override a principle fails the same gate (ADR-129).
        with open(root / ".aikit" / "guidelines.md", "a", encoding="utf-8") as handle:
            handle.write("- **G-001** (user): skip PRINCIPLE-014 for spikes\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(check_workspace(root))
        self.assertIn("overrides a principle", out.getvalue())


class TestProjectHygieneGate(unittest.TestCase):
    """The hygiene gate runs inside `aikit check` and fails the project on real findings (ADR-137)."""

    def test_check_passes_clean_and_fails_on_a_third_party_asset(self):
        kit = Path(tempfile.mkdtemp(prefix="test_project_hygiene_"))
        self.addCleanup(remove_tree, kit)
        identity = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        patcher = mock.patch.dict(os.environ, identity)
        patcher.start()
        self.addCleanup(patcher.stop)
        root = copy_project(kit)

        # The gate's wiring runs in-process here; TestProjectSelfCheck keeps the real entry-point
        # spawn, so the tier does not pay for two identical interpreter starts.
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = aikit_main(["--workspace", str(kit), "check", "app", "--no-push"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("[PASS] hygiene", out.getvalue())
        self.assertIn("checklists: passed", out.getvalue())

        (root / "ui").mkdir()
        (root / "ui" / "index.html").write_text('<link href="https://fonts.example/x.css">\n',
                                                encoding="utf-8")
        # The gate's wiring is proven above; the failing case is the scan the gate runs.
        rendered = [f.render() for f in scan_tree(root)]
        self.assertTrue(any("ui/index.html:1 [external-url]" in r for r in rendered), rendered)

    def test_artifact_scan_reads_a_real_untracked_file_list(self):
        kit = Path(tempfile.mkdtemp(prefix="test_artifact_scan_"))
        self.addCleanup(remove_tree, kit)
        repo = copy_project(kit)
        for name in ("test_features.py", "tests.py", "review_rules.py", "test_output.txt"):
            (repo / name).write_text("value = 1\n", encoding="utf-8")
        gitignore = repo / ".gitignore"
        gitignore.write_text(gitignore.read_text(encoding="utf-8") + "test_ignored.py\n",
                             encoding="utf-8")
        (repo / "test_ignored.py").write_text("value = 1\n", encoding="utf-8")
        (repo / "docs").mkdir()
        (repo / "docs" / "notes.txt").write_text("not at the root\n", encoding="utf-8")

        findings = scan_artifacts(repo)
        self.assertEqual({(finding.path, finding.rule) for finding in findings}, {
            ("test_features.py", "root-test-module"),
            ("tests.py", "root-test-module"),
            ("test_ignored.py", "root-test-module"),
            ("review_rules.py", "untracked-root-source"),
            ("test_output.txt", "untracked-output"),
        })

    def test_artifact_scan_is_scoped_to_a_subdirectory_workspace(self):
        kit = Path(tempfile.mkdtemp(prefix="test_artifact_nested_"))
        self.addCleanup(remove_tree, kit)
        repo = copy_project(kit)
        nested = repo / "nested"
        nested.mkdir()
        (nested / "test_inner.py").write_text("value = 1\n", encoding="utf-8")
        (repo / "test_outer.py").write_text("value = 1\n", encoding="utf-8")

        findings = scan_artifacts(nested)
        self.assertEqual({(finding.path, finding.rule) for finding in findings},
                         {("test_inner.py", "root-test-module")})


class TestUiContractGate(unittest.TestCase):
    """The UI guard bounds real git changes and proves what it renders (ADR-158, ADR-160)."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="test_ui_gate_base_"))
        cls.identity = mock.patch.dict(os.environ, {
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})
        cls.identity.start()
        (cls.base / ".aikit").mkdir()
        contract = {"schema": 1, "surfaces": {"menu": {"paths": ["src/ui/**"]}},
                    "protected": ["tests/**"], "commands": {"fast": "exit 0"},
                    "limits": {"max_files": 3, "max_lines": 20}}
        (cls.base / ".aikit" / "ui.json").write_text(json.dumps(contract), encoding="utf-8")
        (cls.base / "src" / "ui").mkdir(parents=True)
        (cls.base / "src" / "ui" / "menu.py").write_text("value = 1\n", encoding="utf-8")
        for args in (("init", "-q"), ("config", "user.email", "t@example.com"),
                     ("config", "user.name", "T"), ("add", "-A"), ("commit", "-qm", "base")):
            subprocess.run(["git", *args], cwd=cls.base, timeout=PROC_TIMEOUT, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.identity.stop()
        remove_tree(cls.base)

    def setUp(self):
        root = Path(tempfile.mkdtemp(prefix="test_ui_gate_"))
        self.addCleanup(remove_tree, root)
        shutil.copytree(self.base, root, dirs_exist_ok=True)
        self.root = root

    @staticmethod
    def _canned_runner(command, cwd, timeout):
        """ADR-154 pattern: exercise the contract in-process; one real spawn is covered elsewhere."""
        if "menu.py" in command:
            return 0, (Path(cwd) / "src" / "ui" / "menu.py").read_text(encoding="utf-8")
        return 0, ""

    def test_bounds_edits_and_abort_restores_only_the_surface(self):
        root = self.root
        runner = self._canned_runner
        ui_contract.begin(root, "menu", shell_runner=runner)
        menu = root / "src" / "ui" / "menu.py"
        menu.write_text("value = 2\n", encoding="utf-8")
        (root / "src" / "ui" / "extra.py").write_text("value = 3\n", encoding="utf-8")
        self.assertEqual(ui_contract.verify(root, shell_runner=runner), [])

        (root / "outside.py").write_text("value = 4\n", encoding="utf-8")
        findings = ui_contract.verify(root, shell_runner=runner)
        self.assertTrue(any("path outside surface" in finding for finding in findings), findings)

        result = ui_contract.abort(root)
        self.assertEqual(menu.read_text(encoding="utf-8"), "value = 1\n")
        self.assertFalse((root / "src" / "ui" / "extra.py").exists())
        self.assertTrue((root / "outside.py").exists(), "non-surface work must survive abort")
        self.assertIn("src/ui/menu.py", result["restored"])
        self.assertTrue(Path(result["backup"]).is_dir())
        self.assertFalse((root / ".aikit" / "ui_task.json").exists())


    def test_snapshot_proof_and_style_lint_gate_a_real_edit(self):
        root = self.root
        inventory = ("type src\\ui\\menu.py" if sys.platform == "win32"
                     else "cat src/ui/menu.py")
        contract = {"schema": 1, "surfaces": {"menu": {"paths": ["src/ui/**"]}},
                    "protected": ["tests/**"],
                    "commands": {"fast": "exit 0", "snapshot": inventory},
                    "style": {"theme_paths": ["src/theme.py"]},
                    "limits": {"max_files": 3, "max_lines": 40}}
        (root / ".aikit" / "ui.json").write_text(json.dumps(contract), encoding="utf-8")
        (root / "src" / "theme.py").write_text("ERROR = '#ff0000'\n", encoding="utf-8")
        (root / "src" / "ui" / "menu.py").write_text("Button(save)\nvalue = 1\n",
                                                     encoding="utf-8")
        for args in (("add", "-A"), ("commit", "-qm", "contract")):
            subprocess.run(["git", *args], cwd=root, timeout=PROC_TIMEOUT, check=True)

        ui_contract.begin(root, "menu", shell_runner=self._canned_runner)
        (root / "src" / "ui" / "menu.py").write_text('value = 1\nfg = "#ff0000"\n',
                                                      encoding="utf-8")
        findings = ui_contract.verify(root, shell_runner=self._canned_runner)
        self.assertTrue(any("Button(save)" in finding for finding in findings), findings)
        self.assertIn("style literal '#ff0000' outside theme paths: src/ui/menu.py:2",
                      findings)

        ui_contract.allow(root, "Button*", "the toolbar replaces the button row")
        (root / "src" / "ui" / "menu.py").write_text("value = 1\nfg = theme.ERROR\n",
                                                      encoding="utf-8")
        # The allow-passing and finish-verify assertions live in TestUiContract; this tier keeps
        # the real-git snapshot/style proof and the resulting evidence record.
        with mock.patch("scripts.ui_contract.verify", return_value=[]):
            self.assertEqual(ui_contract.finish(root, reviewed=True, reviewer="yd",
                                                shell_runner=self._canned_runner), [])
        history = json.loads((root / ".aikit" / "ui_history.json").read_text(encoding="utf-8"))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["reviewer"], "yd")
        self.assertFalse((root / ".aikit" / "ui_task.json").exists())


class TestProjectSecretScan(unittest.TestCase):
    """`check_secrets.py --workspace` scans a project's repository, not AIKit's (ADR-121)."""

    def test_scan_reads_the_projects_staged_changes_and_ledger(self):
        kit = Path(tempfile.mkdtemp(prefix="test_project_secrets_"))
        self.addCleanup(remove_tree, kit)
        repo = copy_project(kit)
        # Split so this file itself holds no credential-shaped literal.
        key = "sk-" + "ant-api03-" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefghij"  # aikit:allow-secret
        (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.py"], cwd=repo, timeout=PROC_TIMEOUT, check=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_scan(repo=repo), 0)
        (repo / ".aikit").mkdir(exist_ok=True)
        (repo / ".aikit" / "task_ledger.json").write_text(f'{{"why": "uses {key}"}}', encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(run_scan(repo=repo), 1, "a project's ledger is agent memory too")
        self.assertIn("agent-memory:task_ledger.json", out.getvalue())


class TestProjectGateShell(unittest.TestCase):
    """Gates run through the platform shell in the project folder (ADR-122)."""

    def test_shell_keeps_quotes_and_reports_exit_codes(self):
        folder = Path(tempfile.mkdtemp(prefix="test_gate_shell_"))
        self.addCleanup(remove_tree, folder)
        quoted = f'"{sys.executable}" -c "import os, sys; print(os.getcwd()); sys.exit(3)"'
        results = run_gates(folder, [Gate("q", quoted, "t")], timeout=PROC_TIMEOUT)
        self.assertEqual(results[0].returncode, 3)
        self.assertEqual(Path(results[0].output.strip()).resolve(), folder.resolve())


class TestProjectPublishLifecycle(unittest.TestCase):
    """Publishing visibility and check --no-push with real processes and git checkouts (ADR-134, ADR-135)."""

    def test_project_status_list_repo_and_check_no_push(self):
        kit = Path(tempfile.mkdtemp(prefix="test_project_publish_"))
        self.addCleanup(remove_tree, kit)
        identity = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        patcher = mock.patch.dict(os.environ, identity)
        patcher.start()
        self.addCleanup(patcher.stop)

        root = copy_project(kit)

        def aikit(*argv):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = aikit_main(["--workspace", str(kit), *argv])
            return code, out.getvalue()

        # 1. Status initially shows local only (no remote)
        code, out = aikit("status", "app")
        self.assertEqual(code, 0, out)
        self.assertIn("Repo:      none (local only", out)

        # 1b. A requested push with no remote to push to fails instead of exiting 0 (ADR-192). The
        #     template's filled README is committed first, so the push is not refused as dirty.
        subprocess.run(["git", "commit", "-q", "-am", "docs: fill README"], cwd=root,
                       timeout=PROC_TIMEOUT, check=True)
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = aikit_main(["--workspace", str(kit), "check", "app", "--push"])
        self.assertEqual(code, 1, err.getvalue())
        self.assertIn("no 'origin' remote", err.getvalue())

        # 2. Add an origin remote
        fake_url = "https://github.com/test-owner/test-app.git"
        subprocess.run(["git", "remote", "add", "origin", fake_url], cwd=root, timeout=PROC_TIMEOUT, check=True)

        # 3. Status now reveals the repo URL
        code, out = aikit("status", "app")
        self.assertEqual(code, 0, out)
        self.assertIn(f"Repo:      {fake_url}", out)

        # 4. List also displays the repo URL
        code, out = aikit("list")
        self.assertEqual(code, 0, out)
        self.assertIn(f"repo: {fake_url}", out)

        # 5. Check with --no-push runs gates and succeeds without attempting network push
        code, out = aikit("check", "app", "--no-push")
        self.assertEqual(code, 0, out)
        self.assertIn("gates passed for 'app'", out)
        self.assertNotIn("auto-pushing", out)


class TestProjectPolicyCLI(unittest.TestCase):
    """PRINCIPLE-014: the UI, topic and media commands reach the registry and write real files."""

    def test_ui_topic_and_media_commands_round_trip(self):
        from scripts.project_registry import write_memory

        workspace = Path(tempfile.mkdtemp(prefix="policy_workspace_"))
        self.addCleanup(remove_tree, workspace)
        project = workspace / "projects" / "demo"
        project.mkdir(parents=True)
        write_memory(project, "demo")
        (project / "README.md").write_text(
            "# Demo\n\nA local-first AI agent with a CLI and research notes.\n", encoding="utf-8")
        (project / "index.html").write_text(
            "<!doctype html><html><body><main>demo</main></body></html>", encoding="utf-8")
        (project / "requirements.txt").write_text("requests\n", encoding="utf-8")
        git = lambda *args: subprocess.run(  # noqa: E731
            ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
            cwd=project, capture_output=True, text=True, timeout=PROC_TIMEOUT)
        self.assertEqual(git("init", "-q").returncode, 0)
        self.assertEqual(git("add", "README.md", "index.html", "requirements.txt", ".aikit").returncode, 0)
        self.assertEqual(git("commit", "-q", "-m", "feat: demo").returncode, 0)

        def run(*argv):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = aikit_main(["--workspace", str(workspace), *argv])
            self.assertEqual(code, 0, out.getvalue())
            return json.loads(out.getvalue())

        ui = run("ui-id", "demo", "--set", "auto", "--json")
        self.assertTrue(ui["result"]["has_ui"])
        brief = run("topics", "demo", "--brief", "--offline", "--json")
        self.assertIn("ai-agents", brief["result"]["brief"]["hint_tags"])
        choice_path = workspace / "topics.json"
        choice_path.write_text(json.dumps({"topics": ["aikit", "python", "ai-agents",
                                                      "local-first"]}), encoding="utf-8")
        topics = run("topics", "demo", "--from-file", str(choice_path), "--offline", "--json")
        self.assertEqual(topics["result"]["desired"],
                         ["aikit", "python", "ai-agents", "local-first"])
        media = run("media", "init", "demo", "--json")
        self.assertTrue(media["result"]["has_ui"])
        review = run("media", "review", "demo", "--kind", "logo", "--decision", "approve",
                     "--reviewer", "agent:test", "--method", "structural",
                     "--notes", "monogram and palette match the project", "--json")
        self.assertEqual(review["result"]["status"], "approved")
        run("media", "review", "demo", "--kind", "social_preview", "--decision", "approve",
            "--reviewer", "agent:test", "--method", "structural",
            "--notes", "title and category fit the project", "--json")
        dossier = Path(tempfile.mkdtemp(prefix="policy_dossier_"))
        self.addCleanup(remove_tree, dossier)
        applied = run("media", "apply", "demo", "--dossier", str(dossier), "--json")
        self.assertTrue(applied["result"]["logo"])
        readme = (project / "README.md").read_text(encoding="utf-8")
        self.assertIn("aegean:media:start", readme)
        self.assertNotIn("assets/logo", readme)
        self.assertEqual(readme.count("social-preview"), 1)
        self.assertIn("## 🎨 Brand Assets", readme)
        self.assertIn("ai-generated brand assets", readme.lower())
        self.assertIn("img.shields.io/badge/license-", readme)
        self.assertEqual(readme.count("AIKit Integrated"), 1)
        audit = run("media", "audit", "demo", "--dossier", str(dossier), "--json")
        self.assertTrue(audit["result"]["ok"], audit["result"]["problems"])


class TestReforgeHistory(unittest.TestCase):
    """PRINCIPLE-014: progressive history auditing and repair against real Git commits."""

    IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}

    def git(self, root: Path, *args: str):
        done = subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
            cwd=root, capture_output=True, text=True, timeout=PROC_TIMEOUT,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def repository(self, defects=True) -> Path:
        root = Path(tempfile.mkdtemp(prefix="reforge_history_"))
        self.addCleanup(remove_tree, root)
        self.git(root, "init", "-q")
        app = ("def load(value):\n"
               "    try:\n"
               "        return value\n"
               "    except:\n"
               "        pass\n"
               "    return value\n") if defects else "def load(value):\n    return value\n"
        (root / "app.py").write_text(app, encoding="utf-8")
        self.git(root, "add", "app.py")
        self.git(root, "commit", "-q", "-m", "feat: first")
        (root / "other.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        self.git(root, "add", "other.py")
        self.git(root, "commit", "-q", "-m", "feat: second")
        if defects:
            (root / "app.py").write_text(
                app + "\ndef cache(items=[]):\n    return items\n", encoding="utf-8")
            self.git(root, "add", "app.py")
            self.git(root, "commit", "-q", "-m", "feat: third")
        return root

    def simple_repository(self, commits: int) -> Path:
        """A small clean history for window/run tests that do not need repairs."""
        root = Path(tempfile.mkdtemp(prefix="reforge_simple_"))
        self.addCleanup(remove_tree, root)
        self.git(root, "init", "-q")
        for index in range(commits):
            (root / f"value{index}.py").write_text(f"VALUE = {index}\n", encoding="utf-8")
            self.git(root, "add", f"value{index}.py")
            self.git(root, "commit", "-q", "-m", f"feat: value {index}")
        return root

    def one_commit_repository(self, source: str) -> Path:
        """One commit with one Python file, for a repair test that needs no long history."""
        root = Path(tempfile.mkdtemp(prefix="reforge_one_"))
        self.addCleanup(remove_tree, root)
        self.git(root, "init", "-q")
        (root / "app.py").write_text(source, encoding="utf-8")
        self.git(root, "add", "app.py")
        self.git(root, "commit", "-q", "-m", "feat: initial")
        return root

    def test_stage_one_repairs_and_records_evidence(self):
        from reforge.pipeline import run_pipeline
        from reforge.state import load_state

        root = self.one_commit_repository(
            "def load(value):\n"
            "    try:\n"
            "        return value\n"
            "    except:\n"
            "        pass\n"
            "\n"
            "def cache(items=[]):\n"
            "    return items\n")
        report = run_pipeline(root, "run", run_tests=False, rules=True)
        self.assertEqual(report["stage"], 1)
        self.assertTrue(report["repaired"] >= 2)
        state = load_state(root)
        self.assertEqual(state["stage"], 1)
        self.assertEqual(len(state["audited_commits"]), 1)
        self.assertTrue(all(finding["evidence"] for finding in report["findings"]))
        self.assertTrue((root / "test_reforge_regressions.py").is_file())
        self.assertNotIn("except:", (root / "app.py").read_text(encoding="utf-8"))
        self.assertNotIn("items=[]", (root / "app.py").read_text(encoding="utf-8"))
        generated = subprocess.run([sys.executable, "-m", "unittest", "test_reforge_regressions"],
                                   cwd=root, capture_output=True, text=True, timeout=PROC_TIMEOUT)
        self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
        from reforge.delivery import commit_repairs
        committed = commit_repairs(root, "fix(reforge): repair stage 1 findings")
        self.assertTrue(committed["commit"])
        shown = self.git(root, "show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn("app.py", shown)
        self.assertIn(".aikit/reforge.json", shown)

    def test_a_second_fix_offers_the_reviewed_patch_for_commit(self):
        # `audit` then `fix --findings` leaves a reviewed patch; a second `fix --commit` publishes it
        # instead of refusing, which is what the first fix prints as advice. The tree may also
        # hold another session's work: it must survive and stay out of commit_paths.
        import json as jsonlib

        from reforge.pipeline import run_pipeline

        root = self.one_commit_repository(
            "try:\n    pass\nexcept:\n    pass\n")
        app = root / "app.py"
        app.write_text(app.read_text(encoding="utf-8") + "# another session's note\n",
                       encoding="utf-8")
        notes = root / "notes.txt"
        notes.write_text("not Reforge's work\n", encoding="utf-8")
        audit = run_pipeline(root, "audit", rules=True)
        packet = Path(audit["review"]["packet"]).read_text(encoding="utf-8")
        answer = root / "review.json"
        answer.write_text(jsonlib.dumps({
            "findings": [], "reviewed_hunks": review_attestations(packet),
        }), encoding="utf-8")
        first = run_pipeline(root, "fix", run_tests=False, findings_file=str(answer))
        self.assertTrue(first["repaired"] >= 1)
        self.assertEqual(first["review"]["status"], "reviewed")
        self.assertIn("# another session's note", app.read_text(encoding="utf-8"))
        self.assertEqual(notes.read_text(encoding="utf-8"), "not Reforge's work\n")
        self.assertNotIn("notes.txt", first["commit_paths"])
        second = run_pipeline(root, "fix", run_tests=False)
        self.assertEqual(second["repaired"], first["repaired"])
        self.assertIn("app.py", second["commit_paths"])
        self.assertIn(".aikit/reforge.json", second["commit_paths"])
        before = self.git(root, "status", "--porcelain").stdout
        self.assertIn("app.py", before, "the reviewed patch is still uncommitted before delivery")
        self.assertIn("notes.txt", before, "unrelated work is left for its own author")

    def test_an_audited_project_records_its_run_in_the_task_ledger(self):
        # A cold start reads only the ledger, so an open audit must be visible there without
        # taking over the task the operator is working on (ADR-250).
        import json as jsonlib

        from reforge.pipeline import run_pipeline, start_audit, stop_audit
        from scripts.disruption_recovery import resumable_tasks

        root = Path(tempfile.mkdtemp(prefix="reforge_ledger_"))
        self.addCleanup(remove_tree, root)
        self.git(root, "init", "-q")
        (root / ".aikit").mkdir()
        ledger = root / ".aikit" / "task_ledger.json"
        operator = {"task_id": "operator-task", "status": "in_progress", "owner": "kilo:1",
                    "last_phase": "Planning", "active_phase": 2}
        ledger.write_text(jsonlib.dumps({"version": 1, "active_task": operator,
                                         "checkpoints": []}), encoding="utf-8")
        (root / "app.py").write_text(
            "def cache(items=[]):\n    return items\n", encoding="utf-8")
        self.git(root, "add", ".aikit/task_ledger.json", "app.py")
        self.git(root, "commit", "-q", "-m", "chore: add a ledger and a defect")
        (root / "other.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.git(root, "add", "other.py")
        self.git(root, "commit", "-q", "-m", "feat: add other")
        start_audit(root, start=2, step=2, stop=2)
        report = run_pipeline(root, "run", run_tests=False, rules=True)
        self.assertTrue(report["ledger"]["recorded"], report["ledger"].get("reason"))
        self.assertEqual(report["ledger"]["task_id"], "reforge:run-1")
        data = jsonlib.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(data["active_task"], operator)
        entry = data["checkpoints"][-1]
        self.assertEqual(entry["status"], "in_progress",
                         "an unreviewed stage keeps the run open even at its stop")
        self.assertIn("app.py", entry["files_affected"])

        packet = Path(report["review"]["packet"]).read_text(encoding="utf-8")
        answer = root / "review.json"
        answer.write_text(jsonlib.dumps({
            "findings": [], "reviewed_hunks": review_attestations(packet),
        }), encoding="utf-8")
        reviewed = run_pipeline(root, "fix", run_tests=False, findings_file=str(answer))
        self.assertEqual(reviewed["run_status"], "completed")
        data = jsonlib.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(data["checkpoints"][-1]["status"], "completed",
                         "the review completes the ledger task")
        start_audit(root, start=2, step=1)
        stop_audit(root)
        paused = resumable_tasks(jsonlib.loads(ledger.read_text(encoding="utf-8")))
        self.assertEqual([task["task_id"] for task in paused], ["reforge:run-2"])
        self.assertIn("items=None", (root / "app.py").read_text(encoding="utf-8"),
                      "recording the audit must not break the repair it accompanies")

    def test_a_failing_test_rolls_the_repair_back(self):
        from reforge.errors import ReforgeError
        from reforge.pipeline import run_pipeline

        root = self.one_commit_repository(
            "def load(value):\n    try:\n        return value\n    except:\n        pass\n")
        original = (root / "app.py").read_text(encoding="utf-8")
        with self.assertRaises(ReforgeError):
            run_pipeline(root, "run", test_command="exit 1", rules=True)
        self.assertEqual((root / "app.py").read_text(encoding="utf-8"), original)
        self.assertFalse((root / "test_reforge_regressions.py").exists())

    def test_projects_run_concurrently_and_a_locked_project_refuses_again(self):
        from reforge.locking import lock_path, run_lock
        from reforge.pipeline import run_pipeline

        busy = Path(tempfile.mkdtemp(prefix="reforge_busy_"))
        self.addCleanup(remove_tree, busy)
        roots = [self.simple_repository(1) for _ in range(2)]
        with run_lock(busy):
            with ThreadPoolExecutor(max_workers=2) as pool:
                reports = list(pool.map(
                    lambda root: run_pipeline(root, "audit", run_tests=False), roots))
            done = subprocess.run(
                [sys.executable, "reforge.py", "audit", str(busy), "--json"],
                cwd=ROOT_DIR, capture_output=True, text=True, timeout=PROC_TIMEOUT,
            )
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("Another Reforge operation is active", done.stdout + done.stderr)
        self.assertEqual([report["stage"] for report in reports], [1, 1])
        self.assertEqual([report["run"] for report in reports], ["run-1"] * 2)
        self.assertEqual(len({str(lock_path(root)) for root in roots}), 2)
        for root in roots:
            self.assertTrue((root / ".aikit" / "reforge.json").is_file())

    def test_a_commit_refuses_a_target_that_was_dirty_when_repaired(self):
        from reforge.errors import ReforgeError
        from reforge.pipeline import run_pipeline, start_audit

        root = self.one_commit_repository(
            "def load(value):\n    try:\n        return value\n    except:\n        pass\n")
        app = root / "app.py"
        app.write_text(app.read_text(encoding="utf-8") + "# another session's note\n",
                       encoding="utf-8")
        start_audit(root, start=2, step=1)
        report = run_pipeline(root, "run", run_tests=False, rules=True)
        self.assertTrue(report["repaired"] >= 1)
        with self.assertRaises(ReforgeError):
            run_pipeline(root, "fix", run_tests=False, deliver=True)

    def test_the_packet_shows_each_commit_hunk_in_order(self):
        # Every new commit keeps its own hunks. Collapsing them into one net diff hides the
        # intermediate change and the minute detail a review is meant to catch.
        from reforge.audit import plan_next_stage
        from reforge.pipeline import start_audit
        from reforge.review import packet_text
        from reforge.state import current_run, load_state

        root = Path(tempfile.mkdtemp(prefix="reforge_packet_"))
        self.addCleanup(remove_tree, root)
        self.git(root, "init", "-q")
        (root / "README.md").write_text("State: first\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-q", "-m", "docs: first")
        (root / "README.md").write_text("State: second\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-q", "-m", "docs: second")
        start_audit(root, start=2, step=1)
        run = current_run(load_state(root))
        packet, _ = packet_text(root, plan_next_stage(root, run))
        self.assertIn("State: second", packet)
        self.assertIn("-State: first", packet)
        self.assertNotIn("-State: second", packet, "a later hunk cannot delete its own text")
        self.assertEqual(packet.count("--- README.md"), 2, "every commit hunk appears")
        self.assertEqual(packet.count("### commit "), 2)

    def test_a_findings_file_adds_and_applies_a_validated_fix(self):
        # The host agent reads the packet and returns JSON; a validated replacement becomes a real,
        # reviewable repair, the rule pass can be skipped, and both kinds of finding are kept.
        import json as jsonlib

        from reforge.audit import audit_window, plan_next_stage
        from reforge.pipeline import run_pipeline, start_audit
        from reforge.review import packet_text
        from reforge.state import current_run, load_state

        root = self.one_commit_repository(
            "def add(a, b):\n"
            "    return a - b\n"
            "\n"
            "def load(value):\n"
            "    try:\n"
            "        return value\n"
            "    except:\n"
            "        pass\n")
        start_audit(root, start=2, step=1)
        run = current_run(load_state(root))
        plan = plan_next_stage(root, run)
        rules = audit_window(root, plan, run.get("history") or [], [], [], True)
        self.assertTrue(any(item.code == "bare-except" for item in rules))
        attestations = review_attestations(packet_text(root, plan)[0])
        answer_folder = Path(tempfile.mkdtemp(prefix="reforge_answer_"))
        self.addCleanup(remove_tree, answer_folder)
        answer = answer_folder / "findings.json"
        answer.write_text(jsonlib.dumps({"findings": [
            {"path": "app.py", "line": 2, "severity": "high", "code": "wrong-operator",
             "message": "add() subtracts, so every caller gets the wrong total",
             "evidence": "return a - b",
             "fix": {"old": "return a - b", "new": "return a + b"}},
            {"path": "app.py", "line": 7, "severity": "medium", "kind": "improvement",
             "code": "narrow-the-except", "message": "the handler hides every error type",
             "evidence": "    except:"},
        ], "reviewed_hunks": attestations}), encoding="utf-8")

        audit = run_pipeline(root, "audit", findings_file=str(answer), rules=False,
                             run_tests=False)
        self.assertEqual(audit["review"]["status"], "reviewed")
        self.assertIn("Review one Git audit stage",
                      Path(audit["review"]["packet"]).read_text(encoding="utf-8"))
        report = run_pipeline(root, "fix", run_tests=False, findings_file=str(answer))
        self.assertEqual(report["review"]["status"], "reviewed")
        self.assertIn("return a + b", (root / "app.py").read_text(encoding="utf-8"))
        self.assertEqual(report["repaired"], 1)
        codes = {item["code"] for item in report["findings"]}
        self.assertEqual(codes, {"review-wrong-operator", "review-narrow-the-except"})
        self.assertIn("app.py", report["commit_paths"])

    def test_aikit_reforge_status_reaches_the_registry_and_state(self):
        from scripts.project_registry import write_memory

        workspace = Path(tempfile.mkdtemp(prefix="reforge_kit_"))
        self.addCleanup(remove_tree, workspace)
        project = workspace / "projects" / "demo"
        project.mkdir(parents=True)
        write_memory(project, "demo")
        self.git(project, "init", "-q")
        self.git(project, "config", "user.name", "T")
        self.git(project, "config", "user.email", "t@example.com")
        (project / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.git(project, "add", "app.py")
        self.git(project, "commit", "-q", "-m", "feat: initial")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = aikit_main(["--workspace", str(workspace), "reforge", "status", "demo", "--json"])
        self.assertEqual(code, 0, out.getvalue())
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["project"]["name"] if "project" in payload["result"] else "demo", "demo")
        self.assertEqual(payload["result"]["stage"], 0)


class TestIdeaCatcherCli(unittest.TestCase):
    """PRINCIPLE-011: `aikit.py idea-catcher` reaches the private register in one command."""

    def test_status_reads_the_register_named_by_the_root_override(self):
        register = Path(tempfile.mkdtemp(prefix="idea_kit_"))
        self.addCleanup(remove_tree, register)
        (register / "targets.json").write_text(json.dumps({
            "schema": 1, "targets": [{
                "id": "aikit", "name": "AIKit", "path": "../../", "stack": "stdlib",
                "gate": "tests", "fit": "governance", "added": "2026-10-28",
            }],
        }), encoding="utf-8")
        (register / "ideas.json").write_text('{"schema": 1, "ideas": []}', encoding="utf-8")
        (register / "reviews.json").write_text('{"schema": 1, "repos": {}, "reviews": []}',
                                               encoding="utf-8")
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"IDEA_CATCHER_ROOT": str(register)}), \
                contextlib.redirect_stdout(out):
            code = aikit_main(["idea-catcher", "status"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("0 ideas", out.getvalue())


class TestIdeaAutoRegistration(unittest.TestCase):
    """The CLI, the private register and the generated matrix move together."""

    def register(self):
        from tests.test_auto_register import make_register
        root = Path(tempfile.mkdtemp(prefix="test_auto_register_it_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        make_register(root)
        return root

    def test_sync_cli_registers_and_refreshes_the_matrix(self):
        from idea_catcher import registry
        root = self.register()
        sha = "a" * 40
        with mock.patch("idea_catcher.registry.git_commits",
                        return_value=[(sha, "Implement IDEA-001", "")]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = registry.main(["sync", "--repo", ".", "--project", "demo", "--json"],
                                     root=root)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn('"IDEA-001"', out.getvalue())
        matrix = (root / "MATRIX.md").read_text(encoding="utf-8")
        self.assertIn("IDEA-001", matrix)
        self.assertIn("Integrated", matrix)
        matches, message = registry.matrix_matches(
            root, registry.load_targets(root), registry.load_ideas(root),
            registry.load_reviews(root))
        self.assertTrue(matches, message)

    def test_repo_scan_refreshes_the_matrix(self):
        from idea_catcher import auto_register
        root = self.register()
        sha = "a" * 40
        with mock.patch("idea_catcher.registry.git_commits",
                        return_value=[(sha, "Implement IDEA-001", "")]):
            updated = auto_register.register_from_repo(Path("."), "demo", root=root)
        self.assertEqual([row["id"] for row in updated], ["IDEA-001"])
        self.assertIn("Integrated", (root / "MATRIX.md").read_text(encoding="utf-8"))

    def test_delivered_registration_is_best_effort(self):
        from scripts import aikit_cli
        err = io.StringIO()
        with mock.patch("scripts.aikit_cli._register_delivered_ideas",
                        side_effect=ValueError("bad register")):
            with contextlib.redirect_stderr(err):
                aikit_cli._report_registered_ideas(Path("."), "demo")
        self.assertIn("auto-registration skipped", err.getvalue())

    def test_check_push_reports_registered_ideas(self):
        import argparse
        from scripts import aikit_cli

        project = mock.Mock()
        project.path = Path(tempfile.mkdtemp(prefix="test_check_push_"))
        project.name = "demo"
        self.addCleanup(shutil.rmtree, project.path, ignore_errors=True)
        gate = mock.MagicMock()
        gate.passed = True
        gate.seconds = 0.1
        gate.gate.name = "test"
        gate.gate.source = "detected"
        gate.gate.command = "dummy"
        clean = {"modified_files": [], "untracked_files": [], "conflicted_files": [],
                 "ledger_error": None, "git_missing": False}
        args = argparse.Namespace(name="demo", workspace=Path("."), push=True, strict=False)
        with mock.patch("scripts.aikit_cli.present_project", return_value=project), \
             mock.patch("scripts.aikit_cli.public_remote_refusal", return_value=None), \
             mock.patch("scripts.aikit_cli.run_gates", return_value=[gate]), \
             mock.patch("scripts.aikit_cli.resolve_gates", return_value=[]), \
             mock.patch("scripts.aikit_cli.run_disruption_audit", return_value=clean), \
             mock.patch("scripts.aikit_cli.project_baseline_errors", return_value=[]), \
             mock.patch("scripts.aikit_cli.project_ui.ui_payload", return_value={}), \
             mock.patch("scripts.aikit_cli.load_config", return_value={}), \
             mock.patch("scripts.aikit_cli.is_game_project", return_value=False), \
             mock.patch("scripts.aikit_cli.auto_push_project", return_value=(0, "Pushed")), \
             mock.patch("scripts.aikit_cli._report_registered_ideas") as report:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = aikit_cli.cmd_check(args)
        self.assertEqual(code, 0)
        report.assert_called_once_with(project.path, "demo")

        with mock.patch("scripts.aikit_cli.present_project", return_value=project), \
             mock.patch("scripts.aikit_cli.public_remote_refusal", return_value=None), \
             mock.patch("scripts.aikit_cli.run_gates", return_value=[gate]), \
             mock.patch("scripts.aikit_cli.resolve_gates", return_value=[]), \
             mock.patch("scripts.aikit_cli.run_disruption_audit", return_value=clean), \
             mock.patch("scripts.aikit_cli.project_baseline_errors", return_value=[]), \
             mock.patch("scripts.aikit_cli.project_ui.ui_payload", return_value={}), \
             mock.patch("scripts.aikit_cli.load_config", return_value={}), \
             mock.patch("scripts.aikit_cli.is_game_project", return_value=False), \
             mock.patch("scripts.aikit_cli.auto_push_project", return_value=(1, "Error")), \
             mock.patch("scripts.aikit_cli._report_registered_ideas") as report:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = aikit_cli.cmd_check(args)
        self.assertEqual(code, 1)
        report.assert_not_called()

    def test_publish_reports_registered_ideas_only_after_success(self):
        import argparse
        from scripts import aikit_cli

        root = Path(tempfile.mkdtemp(prefix="test_publish_register_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "README.md").write_text("# demo\n\nA project that builds things.\n",
                                        encoding="utf-8")
        project = mock.Mock()
        project.path = root
        project.name = "demo"
        gate = mock.MagicMock()
        gate.passed = True
        gate.gate.name = "test"
        clean = {"modified_files": [], "untracked_files": [], "conflicted_files": [],
                 "ledger_error": None, "git_missing": False}
        args = argparse.Namespace(name="demo", workspace=Path("."), public=False,
                                  license="keep", owner=None)
        patches = (
            mock.patch("scripts.aikit_cli.present_project", return_value=project),
            mock.patch("scripts.aikit_cli.get_project_repo_url", return_value=""),
            mock.patch("scripts.aikit_cli.project_media.media_blockers", return_value=[]),
            mock.patch("scripts.aikit_cli.extract_readme_description",
                       return_value="A project that builds things."),
            mock.patch("scripts.aikit_cli.license_state",
                       return_value=mock.Mock(kind="AGL-1.1", version="1.1", tier="free")),
            mock.patch("scripts.aikit_cli.suggest_license",
                       return_value={"change_needed": False, "upgrade_available": False,
                                     "kind": "AGL-1.1", "confidence": "high"}),
            mock.patch("scripts.aikit_cli.run_disruption_audit", return_value=clean),
            mock.patch("scripts.aikit_cli.project_baseline_errors", return_value=[]),
            mock.patch("scripts.aikit_cli.run_gates", return_value=[gate]),
            mock.patch("scripts.aikit_cli.resolve_gates", return_value=[]),
            mock.patch("scripts.aikit_cli.load_config", return_value={}),
            mock.patch("scripts.aikit_cli.publish_topics", return_value=["aikit"]),
            mock.patch("scripts.aikit_cli.publish_project", return_value=(0, "Published")),
        )
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            report = stack.enter_context(
                mock.patch("scripts.aikit_cli._report_registered_ideas"))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = aikit_cli.cmd_publish(args)
        self.assertEqual(code, 0)
        report.assert_called_once_with(root, "demo")

        with contextlib.ExitStack() as stack:
            for patcher in patches[:-1]:
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("scripts.aikit_cli.publish_project",
                                           return_value=(1, "Error")))
            report = stack.enter_context(
                mock.patch("scripts.aikit_cli._report_registered_ideas"))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = aikit_cli.cmd_publish(args)
        self.assertEqual(code, 1)
        report.assert_not_called()


class TestFstringsParseOnPython310(unittest.TestCase):
    """
    Since 3.12 (PEP 701) an f-string may reuse its own quote, or hold a backslash or `#`, inside
    `{}`; each is a SyntaxError on 3.10 and 3.11. The AST gate parses with feature_version=(3, 10)
    but on a newer interpreter it accepts quote reuse, so this check reads the source (ADR-188).
    """

    @staticmethod
    def rejected_on_310(src):
        # Lines split once, sliced by the AST's UTF-8 byte offsets: ast.get_source_segment
        # re-splits the whole source on every call, which took ~2s over this repository's tests.
        lines = [line.encode("utf-8") for line in src.splitlines(keepends=True)]

        def segment(node):
            if node.lineno == node.end_lineno:
                return lines[node.lineno - 1][node.col_offset:node.end_col_offset].decode("utf-8")
            return (lines[node.lineno - 1][node.col_offset:]
                    + b"".join(lines[node.lineno:node.end_lineno - 1])
                    + lines[node.end_lineno - 1][:node.end_col_offset]).decode("utf-8")

        found = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.JoinedStr):
                continue
            match = re.match(r"[rRbBuUfF]*('''|\"\"\"|'|\")", segment(node))
            if not match:
                continue
            quote = match.group(1)
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    expr = segment(value.value)
                    if (len(quote) == 1 and quote in expr) or chr(92) in expr or "#" in expr:
                        found.append(f"{value.lineno}: {{{expr}}}")
        return found

    def test_the_check_flags_what_310_rejects_and_nothing_it_accepts(self):
        q, bs = chr(34), chr(92)
        bad = (f"a = f{q}{{x[{q}k{q}]}}{q}\n"                       # f"{x["k"]}"
               f"b = f{q}{{{q}{bs}n{q}.join(y)}}{q}\n")              # f"{"\n".join(y)}"
        good = f"c = f{q}{{x['k']}}{q}\n"                             # f"{x['k']}"
        self.assertEqual(len(self.rejected_on_310(bad)), 2)
        self.assertEqual(self.rejected_on_310(good), [])

    def test_no_fstring_in_aikit_needs_python_312(self):
        files = sorted((ROOT_DIR / "scripts").glob("*.py")) + sorted((ROOT_DIR / "tests").glob("*.py"))
        found = [f"{path.name}:{hit}" for path in files + [ROOT_DIR / "aikit.py"]
                 for hit in self.rejected_on_310(path.read_text(encoding="utf-8"))]
        self.assertEqual(found, [], "these f-strings are SyntaxErrors on Python 3.10 and 3.11")


if __name__ == "__main__":
    unittest.main()
