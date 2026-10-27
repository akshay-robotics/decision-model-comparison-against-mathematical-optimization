#!/usr/bin/env python3
"""Check publishable files and simple inline Markdown file links using only stdlib.

Checks tracked and non-ignored untracked files. External URLs, anchor targets,
reference-style links, and Git history are outside this check's scope.
"""

from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 10 * 1024 * 1024
LINK = re.compile(r"!?\[[^\]\n]*\]\(([^\s)]+)\)")


def main():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    files = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
    publishable = set(files)
    errors = []
    for relative in files:
        path = ROOT / relative
        name = path.name.lower()
        if name in {"tr2023-059.pdf", "tr2024-123.pdf"}:
            errors.append(f"{relative}: reference PDF must remain local and ignored")
        if (
            (name == ".env" or name.startswith(".env."))
            and name != ".env.example"
        ) or name.endswith((".pem", ".key")) or name == "credentials.json" or name.startswith("secrets."):
            errors.append(f"{relative}: potential credential file must not be published")
        if path.is_symlink():
            errors.append(f"{relative}: review symlinks explicitly before publication")
            continue
        if not path.is_file():
            errors.append(f"{relative}: missing file; stage intended deletions")
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"{relative}: exceeds the project's 10 MiB artifact limit")
        if path.suffix.lower() != ".md":
            continue
        content = path.read_text(encoding="utf-8")
        # Skip fenced examples; this is deliberately a small link checker.
        content = re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", "", content, flags=re.M | re.S)
        for target in LINK.findall(content):
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            try:
                destination_relative = destination.relative_to(ROOT).as_posix()
            except ValueError:
                errors.append(f"{relative}: link leaves repository: {target}")
                continue
            if not destination.exists():
                errors.append(f"{relative}: broken local link: {target}")
            elif destination.is_file() and destination_relative not in publishable:
                errors.append(f"{relative}: link points to an ignored file: {target}")
    if errors:
        print("Repository checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Repository checks passed ({len(files)} publishable files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
