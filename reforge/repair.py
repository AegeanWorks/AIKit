"""Smallest-safe automatic repairs, generated regression tests and repair verification."""

import ast
import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from reforge.errors import ReforgeError
from reforge.model import Finding, Repair


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    text: str
    priority: int = 0


def _lines(text: str) -> List[str]:
    return text.splitlines(keepends=True)


def _newline(text: str) -> str:
    """The file's own line ending, so a repair never rewrites untouched lines."""
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _offset(lines: Sequence[str], line: int, column: int) -> int:
    return sum(len(item) for item in lines[:max(0, line - 1)]) + column


def _default_constructor(node: ast.AST) -> str:
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Set):
        return "set"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id
    return "list"


def _locate(tree: ast.Module, finding: Finding) -> Optional[ast.AST]:
    nodes = [node for node in ast.walk(tree) if getattr(node, "lineno", None) == finding.line]
    if finding.code == "bare-except":
        return next((n for n in nodes if isinstance(n, ast.ExceptHandler) and n.type is None), None)
    if finding.code == "mutable-default":
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != finding.symbol:
                continue
            positional = list(getattr(node.args, "posonlyargs", [])) + list(node.args.args)
            defaults = list(zip(positional[-len(node.args.defaults):], node.args.defaults))
            defaults += list(zip(node.args.kwonlyargs,
                                 [d for d in node.args.kw_defaults if d is not None]))
            for arg, default in defaults:
                if default.lineno == finding.line:
                    return _MutableDefault(node, arg, default)
        return None
    if finding.code == "unsafe-yaml-load":
        return next((n for n in nodes if isinstance(n, ast.Call)
                     and _call_name(n) in {"yaml.load", "yaml.unsafe_load"}), None)
    if finding.code in {"verify-false", "shell-true"}:
        wanted = "verify" if finding.code == "verify-false" else "shell"
        return next((n for n in nodes if isinstance(n, ast.Call)
                     and any(k.arg == wanted for k in n.keywords)), None)
    return nodes[0] if nodes else None


@dataclass(frozen=True)
class _MutableDefault:
    function: ast.AST
    argument: ast.arg
    default: ast.AST


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        base = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
        return f"{base}.{node.func.attr}" if base else node.func.attr
    return ""


def _bare_except_edit(text: str, lines: Sequence[str], node: ast.ExceptHandler) -> Optional[_Edit]:
    line = node.lineno
    if not 1 <= line <= len(lines):
        return None
    original = lines[line - 1].rstrip("\r\n")
    match = re.match(r"^(\s*)except\s*:", original)
    if not match:
        return None
    start = _offset(lines, line, 0)
    rest = original[match.end():]
    return _Edit(start, start + len(original), f"{match.group(1)}except Exception:{rest}")


def _yaml_edit(text: str, lines: Sequence[str], node: ast.Call) -> _Edit:
    start = _offset(lines, node.func.lineno, node.func.col_offset)
    end = _offset(lines, node.func.end_lineno, node.func.end_col_offset)
    return _Edit(start, end, "yaml.safe_load")


def _remove_keyword(text: str, lines: Sequence[str], node: ast.Call, name: str) -> Optional[_Edit]:
    keyword = next((item for item in node.keywords if item.arg == name), None)
    if keyword is None:
        return None
    start = _offset(lines, keyword.lineno, keyword.col_offset)
    end = _offset(lines, keyword.end_lineno, keyword.end_col_offset)
    after = end
    while after < len(text) and text[after] in " \t":
        after += 1
    if text[after:after + 1] == ",":
        end = after + 1
        while end < len(text) and text[end] in " \t\r\n":
            end += 1
    else:
        before = start - 1
        while before >= 0 and text[before] in " \t":
            before -= 1
        if text[before:before + 1] == ",":
            start = before
    return _Edit(start, end, "")


