from __future__ import annotations

from pathlib import Path

from tests.audit_scripts.scan_secrets import scan_repository


def test_no_hardcoded_secrets_in_repo() -> None:
    """
    Scans entire repository for credentials, tokens, API keys, and passwords.
    Ensures no sensitive production secrets are committed into version control.
    """
    repo_root = Path(__file__).resolve().parent.parent
    findings = scan_repository(repo_root)

    if findings:
        report = "\n".join(
            f" - [{f['type']}] {f['file']}:{f['line']} -> {f['preview']}"
            for f in findings
        )
        assert not findings, f"Hardcoded secrets detected in repository:\n{report}"
