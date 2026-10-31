"""Unit tests for automatic idea registration from commit messages."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from idea_catcher import auto_register, registry


def make_register(root: Path, status: str = "Proposed", target: str = "demo") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "targets.json").write_text(json.dumps({
        "schema": 1,
        "targets": [{"id": target, "name": "Demo", "path": "../demo", "stack": "python",
                     "gate": "tests", "fit": "x", "added": "2026-10-29"}],
    }), encoding="utf-8")
    dossiers = root / "dossiers"
    dossiers.mkdir(exist_ok=True)
    (dossiers / "demo.md").write_text(
        f"### `IDEA-001`: Demo idea\n- **Target Project**: `{target}`\n- **Source**: test\n",
        encoding="utf-8",
    )
    (root / "ideas.json").write_text(json.dumps({
        "schema": 1,
        "ideas": [{"id": "IDEA-001", "dossier": "dossiers/demo.md", "concept": "Demo idea",
                   "target": target, "impact": "High", "effort": "Low", "status": status,
                   "tags": ["unverified"]}],
    }), encoding="utf-8")
    (root / "reviews.json").write_text(
        json.dumps({"schema": 1, "reviews": [], "repos": {}}), encoding="utf-8")
    return root


class TestAutoRegister(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="test_auto_register_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        make_register(self.root)
        self.sha = "a" * 40

    def test_commit_reference_marks_the_matching_idea_integrated(self):
        updated = auto_register.register_from_commits(
            self.root, "demo", [(self.sha, "Implement IDEA-001", "")])
        self.assertEqual([row["id"] for row in updated], ["IDEA-001"])
        idea = json.loads((self.root / "ideas.json").read_text(encoding="utf-8"))["ideas"][0]
        self.assertEqual(idea["status"], "Integrated")
        self.assertIn(self.sha, idea["evidence"])
        self.assertIn("Implement IDEA-001", idea["reason"])

    def test_running_twice_is_idempotent(self):
        auto_register.register_from_commits(self.root, "demo", [(self.sha, "IDEA-001", "")])
        again = auto_register.register_from_commits(self.root, "demo", [(self.sha, "IDEA-001", "")])
        self.assertEqual(again, [])

    def test_a_different_target_is_untouched(self):
        updated = auto_register.register_from_commits(
            self.root, "other", [(self.sha, "Implement IDEA-001", "")])
        self.assertEqual(updated, [])
        idea = json.loads((self.root / "ideas.json").read_text(encoding="utf-8"))["ideas"][0]
        self.assertEqual(idea["status"], "Proposed")

    def test_body_references_are_read_and_dry_run_does_not_write(self):
        updated = auto_register.register_from_commits(
            self.root, "demo", [(self.sha, "Work", "implements IDEA-001")], dry_run=True)
        self.assertEqual([row["id"] for row in updated], ["IDEA-001"])
        idea = json.loads((self.root / "ideas.json").read_text(encoding="utf-8"))["ideas"][0]
        self.assertEqual(idea["status"], "Proposed")

    def test_idea_ids_are_deduplicated(self):
        self.assertEqual(auto_register.parse_idea_ids("IDEA-001 IDEA-001 IDEA-002"),
                         ["IDEA-001", "IDEA-002"])

    def test_git_log_records_are_parsed_without_spawning(self):
        done = mock.Mock(returncode=0, stdout=(
            f"{self.sha}\x1fImplement IDEA-001\x1fbody\x1e"), stderr="")
        with mock.patch("idea_catcher.registry.subprocess.run", return_value=done):
            commits = auto_register.git_commits(Path("."))
        self.assertEqual(commits, [(self.sha, "Implement IDEA-001", "body")])

    def test_a_git_timeout_is_a_reported_value_error(self):
        with mock.patch("idea_catcher.registry.subprocess.run",
                        side_effect=subprocess.TimeoutExpired(["git", "log"], 30)):
            with self.assertRaises(ValueError) as raised:
                auto_register.git_commits(Path("."))
        self.assertIn("git log failed", str(raised.exception))

    def test_a_dry_run_does_not_write_the_matrix(self):
        with mock.patch("idea_catcher.registry.git_commits",
                        return_value=[(self.sha, "Implement IDEA-001", "")]):
            updated = auto_register.register_from_repo(
                Path("."), "demo", root=self.root, dry_run=True)
        self.assertEqual([row["id"] for row in updated], ["IDEA-001"])
        self.assertFalse((self.root / "MATRIX.md").exists())

    def test_a_corrupt_register_is_reported_instead_of_ignored(self):
        (self.root / "ideas.json").write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            auto_register.register_from_commits(
                self.root, "demo", [(self.sha, "Implement IDEA-001", "")])

class TestIdeaIdWidth(unittest.TestCase):
    """The register must keep accepting ids after the three-digit range is exhausted."""

    def test_four_digit_commit_references_are_parsed(self):
        self.assertEqual(auto_register.parse_idea_ids("IDEA-1000 IDEA-999"),
                         ["IDEA-1000", "IDEA-999"])

    def test_four_digit_dossier_heading_is_catalogued(self):
        text = ("### `IDEA-1000`: Fourth digit\n"
                "- **Target Project**: `demo`\n"
                "- **Source**: test\n")
        sections = registry.parse_dossier_sections(text)
        self.assertIn("IDEA-1000", sections)
        self.assertEqual(sections["IDEA-1000"].title, "Fourth digit")

    def test_four_digit_matrix_row_is_recognized(self):
        self.assertIsNotNone(registry.MATRIX_ROW_RE.search("| `IDEA-1000` | x |"))

    def test_four_digit_idea_id_is_valid(self):
        self.assertIsNotNone(registry.IDEA_ID_RE.match("IDEA-1000"))
        self.assertEqual(registry.idea_number("IDEA-1000"), 1000)


if __name__ == "__main__":
    unittest.main()
