"""Create the ragpilot-docs storage bucket if it does not exist.

Run after filling in real values in .env:
    .venv\\Scripts\\python.exe -m scripts.create_bucket
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import get_supabase  # noqa: E402


def main() -> None:
    settings = get_settings()
    sb = get_supabase()
    bucket = settings.storage_bucket

    try:
        existing = sb.storage.get_bucket(bucket)
        print(f"Bucket '{bucket}' already exists.")
        return
    except Exception:
        pass

    sb.storage.create_bucket(bucket, options={"public": False})
    print(f"Created private bucket '{bucket}'.")

    print("Next: apply migrations/001_init.sql and migrations/002_storage.sql "
          "in the Supabase SQL editor, or run `supabase db push`.")


if __name__ == "__main__":
    main()
