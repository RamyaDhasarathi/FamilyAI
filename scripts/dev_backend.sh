#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR/../backend"

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

echo "Applying database migrations..."
alembic upgrade head

echo "Starting Family OS backend on http://0.0.0.0:8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