def _mutable_default_edits(lines: Sequence[str], located: _MutableDefault,
                           newline: str = "\n") -> List[_Edit]:
    default = located.default
    start = _offset(lines, default.lineno, default.col_offset)
    end = _offset(lines, default.end_lineno, default.end_col_offset)
    function = located.function
    body = list(function.body)
    index = 1 if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
        and isinstance(body[0].value.value, str) else 0
    if index >= len(body):
        return [_Edit(start, end, "None")]
    first = body[index]
    if first.lineno == getattr(function, "lineno", 0):
        # A one-line `def f(x=[]): return x` has no separate line to insert a guard before.
        return []
    line_text = lines[first.lineno - 1] if first.lineno <= len(lines) else ""
    indent = line_text[:len(line_text) - len(line_text.lstrip())]
    guard = (f"{indent}if {located.argument.arg} is None:{newline}"
             f"{indent}    {located.argument.arg} = {_default_constructor(default)}(){newline}")
    guard_at = _offset(lines, first.lineno, 0)
    return [_Edit(start, end, "None"), _Edit(guard_at, guard_at, guard, priority=1)]


def _edits_for(text: str, finding: Finding, tree: ast.Module) -> List[_Edit]:
    located = _locate(tree, finding)
    if located is None:
        return []
    lines = _lines(text)
    if finding.code == "bare-except" and isinstance(located, ast.ExceptHandler):
        edit = _bare_except_edit(text, lines, located)
        return [edit] if edit else []
    if finding.code == "mutable-default" and isinstance(located, _MutableDefault):
        return _mutable_default_edits(lines, located, _newline(text))
    if finding.code == "unsafe-yaml-load" and isinstance(located, ast.Call):
        return [_yaml_edit(text, lines, located)]
    if finding.code == "verify-false" and isinstance(located, ast.Call):
        edit = _remove_keyword(text, lines, located, "verify")
        return [edit] if edit else []
    if finding.code == "shell-true" and isinstance(located, ast.Call):
        first = located.args[0] if located.args else None
        if not isinstance(first, (ast.List, ast.Tuple)):
            return []
        edit = _remove_keyword(text, lines, located, "shell")
        return [edit] if edit else []
    return []


def _apply_edits(text: str, edits: Sequence[_Edit]) -> str:
    inserts: Dict[int, List[str]] = {}
    replaced: List[_Edit] = []
    for edit in edits:
        if edit.start == edit.end:
            inserts.setdefault(edit.start, []).append(edit.text)
        else:
            replaced.append(edit)
    combined: List[_Edit] = list(replaced)
    combined += [_Edit(start, start, "".join(items)) for start, items in inserts.items()]
    for edit in sorted(combined, key=lambda item: (item.start, item.end), reverse=True):
        text = text[:edit.start] + edit.text + text[edit.end:]
    return text


def _secret_hits(label: str, text: str) -> Sequence[Tuple[str, int, str, str]]:
    try:
        from scripts.check_secrets import scan_text
    except ImportError:
        return []
    return scan_text(label, text)


def _write_text(path: Path, text: str, newline: Optional[str] = None) -> None:
    try:
        from scripts.update_knowledge_base import write_generated_file
    except ImportError:
        _local_atomic_write(path, text, newline)
        return
    write_generated_file(path, text, newline=newline)


