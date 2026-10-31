"""Actionable failures shared by the standalone CLI and the AIKit command."""


class ReforgeError(Exception):
    """A request Reforge refused; carries the AIKit What/Why/Fix triad and exit code."""

    def __init__(self, message: str, why: str, fix: str, exit_code: int = 1) -> None:
        self.message = message
        self.why = why
        self.fix = fix
        self.exit_code = exit_code
        super().__init__(message)

    def triad(self) -> str:
        return f"Error: {self.message}\nWhy: {self.why}\nFix: {self.fix}"
