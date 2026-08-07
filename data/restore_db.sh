#!/usr/bin/env bash
# ─── Lovreski DB restore for Amvera Cloud ────────────────────────────────────
# Restores lovreski_db_backup.tar.gz into a fresh MongoDB instance.
#
# Usage:
#   MONGO_URI="mongodb://user:pass@host:27017/lovreski?authSource=admin" \
#     ./restore_db.sh lovreski_db_backup.tar.gz
#
# If MONGO_URI is not set, defaults to mongodb://localhost:27017/lovreski.
set -euo pipefail

BACKUP_FILE="${1:-lovreski_db_backup.tar.gz}"
TARGET_URI="${MONGO_URI:-mongodb://localhost:27017}"
TARGET_DB="${DB_NAME:-lovreski}"
SOURCE_DB="test_database"   # DB name inside the dump

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "❌ Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if ! command -v mongorestore >/dev/null 2>&1; then
  echo "❌ mongorestore is not installed. Install mongodb-database-tools:"
  echo "   https://www.mongodb.com/docs/database-tools/installation/"
  exit 1
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "→ Extracting $BACKUP_FILE …"
tar -xzf "$BACKUP_FILE" -C "$TMPDIR"

echo "→ Restoring into $TARGET_URI (db: $TARGET_DB) …"
mongorestore \
  --uri="$TARGET_URI" \
  --nsFrom="${SOURCE_DB}.*" \
  --nsTo="${TARGET_DB}.*" \
  --drop \
  "$TMPDIR/dump"

echo "✅ Restore complete."
echo "→ Verify with: mongosh \"$TARGET_URI/$TARGET_DB\" --eval 'db.users.countDocuments({})'"