def _local_atomic_write(path: Path, text: str, newline: Optional[str] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp_{os.getpid()}_{int(time.time() * 1000)}")
    try:
        with open(tmp, "w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:  # hygiene: allow temp cleanup cannot fail the completed write
                pass


TEST_HEADER = '''"""Regression tests generated by Aegean Reforge; each one pins a repaired defect."""

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent{depth}


class ReforgeRegressionTests(unittest.TestCase):
'''


def _test_method_name(code: str, path: str) -> str:
    digest = hashlib.sha1(f"{code}:{path}".encode("utf-8")).hexdigest()[:8]
    return f"test_{code.replace('-', '_')}_{digest}"


def _test_body(code: str, relative: str) -> str:
    source = f'source = (REPO / {relative!r}).read_text(encoding="utf-8")'
    if code == "bare-except":
        check = ('bad = [n.lineno for n in ast.walk(ast.parse(source)) '
                 'if isinstance(n, ast.ExceptHandler) and n.type is None]\n'
                 '        self.assertEqual(bad, [], "a bare except came back")')
    elif code == "mutable-default":
        check = ('tree = ast.parse(source)\n'
                 '        bad = []\n'
                 '        for node in ast.walk(tree):\n'
                 '            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):\n'
                 '                for default in list(node.args.defaults) + [d for d in node.args.kw_defaults if d]:\n'
                 '                    if isinstance(default, (ast.List, ast.Dict, ast.Set)) or (\n'
                 '                            isinstance(default, ast.Call) and isinstance(default.func, ast.Name)\n'
                 '                            and default.func.id in {"list", "dict", "set"}):\n'
                 '                        bad.append(node.lineno)\n'
                 '        self.assertEqual(bad, [], "a shared mutable default came back")')
    elif code == "unsafe-yaml-load":
        check = ('bad = []\n'
                 '        for node in ast.walk(ast.parse(source)):\n'
                 '            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in '
                 '{"load", "unsafe_load"} and getattr(node.func.value, "id", "") == "yaml":\n'
                 '                bad.append(node.lineno)\n'
                 '        self.assertEqual(bad, [], "an unsafe YAML load came back")')
    elif code == "verify-false":
        check = ('bad = []\n'
                 '        for node in ast.walk(ast.parse(source)):\n'
                 '            if isinstance(node, ast.Call) and any(k.arg == "verify" and '
                 'isinstance(k.value, ast.Constant) and k.value.value is False for k in node.keywords):\n'
                 '                bad.append(node.lineno)\n'
                 '        self.assertEqual(bad, [], "TLS verification was disabled again")')
    elif code == "shell-true":
        check = ('bad = []\n'
                 '        for node in ast.walk(ast.parse(source)):\n'
                 '            if isinstance(node, ast.Call) and any(k.arg == "shell" and '
                 'isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):\n'
                 '                bad.append(node.lineno)\n'
                 '        self.assertEqual(bad, [], "shell=True came back")')
    else:
        return ""
    return f"{source}\n        {check}"


def regression_test_path(root: Path) -> Path:
    tests = root / "tests"
    if tests.is_dir():
        return tests / "test_reforge_regressions.py"
    return root / "test_reforge_regressions.py"


def _add_regression_tests(root: Path, repairs: Sequence[Repair]) -> List[Repair]:
    path = regression_test_path(root)
    # TEST_HEADER already ends in `.parent`; a test module under tests/ needs one more.
    depth = ".parent" if path.parent.name == "tests" else ""
    text = path.read_text(encoding="utf-8") if path.is_file() else TEST_HEADER.format(depth=depth)
    if "class ReforgeRegressionTests" not in text:
        raise ReforgeError(
            f"{path} exists but is not a Reforge regression module.",
            "Reforge appends its generated tests to that exact file and will not overwrite "
            "a module it does not own.",
            "move or rename the existing file, then run the repair again; no source was committed.",
        )
    updated = text
    tests: List[Repair] = []
    for repair in repairs:
        if not repair.applied:
            tests.append(repair)
            continue
        name = _test_method_name(repair.code, repair.path)
        body = _test_body(repair.code, repair.path)
        if body and name not in updated:
            updated = updated.rstrip("\n") + (
                f"\n\n    def {name}(self):\n"
                f"        {body}\n"
            )
        tests.append(Repair(repair.code, repair.path, repair.line, repair.summary, name, True))
    if updated != text:
        hits = _secret_hits(str(path), updated)
        if hits:
            raise ReforgeError(
                f"The generated regression test would contain credential-shaped text ({hits[0][2]}).",
                "PRINCIPLE-019 treats a written credential as already leaked.",
                "rename the finding path or remove the literal from the source, then retry; "
                "no test file was written.",
            )
        _write_text(path, updated)
    return tests


def repair_findings(root: Path, findings: Sequence[Finding],
                    add_tests: bool = True) -> List[Repair]:
    """Apply safe repairs per file, then add one regression test per repaired rule and file."""
    root = Path(root)
    by_path: Dict[str, List[Finding]] = {}
    for finding in findings:
        if finding.fixable:
            by_path.setdefault(finding.path, []).append(finding)
    repairs: List[Repair] = []
    for relative, items in sorted(by_path.items()):
        path = root / relative
        try:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                text = handle.read()
            tree = ast.parse(text)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            repairs.extend(Repair(item.code, relative, item.line, f"not repaired: {exc}", "", False)
                           for item in items)
            continue
        edits: List[_Edit] = []
        edited: List[Finding] = []
        for finding in sorted(items, key=lambda item: item.line, reverse=True):
            made = _edits_for(text, finding, tree)
            if not made:
                repairs.append(Repair(finding.code, relative, finding.line,
                                      "left for review: no safe automatic edit", "", False))
                continue
            edited.append(finding)
            edits.extend(made)
        if not edits:
            continue
        new_text = _apply_edits(text, edits)
        try:
            ast.parse(new_text, filename=relative)
        except SyntaxError as exc:
            repairs.extend(Repair(item.code, relative, item.line,
                                  f"not repaired: edit did not parse ({exc.msg})", "", False)
                           for item in edited)
            continue
        if _secret_hits(relative, new_text):
            repairs.extend(Repair(item.code, relative, item.line,
                                  "not repaired: the edit would write credential-shaped text", "", False)
                           for item in edited)
            continue
        if new_text == text:
            repairs.extend(Repair(item.code, relative, item.line,
                                  "left for review: the edit changed nothing", "", False)
                           for item in edited)
            continue
        _write_text(path, new_text, newline="")
        for item in edited:
            repairs.append(Repair(item.code, relative, item.line,
                                  f"repaired {item.code}", "", True))
    repairs = [item for item in repairs if item.applied or item.summary.startswith(("left", "not "))]
    if add_tests and any(item.applied for item in repairs):
        repairs = _add_regression_tests(root, repairs)
    return repairs


def apply_text_patches(root: Path, findings: Sequence[Finding]) -> List[Repair]:
    """Apply reviewed exact replacements, one per finding, only when each is unambiguous.

    A patch is text, so it is applied to the file's own line endings without normalising anything
    else. When any replacement for a file fails (the quoted text vanished or appears twice, or a
    Python result would not parse) nothing is written for that file and every finding there is
    reported as left for review.
    """
    root = Path(root)
    by_path: Dict[str, List[Finding]] = {}
    for finding in findings:
        if finding.patch_old:
            by_path.setdefault(finding.path, []).append(finding)
    applied: List[Repair] = []
    for relative, items in sorted(by_path.items()):
        path = root / relative
        try:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                original = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            applied.extend(Repair(item.code, relative, item.line,
                                  f"not repaired: the file cannot be read ({exc})", "", False)
                           for item in items)
            continue
        updated = original
        made: List[Repair] = []
        failed = False
        for finding in sorted(items, key=lambda item: item.line, reverse=True):
            old, new = finding.patch_old, finding.patch_new
            count = updated.count(old) if old else 0
            if count != 1:
                made.append(Repair(finding.code, relative, finding.line,
                                   f"not repaired: the quoted text occurs {count} times", "", False))
                failed = True
                continue
            candidate = updated.replace(old, new, 1)
            if relative.lower().endswith(".py"):
                try:
                    ast.parse(candidate, filename=relative)
                except SyntaxError as exc:
                    made.append(Repair(finding.code, relative, finding.line,
                                       f"not repaired: the patch does not parse ({exc.msg})", "", False))
                    failed = True
                    continue
            if candidate == updated:
                made.append(Repair(finding.code, relative, finding.line,
                                   "not repaired: the patch changed nothing", "", False))
                failed = True
                continue
            updated = candidate
            made.append(Repair(finding.code, relative, finding.line,
                               f"applied review suggestion: {finding.message[:80]}", "", True))
        if failed or updated == original:
            for item in made:
                applied.append(
                    Repair(item.code, item.path, item.line,
                           "left for review: the file held an unusable reviewed patch", "", False)
                    if item.applied else item)
            continue
        _write_text(path, updated, newline="")
        applied.extend(made)
    return applied


def repair_paths(repairs: Sequence[Repair], root: Path) -> List[str]:
    """The source and test paths a repair touched, for an explicit commit and patch review."""
    paths = {item.path for item in repairs if item.applied}
    if any(item.test_name for item in repairs):
        test_file = regression_test_path(Path(root))
        try:
            paths.add(str(test_file.relative_to(root)).replace("\\", "/"))
        except ValueError:  # hygiene: allow the generated test file is always under root
            pass
    return sorted(paths)
