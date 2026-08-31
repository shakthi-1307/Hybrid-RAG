#!/bin/sh
set -e

# Migrations are the API's job. Running them here too would have two
# containers racing for the same Alembic lock on every deploy, and the worker
# has nothing useful to do until the schema exists anyway.
#
# The check greps for the literal "(head)" marker that `alembic current` prints
# when the database is at the latest revision. Parsing the revision id out of
# that output instead looks tidier and is wrong: env.py prints its own
# "alembic: connecting to ..." line first, so a pattern matching hex
# characters happily matches the "a" in "alembic" and the worker waits
# forever comparing 'a' against the real head.
echo "Waiting for migrations to reach head..."

attempt=0
max_attempts=150   # 150 * 2s = 5 minutes, enough for a slow first migration

while [ "$attempt" -lt "$max_attempts" ]; do
    if alembic current 2>/dev/null | grep -q '(head)'; then
        echo "Schema is at head; starting worker."
        exec python -m app.worker
    fi

    attempt=$((attempt + 1))
    # Only report every tenth attempt: at one line per two seconds this would
    # otherwise bury the API's migration output, which is what you actually
    # need to read when a migration is failing.
    if [ $((attempt % 10)) -eq 0 ]; then
        echo "Still waiting for migrations (attempt $attempt/$max_attempts)..."
        alembic current 2>&1 | grep -v '^alembic: connecting' || true
    fi
    sleep 2
done

echo "Migrations did not reach head within $((max_attempts * 2))s." >&2
echo "Check the api container's logs — it runs them." >&2
exit 1
