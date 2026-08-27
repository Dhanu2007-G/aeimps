#!/bin/bash
set -e
echo "AEIMPS Backup Service Starting..."
echo "Schedule: ${BACKUP_SCHEDULE:-0 2 * * *}"
echo "Retention: ${BACKUP_RETENTION_DAYS:-7} days"
exec "$@"
