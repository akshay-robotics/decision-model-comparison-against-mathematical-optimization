"""Scan publishable files and nested ZIP members without printing secret values.

This is a release gate for common credential and privacy mistakes, not a
comprehensive secret detector or a substitute for code/dependency review.
"""

import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "credential-shaped token": re.compile(
        rb"(?:sk-or-v1-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
        rb"github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|"
        rb"Bearer [A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"),
    "personal filesystem path": re.compile(rb"(?:/Users/|/home/)[A-Za-z0-9_.-]+/"),
    "personal email": re.compile(
        rb"[A-Za-z0-9._%+-]+@(?:gmail|icloud|hotmail|outlook|yahoo)\.[A-Za-z]{2,}", re.I),
    "private response/account identifier": re.compile(
        rb'''(?:response_id|account_id|user_id|organization_id)["']?\s*[:=]\s*["'][^"']{12,}''', re.I),
}
PRIVATE_NAMES = {".env", "credentials.json", "gurobi.lic", "calls.jsonl", "runs.jsonl",
                 "requests.jsonl", "responses.jsonl", "errors.jsonl"}


def local_secret_values():
    values = [v for k, v in os.environ.items()
              if any(word in k for word in ("API_KEY", "AUTH_TOKEN", "ACCESS_TOKEN"))]
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and any(word in key.upper() for word in ("KEY", "TOKEN", "PASSWORD")):
                values.append(value.strip().strip('"\''))
    return [v.encode() for v in values if len(v) >= 16]


def inspect_bytes(name, raw, secrets=(), depth=0):
    """Return names/rules only; never return matched contents."""
    findings = []
    path = PurePosixPath(name.split("!")[-1])
    if (path.name in PRIVATE_NAMES or path.name.endswith((".pem", ".key", ".log"))
            or path.is_absolute() or ".." in path.parts
            or any(p in {"results", ".git", ".ssh", ".aws"} for p in path.parts)):
        findings.append((name, "private or unsafe publication path"))
    for label, pattern in PATTERNS.items():
        if pattern.search(raw):
            findings.append((name, label))
    if any(value in raw for value in secrets):
        findings.append((name, "configured local secret"))
    if path.suffix.lower() == ".zip":
        if depth >= 3:
            return findings + [(name, "archive nesting limit")]
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
                return findings + [(name, "archive expansion limit")]
            for item in archive.infolist():
                if stat.S_ISLNK(item.external_attr >> 16):
                    findings.append((name + "!" + item.filename, "archive symlink"))
                elif not item.is_dir():
                    findings.extend(inspect_bytes(name + "!" + item.filename,
                                                  archive.read(item), secrets, depth + 1))
    return findings


def main():
    files = set(subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")) - {""}
    secrets = local_secret_values()
    findings = []
    for name in sorted(files):
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            findings.append((name, "missing file or symlink"))
            continue
        findings.extend(inspect_bytes(name, path.read_bytes(), secrets))
    for name, rule in findings:
        print(f"{name}: {rule}", file=sys.stderr)
    if findings:
        print(f"Publication security check failed: {len(findings)} finding(s).", file=sys.stderr)
        return 1
    print(f"Publication security checks passed ({len(files)} files and nested ZIP contents).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
