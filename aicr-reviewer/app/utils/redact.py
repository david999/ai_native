import re

_SECRET_PATTERNS = [
    (re.compile(r"(password|secret|api[_-]?key|token)\s*[:=]\s*\S+", re.I), r"\1=***REDACTED***"),
    (re.compile(r"glpat-[A-Za-z0-9._-]+"), "glpat-***REDACTED***"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***REDACTED***"),
]


def redact_secrets(text: str) -> str:
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text
