"""
Tests for Safe Facts Schema Migration (Task 3)
Validates:
1. Legacy SQLite database containing existing user facts upgrades safely without data loss.
2. Pre-existing records acquire default values (fact_type='stable_fact', source='user_explicit', confidence=100, is_sensitive=0).
3. Migration is completely idempotent (subsequent runs produce no errors).
4. Full ORM operations succeed on the upgraded database.
"""

import pytest
import sqlite3
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import migrate_facts_schema
from app.models import Fact, Base


def test_sqlite_upgrade_with_existing_user_data(tmp_path):
    db_file = str(tmp_path / "legacy_sinbha.db")

    # 1. Create a legacy database using raw sqlite with the old facts schema
    raw_conn = sqlite3.connect(db_file)
    cursor = raw_conn.cursor()
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            fact TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Populate existing user data
    cursor.execute("INSERT INTO users (id, email, password_hash) VALUES (1, 'legacy_user@example.com', 'hash123')")
    cursor.execute("INSERT INTO facts (id, user_id, fact, category) VALUES (10, 1, 'Lives in Seattle', 'personal')")
    cursor.execute("INSERT INTO facts (id, user_id, fact, category) VALUES (11, 1, 'Prefers dark roast coffee', 'preference')")
    cursor.execute("INSERT INTO facts (id, user_id, fact, category) VALUES (12, 1, 'Studying BTech Computer Science', 'education')")
    raw_conn.commit()
    raw_conn.close()

    # Verify legacy columns before migration
    test_engine = create_engine(f"sqlite:///{db_file}")
    with test_engine.connect() as conn:
        cols_before = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(facts)").fetchall()]
        assert "fact_type" not in cols_before
        assert "source" not in cols_before
        assert "confidence" not in cols_before
        assert "is_sensitive" not in cols_before
        assert "last_confirmed_at" not in cols_before
        assert "expires_at" not in cols_before

    # 3. Run safe migration
    res = migrate_facts_schema(target_engine=test_engine)
    assert res["dialect"] == "sqlite"
    assert "fact_type" in res["added_columns"]
    assert "confidence" in res["added_columns"]

    # 4. Verify columns exist and legacy data is preserved
    with test_engine.connect() as conn:
        cols_after = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(facts)").fetchall()]
        assert "fact_type" in cols_after
        assert "source" in cols_after
        assert "confidence" in cols_after
        assert "is_sensitive" in cols_after
        assert "last_confirmed_at" in cols_after
        assert "expires_at" in cols_after

        # Verify existing user records retained data and took on defaults
        rows = conn.exec_driver_sql("SELECT id, user_id, fact, category, fact_type, source, confidence, is_sensitive FROM facts ORDER BY id").fetchall()
        assert len(rows) == 3
        # Row 10
        assert rows[0][0] == 10
        assert rows[0][2] == "Lives in Seattle"
        assert rows[0][4] == "stable_fact"
        assert rows[0][5] == "user_explicit"
        assert rows[0][6] == 100
        assert rows[0][7] == 0
        # Row 12
        assert rows[2][0] == 12
        assert rows[2][2] == "Studying BTech Computer Science"
        assert rows[2][4] == "stable_fact"

    # 5. Verify Idempotence: running migration a second time does not fail or duplicate
    res_repeat = migrate_facts_schema(target_engine=test_engine)
    assert len(res_repeat["added_columns"]) == 0

    # 6. Verify ORM query on upgraded database
    with Session(test_engine) as sess:
        facts = sess.scalars(select(Fact).order_by(Fact.id)).all()
        assert len(facts) == 3
        assert facts[0].fact == "Lives in Seattle"
        assert facts[0].fact_type == "stable_fact"

        # Insert new record using full v1.5.0 schema into upgraded database
        new_fact = Fact(
            user_id=1,
            fact="Goal: Pass Machine Learning Exam",
            category="education",
            fact_type="current_goal",
            source="user_explicit",
            confidence=95,
            is_sensitive=False
        )
        sess.add(new_fact)
        sess.commit()

        updated_facts = sess.scalars(select(Fact).where(Fact.fact_type == "current_goal")).all()
        assert len(updated_facts) == 1
        assert updated_facts[0].fact == "Goal: Pass Machine Learning Exam"

