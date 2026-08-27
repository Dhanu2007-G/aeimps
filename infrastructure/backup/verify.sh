#!/bin/bash
# Verify backup integrity

BACKUP_DIR="$1"

echo "Verifying backups in $BACKUP_DIR..."

verify_file() {
    if [ -f "$1" ]; then
        if [ -s "$1" ]; then
            echo "✓ $1 ($(du -h "$1" | cut -f1))"
            return 0
        else
            echo "✗ $1 is empty"
            return 1
        fi
    else
        echo "✗ $1 not found"
        return 1
    fi
}

ERRORS=0

# Verify PostgreSQL backup
POSTGRES_BACKUP=$(ls "$BACKUP_DIR"/postgres_*.dump 2>/dev/null | tail -1)
verify_file "$POSTGRES_BACKUP" || ((ERRORS++))

# Verify Redis backup
REDIS_BACKUP=$(ls "$BACKUP_DIR"/redis_*.rdb.gz 2>/dev/null | tail -1)
verify_file "$REDIS_BACKUP" || ((ERRORS++))

# Verify Neo4j backup
NEO4J_BACKUP=$(ls "$BACKUP_DIR"/neo4j_*.json.gz 2>/dev/null | tail -1)
verify_file "$NEO4J_BACKUP" || ((ERRORS++))

# Verify Qdrant backup
QDRANT_BACKUP=$(ls "$BACKUP_DIR"/qdrant_*.tar.gz 2>/dev/null | tail -1)
verify_file "$QDRANT_BACKUP" || ((ERRORS++))

if [ $ERRORS -eq 0 ]; then
    echo "✓ All backups verified successfully"
    exit 0
else
    echo "✗ $ERRORS backup(s) failed verification"
    exit 1
fi
