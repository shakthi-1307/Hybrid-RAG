"""Guard against reserved keys in ``logger.*(extra=...)``.

Passing a key that ``LogRecord`` already defines — ``filename``, ``module``,
``lineno``, ``args`` — makes ``logging`` raise ``KeyError`` rather than
overwrite it. That failure happens at the call site, so a single bad key turns
a working endpoint into a 500 the moment it logs, and only on the path that
reaches that line.

This scans the source rather than exercising every logging call, because the
whole problem is that the bad calls are the ones nobody exercised.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRECTORIES = ("app", "evaluation")

LOG_METHODS = frozenset(
    {"debug", "info", "warning", "error", "exception", "critical", "log"}
)


def reserved_attributes() -> frozenset[str]:
    """Attributes ``makeRecord`` refuses to let ``extra`` overwrite.

    Derived from a real record rather than hard-coded, so a future Python
    release that adds an attribute is covered automatically.
    """
    record = logging.LogRecord("n", logging.INFO, "path", 1, "msg", (), None)
    return frozenset(record.__dict__) | {"message", "asctime", "taskName"}


def python_files() -> list[Path]:
    return [
        path
        for directory in SCANNED_DIRECTORIES
        for path in (BACKEND_ROOT / directory).rglob("*.py")
    ]


def extra_keys_in(path: Path) -> list[tuple[int, str]]:
    """Every literal key passed as ``extra={...}`` to a logging call."""
    found: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not isinstance(function, ast.Attribute) or function.attr not in LOG_METHODS:
            continue

        for keyword in node.keywords:
            if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                continue
            for key in keyword.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.append((node.lineno, key.value))
    return found


def test_no_logging_extra_key_shadows_a_record_attribute():
    reserved = reserved_attributes()
    collisions = [
        f"{path.relative_to(BACKEND_ROOT)}:{line} uses extra={{'{key}': ...}}"
        for path in python_files()
        for line, key in extra_keys_in(path)
        if key in reserved
    ]

    assert not collisions, (
        "These logging calls would raise KeyError at runtime. Rename the key "
        "(e.g. 'filename' -> 'document_filename'):\n  " + "\n  ".join(collisions)
    )


def test_the_scanner_actually_finds_keys():
    """A scanner that silently matches nothing would pass forever."""
    keys = {key for path in python_files() for _, key in extra_keys_in(path)}

    assert "document_id" in keys


def test_a_reserved_key_really_does_raise():
    """Pins the behaviour this guard exists for, so the rule is not folklore."""
    logger = logging.getLogger("test.reserved")
    # Without an enabled level, ``info`` returns before building a record and
    # the KeyError never happens — the test would pass while proving nothing.
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.NullHandler())

    with pytest.raises(KeyError):
        logger.info("boom", extra={"filename": "report.pdf"})

    # The renamed version is fine.
    logger.info("fine", extra={"document_filename": "report.pdf"})
