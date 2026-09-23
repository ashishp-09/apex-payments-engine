#!/usr/bin/env python3
from __future__ import annotations

"""
Automated Daily Git Commit & Push Engine for Apex Payments Engine (Python).
Iterates through pending files and commits multiple files per day (default: 3 files)
with realistic conventional commit messages, then pushes to GitHub.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

REPO_DIR = Path(__file__).resolve().parent.parent

# Custom conventional commit mapping for Python project files
FILE_COMMIT_MESSAGES = {
    "pyproject.toml": "chore(build): define python 3.13 project metadata and dependencies",
    "requirements.txt": "chore(deps): add FastAPI, SQLAlchemy 2.0 async, and Stripe requirements",
    "alembic.ini": "chore(db): configure alembic database migration environment",
    "alembic/env.py": "feat(db): implement async migration runner in alembic",
    "alembic/script.py.mako": "chore(db): add alembic script template",
    "alembic/versions/001_initial_schema.py": "feat(db): create initial double-entry schema and postgresql triggers",
    "alembic/versions/002_processed_events_and_refunds.py": "feat(db): add processed events dedupe and refunds tables",
    "app/config.py": "feat(config): implement pydantic BaseSettings for database and redis configuration",
    "app/domain/enums.py": "feat(domain): define domain enumerations for account types and payment states",
    "app/domain/exceptions.py": "feat(domain): define domain exceptions for balance guards and idempotency",
    "app/domain/models.py": "feat(domain): implement SQLAlchemy 2.0 async declarative models",
    "app/domain/__init__.py": "feat(domain): expose domain models and exceptions in package init",
    "app/infrastructure/database.py": "feat(infra): configure async SQLAlchemy engine and session dependency",
    "app/infrastructure/redis_client.py": "feat(infra): implement async Redis connection pool and idempotency lock",
    "app/infrastructure/psp/provider.py": "feat(psp): define PaymentProvider abstract interface and authorization results",
    "app/infrastructure/psp/mock_psp.py": "feat(psp): implement MockPspClient for local testing and simulation",
    "app/infrastructure/psp/stripe_psp.py": "feat(psp): implement StripePaymentProvider with manual capture method",
    "app/infrastructure/psp/signature.py": "feat(security): add HMAC-SHA256 and Stripe webhook signature verifiers",
    "app/infrastructure/psp/__init__.py": "feat(psp): package psp providers and signature verifiers",
    "app/infrastructure/__init__.py": "feat(infra): expose database and redis infrastructure",
    "app/application/schemas.py": "feat(app): define Pydantic v2 request and response DTO schemas",
    "app/application/ledger_service.py": "feat(ledger): implement double-entry balance validation and row locking",
    "app/application/idempotency_service.py": "feat(idempotency): implement two-tier Redis and Postgres idempotency engine",
    "app/application/payment_saga.py": "feat(saga): implement Hold-Authorize-Settle distributed payment saga",
    "app/application/payment_service.py": "feat(payments): implement PaymentService orchestrating payment lifecycle",
    "app/application/refund_service.py": "feat(refunds): implement RefundService with over-refund protection",
    "app/application/webhook_service.py": "feat(webhooks): implement WebhookService with deduplication and state guards",
    "app/application/reconciliation_service.py": "feat(reconciliation): implement continuous ledger audit and hold expiry",
    "app/application/outbox_relay.py": "feat(outbox): implement asynchronous OutboxRelay background worker",
    "app/application/__init__.py": "feat(app): package application services and schemas",
    "app/api/dependencies.py": "feat(api): define FastAPI dependency injection providers",
    "app/api/payments.py": "feat(api): implement /v1/payments endpoints with idempotency support",
    "app/api/accounts.py": "feat(api): implement /v1/accounts balance and ledger audit trail endpoints",
    "app/api/refunds.py": "feat(api): implement /v1/payments/{id}/refunds endpoint",
    "app/api/webhooks.py": "feat(api): implement /v1/webhooks for Stripe and custom PSP callbacks",
    "app/api/reconciliation.py": "feat(api): implement /v1/reconciliation/report endpoint",
    "app/api/__init__.py": "feat(api): expose API routers",
    "app/main.py": "feat(core): initialize FastAPI application with Lifespan, Prometheus, and exception handlers",
    "app/__init__.py": "feat(core): expose FastAPI app instance",
    "tests/conftest.py": "test: configure pytest-asyncio test fixtures and in-memory database",
    "tests/test_ledger.py": "test(ledger): verify double-entry invariant validation and balance checks",
    "tests/test_concurrency.py": "test(concurrency): verify concurrent balance debits prevent oversell",
    "tests/test_idempotency.py": "test(idempotency): verify response replay and payload mismatch rejection",
    "tests/test_payments.py": "test(payments): verify hold-authorize-settle saga and failure reversals",
    "tests/test_refunds.py": "test(refunds): verify full, partial, and over-refund protections",
    "tests/test_webhooks.py": "test(webhooks): verify webhook signature checks and async capture",
    "tests/test_reconciliation.py": "test(reconciliation): verify mathematical ledger integrity checks",
    "Dockerfile": "ci(docker): configure multi-stage Python 3.13-slim container build",
    "docker-compose.yml": "ci(docker): configure full stack orchestration with Postgres, Redis, and Grafana",
    "README.md": "docs: update system architecture, double-entry specs, and Python API reference",
}

PREFERRED_ORDER = [
    "pyproject.toml",
    "requirements.txt",
    "alembic.ini",
    "alembic/env.py",
    "alembic/script.py.mako",
    "alembic/versions/001_initial_schema.py",
    "alembic/versions/002_processed_events_and_refunds.py",
    "app/config.py",
    "app/domain/enums.py",
    "app/domain/exceptions.py",
    "app/domain/models.py",
    "app/domain/__init__.py",
    "app/infrastructure/database.py",
    "app/infrastructure/redis_client.py",
    "app/infrastructure/psp/provider.py",
    "app/infrastructure/psp/mock_psp.py",
    "app/infrastructure/psp/stripe_psp.py",
    "app/infrastructure/psp/signature.py",
    "app/infrastructure/psp/__init__.py",
    "app/infrastructure/__init__.py",
    "app/application/schemas.py",
    "app/application/ledger_service.py",
    "app/application/idempotency_service.py",
    "app/application/payment_saga.py",
    "app/application/payment_service.py",
    "app/application/refund_service.py",
    "app/application/webhook_service.py",
    "app/application/reconciliation_service.py",
    "app/application/outbox_relay.py",
    "app/application/__init__.py",
    "app/api/dependencies.py",
    "app/api/payments.py",
    "app/api/accounts.py",
    "app/api/refunds.py",
    "app/api/webhooks.py",
    "app/api/reconciliation.py",
    "app/api/__init__.py",
    "app/main.py",
    "app/__init__.py",
    "tests/conftest.py",
    "tests/test_ledger.py",
    "tests/test_concurrency.py",
    "tests/test_idempotency.py",
    "tests/test_payments.py",
    "tests/test_refunds.py",
    "tests/test_webhooks.py",
    "tests/test_reconciliation.py",
    "Dockerfile",
    "docker-compose.yml",
    "README.md",
]


def run_cmd(cmd: list[str], cwd: Path = REPO_DIR) -> tuple[int, str, str]:
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def get_pending_files() -> list[str]:
    """Returns a list of uncommitted/modified/untracked files relative to REPO_DIR."""
    code, stdout, _ = run_cmd(["git", "status", "--porcelain"])
    if code != 0 or not stdout:
        return []

    files = []
    for line in stdout.splitlines():
        if len(line) < 4:
            continue
        raw_path = line[3:].strip().strip('"')
        target_path = REPO_DIR / raw_path
        if target_path.is_dir():
            for p in sorted(target_path.rglob("*")):
                if p.is_file() and not str(p).endswith((".pyc", ".DS_Store")):
                    files.append(str(p.relative_to(REPO_DIR)))
        elif target_path.is_file():
            if not raw_path.endswith((".pyc", ".DS_Store")):
                files.append(raw_path)

    def sort_key(f: str):
        try:
            return (0, PREFERRED_ORDER.index(f))
        except ValueError:
            return (1, f)

    return sorted(list(dict.fromkeys(files)), key=sort_key)


def generate_commit_message(filepath: str) -> str:
    """Generates a clean conventional commit message for a given file."""
    if filepath in FILE_COMMIT_MESSAGES:
        return FILE_COMMIT_MESSAGES[filepath]

    basename = os.path.basename(filepath)
    if "test" in filepath.lower():
        return f"test: add test coverage for {basename}"
    elif filepath.endswith((".py", ".pyi")):
        return f"feat: implement updates in {basename}"
    elif filepath.endswith((".yml", ".yaml", ".ini", ".toml", ".plist")):
        return f"chore(config): update configuration in {basename}"
    elif filepath.endswith((".md", ".txt")):
        return f"docs: update documentation in {basename}"
    return f"feat: update {basename}"


def push_batch(count: int = 3, dry_run: bool = False, specific_file: str | None = None) -> bool:
    pending = get_pending_files()
    if not pending:
        print("✅ No pending files left to commit! Working tree is completely clean.")
        return True

    files_to_commit = [specific_file] if specific_file else pending[:count]

    print("=" * 65)
    print(f"📦 Daily Batch Push: Committing {len(files_to_commit)} file(s) today")
    print("=" * 65)

    committed_files = []
    for target_file in files_to_commit:
        if not (REPO_DIR / target_file).exists():
            print(f"❌ File '{target_file}' does not exist.")
            continue

        commit_msg = generate_commit_message(target_file)
        print(f"\n🎯 File        : {target_file}")
        print(f"💬 Commit Msg  : {commit_msg}")

        if dry_run:
            print("🔍 [Dry Run] Would stage and commit.")
            continue

        # 1. Stage file
        code, out, err = run_cmd(["git", "add", target_file])
        if code != 0:
            print(f"❌ Error staging file: {err}")
            return False

        # 2. Commit
        code, out, err = run_cmd(["git", "commit", "-m", commit_msg])
        if code != 0:
            print(f"❌ Error creating commit: {err}")
            return False

        committed_files.append(target_file)

    if dry_run:
        print("\n🔍 [Dry Run] No git changes were committed or pushed.")
        return True

    # 3. Push all committed changes to remote
    print("\n🚀 Pushing commits to remote (origin main)...")
    code, out, err = run_cmd(["git", "push", "origin", "main"])
    if code != 0:
        print(f"⚠️  Git push returned: {err or out}")
        return False

    remaining = len(get_pending_files())
    print("=" * 65)
    print(f"🎉 Successfully committed {len(committed_files)} file(s) and pushed to GitHub!")
    print(f"📋 Remaining in queue: {remaining} file(s)")
    print("=" * 65)
    return True


def list_queue(per_day: int = 3):
    pending = get_pending_files()
    if not pending:
        print("✅ Working tree is clean! All files committed.")
        return

    days_needed = (len(pending) + per_day - 1) // per_day
    print(f"\n📋 Daily Commit Queue ({len(pending)} files pending — ~{days_needed} days remaining at {per_day} files/day):")
    print("=" * 70)

    for i in range(0, len(pending), per_day):
        day_num = (i // per_day) + 1
        day_files = pending[i : i + per_day]
        marker = f"👉 [TODAY / Day 1]" if day_num == 1 else f"   Day {day_num}"
        print(f"\n{marker} ({len(day_files)} files):")
        for f in day_files:
            msg = generate_commit_message(f)
            print(f"   • {f}")
            print(f"     ↳ \"{msg}\"")
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Daily Git Push Automation (3 files/day)")
    parser.add_argument("--push", action="store_true", help="Commit and push the daily batch of files (default 3)")
    parser.add_argument("--count", type=int, default=3, help="Number of files to commit today (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Preview the commits without making changes")
    parser.add_argument("--status", action="store_true", help="List all pending files in the queue grouped by day")
    parser.add_argument("--file", type=str, help="Specify a specific file to commit today")

    args = parser.parse_args()

    if args.status:
        list_queue(per_day=args.count)
    elif args.push or args.dry_run or args.file:
        push_batch(count=args.count, dry_run=args.dry_run, specific_file=args.file)
    else:
        list_queue(per_day=args.count)
        print("\n💡 Commands:")
        print("  python3 scripts/daily_push.py --push       # Commit & push 3 files today")
        print("  python3 scripts/daily_push.py --count 3    # Specify custom batch count")
        print("  python3 scripts/daily_push.py --dry-run    # Preview next 3 commits")
        print("  python3 scripts/daily_push.py --status     # View grouped daily queue")


if __name__ == "__main__":
    main()
