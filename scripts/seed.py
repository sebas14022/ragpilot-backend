"""Seed sample data for a user (run with real creds after bucket/migrations).

Usage:
    .venv\\Scripts\\python.exe -m scripts.seed <user_email>
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_supabase, get_user_email  # noqa: E402

QUESTIONS = [
    "What was RagPilot revenue in 2025?",
    "Who founded RagPilot and who is the CEO?",
    "What is the refund policy for annual plans?",
    "What is the S3 retention period for raw documents?",
    "What is the p95 latency target for the production API?",
    "What OAuth scopes are required to create documents?",
]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.seed <user_email>")
        sys.exit(1)

    email = sys.argv[1]
    sb = get_supabase()
    user_id = get_user_email(sb, email)

    # Resolve user id by email if possible; otherwise look up via admin API.
    if not user_id:
        try:
            res = sb.auth.admin.list_users()
            for u in (res.users or []):
                if u.email == email:
                    user_id = u.id
                    break
        except Exception as exc:
            print(f"Could not resolve user: {exc}")
            sys.exit(1)

    if not user_id:
        print(f"No user found for {email}")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    rows = []
    for i in range(24):
        when = now - timedelta(days=random.randint(0, 60), hours=random.randint(0, 23))
        rows.append(
            {
                "user_id": user_id,
                "question": random.choice(QUESTIONS),
                "answer": "Seeded answer for dashboard demo.",
                "model": "gemini-3.6-flash",
                "latency_ms": random.randint(200, 900),
                "groundedness": random.choice(["High", "High", "Medium"]),
                "tokens_used": random.randint(80, 400),
                "chunks_retrieved": random.randint(1, 6),
                "status": "success",
                "created_at": when.isoformat(),
            }
        )

    sb.table("queries").insert(rows).execute()
    print(f"Seeded {len(rows)} queries for {email} ({user_id})")


if __name__ == "__main__":
    main()
