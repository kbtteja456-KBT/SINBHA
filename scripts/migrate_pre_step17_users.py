"""
Step 1C Item 3: One-time reviewable migration for pre-Step 17 accounts.
Marks accounts created before Step 17 (2026-11-01 12:00:00 UTC) as verified.
Accounts created after Step 17 must verify their email via the verification link.
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Add project root
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select, and_, or_
from app.database import get_db_session, User

# Cutoff: Step 17 was deployed 2026-11-01 12:00:00 UTC
STEP17_CUTOFF_UTC = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
STEP17_MAX_PRE_USER_ID = 235


def migrate_pre_step17_verified_users(session=None, dry_run: bool = False) -> dict:
    """
    Finds accounts created before Step 17 and marks them verified.
    Returns: {"migrated_count": int, "migrated_users": list}
    """
    def _execute(sess):
        # Query users created before cutoff or id <= 235 that are currently unverified
        stmt = select(User).where(
            and_(
                User.is_verified == False,
                or_(
                    User.created_at < STEP17_CUTOFF_UTC,
                    User.created_at.is_(None),
                    User.id <= STEP17_MAX_PRE_USER_ID,
                )
            )
        )
        users_to_migrate = list(sess.scalars(stmt).all())
        migrated = []
        for u in users_to_migrate:
            migrated.append({"id": u.id, "email": u.email, "created_at": str(u.created_at)})
            if not dry_run:
                u.is_verified = True

        if not dry_run and users_to_migrate:
            sess.commit()

        return {
            "dry_run": dry_run,
            "migrated_count": len(migrated),
            "migrated_users": migrated
        }

    if session is not None:
        return _execute(session)
    else:
        with get_db_session() as sess:
            return _execute(sess)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate pre-Step 17 user verification status.")
    parser.add_argument("--dry-run", action="store_true", help="Preview users without making changes")
    args = parser.parse_args()

    print(f"Running pre-Step 17 account verification migration (dry_run={args.dry_run})...")
    res = migrate_pre_step17_verified_users(dry_run=args.dry_run)
    print(f"Migrated {res['migrated_count']} accounts.")
    for u in res["migrated_users"]:
        print(f" - User {u['id']}: {u['email']} (created: {u['created_at']})")
