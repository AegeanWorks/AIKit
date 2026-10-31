"""AST detectors for the defect, security and reliability classes Reforge can evidence."""

import ast
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from reforge.model import Finding


@dataclass(frozen=True)
class Rule:
    """Catalogue entry: what a code means and whether a safe repair exists."""

    code: str
    category: str
    severity: str
    message: str
    fixable: bool = False


RULES: Dict[str, Rule] = {
    "syntax-error": Rule("syntax-error", "defect", "high", "the file does not parse"),
    "bare-except": Rule("bare-except", "reliability", "high",
                        "a bare except catches every exception, including SystemExit", True),
    "swallowed-exception": Rule("swallowed-exception", "reliability", "high",
                                "an exception handler discards the error silently"),
    "mutable-default": Rule("mutable-default", "defect", "high",
                            "a mutable default is shared by every call", True),
    "eval-exec": Rule("eval-exec", "security", "high",
                      "eval/exec executes arbitrary code"),
    "os-system": Rule("os-system", "security", "high",
                      "os.system runs through a shell and cannot be bounded"),
    "shell-true": Rule("shell-true", "security", "high",
                       "shell=True turns arguments into a shell program", True),
    "verify-false": Rule("verify-false", "security", "high",
                         "TLS verification is disabled", True),
    "unsafe-yaml-load": Rule("unsafe-yaml-load", "security", "high",
                             "yaml.load without a safe Loader can build objects", True),
    "unsafe-pickle-load": Rule("unsafe-pickle-load", "security", "high",
                               "pickle.loads executes data as code"),
    "tempfile-mktemp": Rule("tempfile-mktemp", "security", "medium",
                            "mktemp has a race between name and open"),
    "hardcoded-secret": Rule("hardcoded-secret", "security", "high",
                             "a credential-shaped literal is stored in source"),
    "subprocess-timeout": Rule("subprocess-timeout", "reliability", "medium",
                               "a subprocess call has no timeout"),
    "network-timeout": Rule("network-timeout", "reliability", "medium",
                            "an HTTP call has no timeout"),
    "unmanaged-open": Rule("unmanaged-open", "reliability", "medium",
                           "open() is not used as a context manager"),
    "environ-index": Rule("environ-index", "reliability", "medium",
                          "os.environ[...] crashes on a missing variable"),
    "duplicate-key": Rule("duplicate-key", "defect", "medium",
                          "a dictionary literal defines one key twice"),
    "division-by-zero": Rule("division-by-zero", "defect", "high",
                             "a literal zero divisor raises at runtime"),
    "unreachable-code": Rule("unreachable-code", "defect", "low",
                             "code after a terminal statement cannot run"),
    "return-in-finally": Rule("return-in-finally", "defect", "medium",
                              "return in finally replaces an exception"),
    "chmod-777": Rule("chmod-777", "security", "medium",
                      "world-writable permissions are granted"),
    "merge-conflict-marker": Rule("merge-conflict-marker", "defect", "high",
                                  "a merge conflict marker was committed"),
    "invalid-json": Rule("invalid-json", "defect", "high",
                         "the file does not parse as JSON"),
    "invalid-toml": Rule("invalid-toml", "defect", "high",
                         "the file does not parse as TOML"),
    "unclosed-code-fence": Rule("unclosed-code-fence", "defect", "medium",
                                "a Markdown code fence is never closed"),
}

SUBPROCESS_CALLS = {"run", "call", "check_call", "check_output"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "request"}
SECRET_NAMES = ("password", "passwd", "secret", "api_key", "apikey", "access_token",
                "auth_token", "private_key", "credential")
PLACEHOLDERS = {"", "changeme", "placeholder", "redacted", "<redacted>", "example"}


def parse_source(source: str, path: str) -> ast.Module:
    """Parse with the running grammar; raises SyntaxError, never guesses a fix."""
    return ast.parse(source, filename=path)


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _snippet(lines: Sequence[str], line: int) -> str:
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()[:160]
    return ""


def _function_ranges(tree: ast.Module) -> List[Tuple[str, int, int]]:
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            ranges.append((node.name, start, getattr(node, "end_lineno", node.lineno) or node.lineno))
    return ranges


