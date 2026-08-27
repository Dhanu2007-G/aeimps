#!/bin/bash
# Cleanup old backups based on retention policy

BACKUP_DIR="/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

echo "=== Backup Cleanup ==="
echo "Retention: $RETENTION_DAYS days"

# Find and delete old backup directories
find "$BACKUP_DIR" -maxdepth 1 -type d -name "202*" -mtime +$RETENTION_DAYS -exec rm -rf {} \;

echo "Current backups:"
du -sh "$BACKUP_DIR"/*/ 2>/dev/null || echo "No backups found"

echo "✓ Cleanup complete"
