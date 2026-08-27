#!/bin/bash
# Automated backup script for AEIMPS

set -e

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE_DIR="$BACKUP_DIR/$(date +%Y%m%d)"

mkdir -p "$DATE_DIR"

echo "=== AEIMPS Backup Started: $TIMESTAMP ==="

# Read passwords from secrets
POSTGRES_PASSWORD=$(cat /run/secrets/postgres_password)
REDIS_PASSWORD=$(cat /run/secrets/redis_password)
NEO4J_PASSWORD=$(cat /run/secrets/neo4j_password)

# PostgreSQL Backup
echo "Backing up PostgreSQL..."
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$POSTGRES_HOST" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --format=custom \
    --compress=9 \
    --file="$DATE_DIR/postgres_$TIMESTAMP.dump"
echo "✓ PostgreSQL backup complete: $(du -h "$DATE_DIR/postgres_$TIMESTAMP.dump" | cut -f1)"

# Redis Backup
echo "Backing up Redis..."
redis-cli -h "$REDIS_HOST" -a "$REDIS_PASSWORD" --rdb "$DATE_DIR/redis_$TIMESTAMP.rdb" SAVE
sleep 2
cp /redis_data/dump.rdb "$DATE_DIR/redis_$TIMESTAMP.rdb" 2>/dev/null || echo "Warning: Redis RDB copy failed"
gzip "$DATE_DIR/redis_$TIMESTAMP.rdb"
echo "✓ Redis backup complete"

# Neo4j Backup
echo "Backing up Neo4j..."
curl -u "neo4j:$NEO4J_PASSWORD" \
    -H "Accept: application/json" \
    -X POST "http://$NEO4J_HOST:7474/db/neo4j/tx/commit" \
    -d '{"statements":[{"statement":"CALL apoc.export.json.all(null,{stream:true})"}]}' \
    > "$DATE_DIR/neo4j_$TIMESTAMP.json"
gzip "$DATE_DIR/neo4j_$TIMESTAMP.json"
echo "✓ Neo4j backup complete"

# Qdrant Backup
echo "Backing up Qdrant..."
if [ -d "/qdrant_data" ]; then
    tar -czf "$DATE_DIR/qdrant_$TIMESTAMP.tar.gz" -C /qdrant_data .
    echo "✓ Qdrant backup complete: $(du -h "$DATE_DIR/qdrant_$TIMESTAMP.tar.gz" | cut -f1)"
else
    echo "Warning: Qdrant data directory not found"
fi

# Create backup manifest
cat > "$DATE_DIR/manifest.txt" <<EOF
Backup Date: $TIMESTAMP
PostgreSQL: postgres_$TIMESTAMP.dump
Redis: redis_$TIMESTAMP.rdb.gz
Neo4j: neo4j_$TIMESTAMP.json.gz
Qdrant: qdrant_$TIMESTAMP.tar.gz
EOF

echo "=== Backup Complete ==="
echo "Location: $DATE_DIR"
du -sh "$DATE_DIR"

# Run verification
/usr/local/bin/verify.sh "$DATE_DIR"
