#!/usr/bin/env bash
# Render Build Script for SINBHA
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "📦 Step 1: Upgrading pip and installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "🔄 Step 2: Running Alembic database migrations..."
python -m alembic upgrade head

echo "✅ Build complete! Database is up to date and dependencies are installed."
