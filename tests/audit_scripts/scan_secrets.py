from __future__ import annotations

import os
import re
from pathlib import Path

# High-entropy production credential signatures
SECRET_PATTERNS = {
    "Discord Bot Token": re.compile(r"[MNO][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}"),
    "Google API Key": re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    "Groq API Key": re.compile(r"gsk_[a-zA-Z0-9]{48}"),
    "GitHub Classic PAT": re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    "GitHub Fine-Grained PAT": re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
    "Postgres DSN with Password": re.compile(r"postgres(?:ql)?://[^:\s@]+:[^@\s]+@[^/\s]+/\w+"),
}

EXCLUDED_DIRS = {
    ".git",
    "assets",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
}

EXCLUDED_FILES = {
    ".env",
    ".env.example",
    "AUDIT.md",
    "scan_secrets.py",
    "test_secret_scanner.py",
    "libopus.so.0",
    "opus.dll",
}

# Binary file extensions to skip
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".so", ".dll", ".dylib", ".exe", ".bin", ".pyc",
    ".zip", ".tar", ".gz",
}


def scan_repository(repo_root: Path | str) -> list[dict[str, str | int]]:
    root_path = Path(repo_root).resolve()
    findings: list[dict[str, str | int]] = []

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file_name in files:
            if file_name in EXCLUDED_FILES:
                continue

            file_path = Path(root) / file_name
            if file_path.suffix.lower() in BINARY_EXTENSIONS:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            for line_no, line in enumerate(lines, start=1):
                # Ignore commented template/placeholder examples in docs or config
                stripped = line.strip()
                if "YOUR-PASSWORD" in stripped or "[PROJECT-REF]" in stripped or "<password>" in stripped:
                    continue
                if stripped.startswith("#") and ("your_" in stripped or "example" in stripped.lower() or "placeholder" in stripped.lower()):
                    continue

                for secret_name, pattern in SECRET_PATTERNS.items():
                    match = pattern.search(line)
                    if match:
                        findings.append({
                            "type": secret_name,
                            "file": str(file_path.relative_to(root_path)),
                            "line": line_no,
                            "preview": line.strip()[:60],
                        })

    return findings


if __name__ == "__main__":
    repo = Path(__file__).resolve().parent.parent.parent
    results = scan_repository(repo)
    if results:
        print(f"CRITICAL: Found {len(results)} potential secret(s):")
        for res in results:
            print(f" - [{res['type']}] {res['file']}:{res['line']} -> {res['preview']}")
        exit(1)
    else:
        print("Zero hardcoded secrets detected across repository.")