def symbol_at(tree: ast.Module, line: int) -> str:
    """The innermost function or class containing `line`, for interaction evidence."""
    candidates = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            if node.lineno <= line <= end:
                candidates.append((end - node.lineno, node.name))
    return sorted(candidates)[0][1] if candidates else ""


def symbols_in_source(source: str) -> List[Tuple[str, int, int]]:
    return _function_ranges(ast.parse(source))


ALLOW_MARKER = re.compile(r"hygiene:\s*allow\s+\S{3,}")


def allow_marker(lines: Sequence[str], line: int) -> bool:
    """Whether the project marked this line as a deliberate finding.

    AIKit's own hygiene scan accepts `hygiene: allow <reason>` on the finding's line or the line
    directly above it (ADR-147). Reforge honours the same marker so a reviewed, documented decision
    is not reported again as a defect. One line above only, never further: a marker cannot drift
    away from what it excuses.
    """
    if not 1 <= line <= len(lines):
        return False
    if ALLOW_MARKER.search(lines[line - 1]):
        return True
    return line >= 2 and bool(ALLOW_MARKER.search(lines[line - 2]))


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, commit: str, lines: Sequence[str]) -> None:
        self.path = path
        self.commit = commit
        self.lines = lines
        self.findings: List[Finding] = []
        self.tree: Optional[ast.Module] = None
        self.managed: set = set()

    def add(self, code: str, node: ast.AST, line: Optional[int] = None,
            symbol: str = "", reproducible: bool = False) -> None:
        rule = RULES[code]
        where = line or getattr(node, "lineno", 1)
        self.findings.append(Finding(
            code=code,
            category=rule.category,
            severity=rule.severity,
            path=self.path,
            line=int(where),
            message=rule.message,
            evidence=f"{self.path}:{where}: {_snippet(self.lines, int(where))}",
            commit=self.commit,
            symbol=symbol or (symbol_at(self.tree, int(where)) if self.tree else ""),
            reproducible=reproducible,
            fixable=rule.fixable,
        ))

    def _visit_function(self, node) -> None:
        pairs: List[Tuple[ast.arg, ast.AST]] = []
        positional = list(getattr(node.args, "posonlyargs", [])) + list(node.args.args)
        if node.args.defaults:
            pairs += list(zip(positional[-len(node.args.defaults):], node.args.defaults))
        pairs += list(zip(node.args.kwonlyargs,
                          [d for d in node.args.kw_defaults if d is not None]))
        for arg, default in pairs:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.add("mutable-default", default, symbol=node.name, reproducible=True)
            elif (isinstance(default, ast.Call) and isinstance(default.func, ast.Name)
                  and default.func.id in {"list", "dict", "set"}):
                self.add("mutable-default", default, symbol=node.name, reproducible=True)
        self.generic_visit(node)

    def visit_FunctionDef(self, node) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node) -> None:
        self._visit_function(node)

    def visit_ExceptHandler(self, node) -> None:
        if node.type is None:
            self.add("bare-except", node)
        body = [item for item in node.body if not isinstance(item, ast.Pass)]
        if not body:
            self.add("swallowed-exception", node)
        self.generic_visit(node)

    def visit_With(self, node) -> None:
        for item in node.items:
            self.managed.update(id(call) for call in ast.walk(item.context_expr)
                                if isinstance(call, ast.Call))
        self.generic_visit(node)

    def visit_AsyncWith(self, node) -> None:
        self.visit_With(node)

    def visit_BinOp(self, node) -> None:
        if (isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod))
                and isinstance(node.right, ast.Constant) and node.right.value == 0):
            self.add("division-by-zero", node, line=node.right.lineno, reproducible=True)
        self.generic_visit(node)

    def visit_Dict(self, node) -> None:
        seen = set()
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, (str, int)):
                if key.value in seen:
                    self.add("duplicate-key", key)
                seen.add(key.value)
        self.generic_visit(node)

    def visit_Try(self, node) -> None:
        if any(isinstance(item, (ast.Return, ast.Raise)) for item in node.finalbody):
            self.add("return-in-finally", node)
        self.generic_visit(node)

    def visit_Subscript(self, node) -> None:
        if (isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Attribute)
                and node.value.attr == "environ"
                and isinstance(node.value.value, ast.Name) and node.value.value.id == "os"):
            self.add("environ-index", node)
        self.generic_visit(node)

    def visit_Assign(self, node) -> None:
        self._credential_assignment(node.targets, node.value, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node) -> None:
        self._credential_assignment([node.target], node.value, node)
        self.generic_visit(node)

    def _credential_assignment(self, targets, value, node) -> None:
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return
        text = value.value
        if len(text) < 8 or text.lower() in PLACEHOLDERS or text.startswith(("$", "{", "%", "<")):
            return
        for target in targets:
            name = getattr(target, "id", getattr(target, "attr", "")).lower()
            if any(name == token or name.endswith("_" + token) or name.endswith(token)
                   for token in SECRET_NAMES):
                self.add("hardcoded-secret", node)
                return

    def visit_Call(self, node) -> None:
        name = _dotted(node.func)
        leaf = name.rsplit(".", 1)[-1]
        if name in {"eval", "exec"}:
            self.add("eval-exec", node)
        if name == "os.system":
            self.add("os-system", node)
        if name.startswith("pickle.") and leaf in {"load", "loads"}:
            self.add("unsafe-pickle-load", node)
        if name == "tempfile.mktemp":
            self.add("tempfile-mktemp", node)
        if name == "os.chmod":
            mode = next((k.value for k in node.keywords if k.arg == "mode"), None)
            if isinstance(mode, ast.Constant) and isinstance(mode.value, int):
                if mode.value & 0o777 == 0o777:
                    self.add("chmod-777", node)
        if name.startswith("subprocess.") and leaf in SUBPROCESS_CALLS | {"Popen"}:
            shell = next((k for k in node.keywords if k.arg == "shell"), None)
            if shell is not None and isinstance(shell.value, ast.Constant) and shell.value.value is True:
                self.add("shell-true", node)
            if leaf in SUBPROCESS_CALLS and not any(k.arg == "timeout" for k in node.keywords):
                self.add("subprocess-timeout", node)
        if leaf in HTTP_METHODS and (name.startswith("requests.") or name.startswith("httpx.")):
            verify = next((k for k in node.keywords if k.arg == "verify"), None)
            if verify is not None and isinstance(verify.value, ast.Constant) and verify.value.value is False:
                self.add("verify-false", node)
            if not any(k.arg == "timeout" for k in node.keywords):
                self.add("network-timeout", node)
        if name in {"yaml.load", "yaml.unsafe_load"}:
            if not any(k.arg == "Loader" for k in node.keywords) or name == "yaml.unsafe_load":
                self.add("unsafe-yaml-load", node)
        if (name in {"open", "Path.open"} or name.endswith(".open")) and id(node) not in self.managed:
            if not name.startswith("os."):
                self.add("unmanaged-open", node)
        self.generic_visit(node)

    def generic_visit(self, node) -> None:
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and all(isinstance(item, ast.stmt) for item in body):
            terminal = False
            for item in body:
                if terminal:
                    self.add("unreachable-code", item)
                    break
                if isinstance(item, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                    terminal = True
        super().generic_visit(node)


def detect_source(path: str, source: str, commit: str) -> List[Finding]:
    """Every rule hit in one file revision, deduplicated and ordered by line."""
    lines = source.splitlines()
    try:
        tree = parse_source(source, path)
    except SyntaxError as exc:
        line = int(exc.lineno or 1)
        return [Finding(
            code="syntax-error", category="defect", severity="high", path=path, line=line,
            message=RULES["syntax-error"].message,
            evidence=f"{path}:{line}: {_snippet(lines, line)}",
            commit=commit, reproducible=True,
        )]
    visitor = _Visitor(path, commit, lines)
    visitor.tree = tree
    visitor.visit(tree)
    unique: Dict[Tuple[str, str, int, str], Finding] = {}
    for finding in visitor.findings:
        if allow_marker(lines, finding.line):
            continue
        unique.setdefault(finding.key(), finding)
    return sorted(unique.values(), key=lambda item: (item.line, item.code))
