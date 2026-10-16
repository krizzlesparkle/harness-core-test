#!/usr/bin/env python3
"""Scan gate for harness-core (ITSM-220).

Refuses content that must not leave the work side or enter a shared repo:
LHP names, ITSM keys, keeper:// pointers and secret-shaped strings.

Usage:  python scan_core.py PATH [PATH ...]
Exit:   0 clean, 1 findings, 2 could not read something (never read as clean).
Standard library only.
"""
import re
import sys
from pathlib import Path

DENY = [
    ("lhp-name", re.compile(r"\blhp(?:inc|es|net|software)?\b|lhp-[a-z]", re.I)),
    ("lhp-domain", re.compile(r"lhpinc|lhpes|lhpnet|lhpsoftware|lertechforce|ler techforce", re.I)),
    ("itsm-key", re.compile(r"\bITSM(?:AMPLE)?-\d+\b")),
    ("keeper-pointer", re.compile(r"keeper://|\bksm exec\b", re.I)),
    ("atlassian-site", re.compile(r"atlassian\.net", re.I)),
    ("work-system", re.compile(r"\bworkday\b|\bintune\b|\bentra\b|\bhubspot\b", re.I)),
    ("work-identity", re.compile(r"ryan\.kreigh|ryan-kreigh_lhpinc", re.I)),
    ("gh-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secret-assign", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{12,}")),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__"}
# The gate's own files describe the patterns, so they are exempt from themselves.
SELF_EXEMPT = {"scan_core.py", "test_scan_core.py"}
MAX_BYTES = 2_000_000


def iter_files(paths):
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not (set(f.parts) & SKIP_DIRS):
                    yield f
        else:
            yield p


def scan_text(text):
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, rx in DENY:
            if rx.search(line):
                hits.append((n, name))
    return hits


def main(argv):
    if not argv:
        print("usage: scan_core.py PATH [PATH ...]", file=sys.stderr)
        return 2
    findings, unreadable, scanned = [], [], 0
    for f in iter_files(argv):
        if f.name in SELF_EXEMPT:
            continue
        try:
            if f.stat().st_size > MAX_BYTES:
                unreadable.append((str(f), "over 2 MB"))
                continue
            data = f.read_bytes()
        except OSError as e:
            unreadable.append((str(f), str(e)))
            continue
        if b"\x00" in data[:4096]:
            unreadable.append((str(f), "binary file, not scanned"))
            continue
        scanned += 1
        for n, name in scan_text(data.decode("utf-8", errors="replace")):
            findings.append((str(f), n, name))
    for path, n, name in findings:
        print(f"BLOCK {name}: {path}:{n}")
    for path, why in unreadable:
        print(f"UNREAD {path}: {why}")
    print(f"scanned {scanned} files, {len(findings)} findings, {len(unreadable)} unread")
    if unreadable:
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
