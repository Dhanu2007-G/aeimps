#!/bin/bash
# Restore AEIMPS from backup

set -e

if [ -z "$1" ]; then
    echo "Usage: restore.sh <backup_directory>"
    echo "Example: restore.sh /backups/20260609"
    exit 1
fi

BACKUP_DIR="$1"
POSTGRES_PASSWORD=$(cat /run/secrets/postgres_password)

echo "=== AEIMPS Restore Started ==="
echo "Source: $BACKUP_DIR"

# Find backup files
POSTGRES_BACKUP=$(ls "$BACKUP_DIR"/postgres_*.dump 2>/dev/null | tail -1)
REDIS_BACKUP=$(ls "$BACKUP_DIR"/redis_*.rdb.gz 2>/dev/null | tail -1)
NEO4J_BACKUP=$(ls "$BACKUP_DIR"/neo4j_*.json.gz 2>/dev/null | tail -1)
QDRANT_BACKUP=$(ls "$BACKUP_DIR"/qdrant_*.tar.gz 2>/dev/null | tail -1)

# Restore PostgreSQL
if [ -n "$POSTGRES_BACKUP" ]; then
    echo "Restoring PostgreSQL from $POSTGRES_BACKUP..."
    PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
        -h "$POSTGRES_HOST" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --clean \
        --if-exists \
        "$POSTGRES_BACKUP"
    echo "✓ PostgreSQL restored"
else
    echo "⚠ No PostgreSQL backup found"
fi

# Restore Redis
if [ -n "$REDIS_BACKUP" ]; then
    echo "Restoring Redis from $REDIS_BACKUP..."
    gunzip -c "$REDIS_BACKUP" > /tmp/dump.rdb
    redis-cli -h "$REDIS_HOST" -a "$(cat /run/secrets/redis_password)" SHUTDOWN NOSAVE || true
    sleep 2
    cp /tmp/dump.rdb /redis_data/dump.rdb
    echo "✓ Redis backup copied (restart Redis to load)"
else
    echo "⚠ No Redis backup found"
fi

# Restore Neo4j
if [ -n "$NEO4J_BACKUP" ]; then
    echo "Restoring Neo4j from $NEO4J_BACKUP..."
    echo "⚠ Neo4j restore requires manual import via Cypher or apoc.import.json"
    echo "Backup file: $NEO4J_BACKUP"
else
    echo "⚠ No Neo4j backup found"
fi

# Restore Qdrant
if [ -n "$QDRANT_BACKUP" ]; then
    echo "Restoring Qdrant from $QDRANT_BACKUP..."
    tar -xzf "$QDRANT_BACKUP" -C /qdrant_data/
    echo "✓ Qdrant restored"
else
    echo "⚠ No Qdrant backup found"
fi

echo "=== Restore Complete ==="
echo "Note: Restart services to apply changes"
