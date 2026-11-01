"""
Step 1C Item 3 Test Suite: Verification Migration & Invariant Testing
Validates:
1. One-time migration marks accounts created before Step 17 as verified.
2. New accounts created after Step 17 remain unverified until clicking email link.
3. is_user_verified never infers 'verified' from having trusted devices.
"""

from datetime import datetime, timezone, timedelta
import pytest
from app import database as db
from app.models import User, Device
from scripts.migrate_pre_step17_users import migrate_pre_step17_verified_users, STEP17_CUTOFF_UTC


def test_verification_not_inferred_from_trusted_devices():
    with db.get_db_session() as sess:
        # Create unverified user
        user = User(
            email="unverified_device_user@example.com",
            password_hash=db.hash_password("Password123!"),
            is_verified=False,
            created_at=datetime.now(timezone.utc)
        )
        sess.add(user)
        sess.flush()
        user_id = user.id

        # Attach a trusted device
        dev = Device(
            user_id=user_id,
            device_id="trusted_dev_test_99",
            name="Test PC",
            platform="windows",
            status="trusted"
        )
        sess.add(dev)
        sess.commit()

    # Invariant: Must NOT be inferred as verified just because it has a trusted device!
    assert db.is_user_verified(user_id) is False


def test_pre_step17_migration_verifies_old_accounts_only():
    old_user_id = None
    new_user_id = None

    with db.get_db_session() as sess:
        # 1. Pre-Step 17 user (created before Nov 1, 2026 12:00:00 UTC)
        old_time = STEP17_CUTOFF_UTC - timedelta(days=10)
        old_user = User(
            email="pre_step17_user@example.com",
            password_hash=db.hash_password("Password123!"),
            is_verified=False,
            created_at=old_time
        )
        sess.add(old_user)

        # 2. Post-Step 17 user (created after Nov 1, 2026 12:00:00 UTC)
        new_time = STEP17_CUTOFF_UTC + timedelta(hours=5)
        new_user = User(
            email="post_step17_user@example.com",
            password_hash=db.hash_password("Password123!"),
            is_verified=False,
            created_at=new_time
        )
        # Ensure ID > 235 for post-cutoff test user
        new_user.id = 9999
        sess.add(new_user)
        sess.commit()

        old_user_id = old_user.id
        new_user_id = new_user.id

    # Run migration
    res = migrate_pre_step17_verified_users(dry_run=False)
    migrated_ids = [u["id"] for u in res["migrated_users"]]

    assert old_user_id in migrated_ids
    assert new_user_id not in migrated_ids

    # Old user is now verified
    assert db.is_user_verified(old_user_id) is True

    # New user remains strictly unverified
    assert db.is_user_verified(new_user_id) is False
