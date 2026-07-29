from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Problem:
    severity: Severity
    message: str
    line: int | None = None
    # The file this problem was found in, when that is known where it is built.
    # It exists because the dataset being reported against is merged from two
    # files: a problem found *during* the merge still knows which input it read
    # and must be able to say so, since the code printing it holds one path and
    # cannot recover the provenance of an individual record.
    #
    # Problems found *after* the merge — validation, raw-check — see a single
    # dataset with no provenance left in it. They leave this None and fall back
    # to the path the caller supplies.
    path: str | None = None

    def render(self, default_path: str) -> str:
        path = self.path or default_path
        location = f"{path}:{self.line}" if self.line is not None else path
        return f"{location}  {self.severity}  {self.message}"
