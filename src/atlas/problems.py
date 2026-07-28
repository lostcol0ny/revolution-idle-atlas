from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Problem:
    severity: Severity
    message: str
    line: int | None = None

    def render(self, path: str) -> str:
        location = f"{path}:{self.line}" if self.line is not None else path
        return f"{location}  {self.severity}  {self.message}"
