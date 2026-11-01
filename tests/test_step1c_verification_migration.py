"""
Step 1C Item 3 Test: Legacy Accounts Migration & Strict Email Verification
Verifies that:
1. Legacy accounts created before Step 17 cutoff are migrated to is_verified = True.
2. New accounts start as is_verified = False.
3. Having trusted devices does NOT dynamically infer or bypass is_verified.
4. Completing email verification properly unlocks verification status.
"""

import pytest
from datetime import datetime, timedelta, timezone

from app import database as db


def test_legacy_account_migration_and_no_device_inference():
    # 1. Create a legacy unverified user with created_at in the past
    legacy_user = db.create_user(
        email="legacy_user@example.com",
        password="Password123!",
        is_verified=False
    )
    legacy_id = legacy_user["id"]

    # Set created_at to before Step 17 cutoff (e.g. Oct 2026)
    with db.get_db_session() as session:
        u = session.scalar(db.select(db.User).where(db.User.id == legacy_id))
        u.created_at = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
        session.commit()

    # Prior to migration, is_verified is False
    assert db.is_user_verified(legacy_id) is False

    # 2. Add a trusted device to legacy_user
    # Invariant: having a trusted device must NEVER infer or grant is_verified
    db.create_or_register_device(
        user_id=legacy_id,
        device_id="legacy_dev_1",
        name="Legacy Laptop",
        platform="windows",
        is_signup=True
    )
    # Must still be False (no dynamic device inference)
    assert db.is_user_verified(legacy_id) is False

    # 3. Create a NEW user created after cutoff
    new_user = db.create_user(
        email="new_user_post_step17@example.com",
        password="Password123!",
        is_verified=False
    )
    new_id = new_user["id"]
    with db.get_db_session() as session:
        u_new = session.scalar(db.select(db.User).where(db.User.id == new_id))
        u_new.created_at = datetime(2026, 11, 1, 15, 0, 0, tzinfo=timezone.utc)
        session.commit()

    assert db.is_user_verified(new_id) is False

    # Even with a trusted device, new_user is NOT verified
    db.create_or_register_device(
        user_id=new_id,
        device_id="new_dev_1",
        name="New Laptop",
        platform="windows",
        is_signup=True
    )
    assert db.is_user_verified(new_id) is False

    # 4. Run the one-time migration
    cutoff = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    migrated_count = db.migrate_legacy_accounts_pre_step17(cutoff_date=cutoff)
    assert migrated_count >= 1

    # 5. After migration:
    # - Legacy user is now verified
    assert db.is_user_verified(legacy_id) is True

    # - New user remains UNVERIFIED
    assert db.is_user_verified(new_id) is False

    # 6. New user verifies strictly via token
    with db.get_db_session() as session:
        tok = session.scalar(db.select(db.User.verification_token).where(db.User.id == new_id))
    
    assert tok is not None
    success, msg, uid = db.verify_email_with_token(tok)
    assert success is True
    assert db.is_user_verified(new_id) is True
