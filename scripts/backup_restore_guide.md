# SINBHA Database Backup & Restore Guide (pg_dump & psql)

This guide walks you through backing up and restoring your SINBHA PostgreSQL database safely.

---

## 1. Quick One-Command Backup (Automated)

You can run the built-in backup tool at any time:

```bash
# Backs up the active database specified in DATABASE_URL
python scripts/db_backup_restore.py --action backup --file backup_2026.sql
```

---

## 2. Manual Backup with `pg_dump`

If you are using PostgreSQL directly or through a cloud provider (Neon / Supabase):

```bash
# General Syntax:
pg_dump "postgresql://username:password@host:5432/sinbha" -F p -f sinbha_backup.sql

# With parameters:
pg_dump -h localhost -p 5432 -U postgres -d sinbha -F p -f sinbha_backup.sql
```

### Options Breakdown:
* `-F p`: Plain SQL format (human-readable and portable).
* `-f sinbha_backup.sql`: Output filename.
* `--no-owner --no-acl`: Prevents ownership permission errors when restoring to another user or machine.

---

## 3. Manual Restore with `psql`

To restore your data into a fresh PostgreSQL database:

```bash
# Step 1 (Optional): Create clean database if it doesn't exist
createdb -U postgres sinbha_new

# Step 2: Restore the SQL file into the database
psql "postgresql://username:password@host:5432/sinbha_new" -f sinbha_backup.sql
```

---

## 4. Testing a Restore Cycle

To verify that your backups work without touching your production database, run:

```bash
python scripts/db_backup_restore.py --action test
```

This automatically:
1. Generates a fresh SQL dump from your current database.
2. Restores it into a clean temporary database.
3. Confirms that all tables and records are intact.
