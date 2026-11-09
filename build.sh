#!/usr/bin/env bash
# Render Build Script for SINBHA
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "📦 Step 1: Upgrading pip and installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "🔄 Step 2: Initializing database schema..."
if command -v alembic &> /dev/null; then
    alembic upgrade head || echo "Alembic handled or skipped."
fi
python -c "import app.database; app.database.init_db(); print('Database verified and initialized.')"

echo "✅ Build complete! Database is up to date and dependencies are installed."
