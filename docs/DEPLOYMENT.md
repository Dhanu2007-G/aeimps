# AEIMPS Production Deployment Guide

## Overview
This guide covers deploying AEIMPS as a production-ready MVP for on-premise enterprise environments supporting 5-20 users with up to 10K documents.

## Prerequisites

### Hardware Requirements
- **CPU**: 16+ cores recommended
- **RAM**: 64GB+ recommended
- **Storage**: 500GB+ SSD (data) + 100GB (backups)
- **GPU**: Optional (24GB VRAM for vision features)

### Software Requirements
- Docker Engine 24.0+
- Docker Compose 2.20+ (for development)
- Docker Swarm (for production clustering)
- Linux OS (Ubuntu 22.04 LTS recommended)

## Quick Start (Development)

```bash
# 1. Clone and configure
git clone <repo>
cd aeimps
cp .env.example .env

# 2. Edit .env - set required values
# - SECRET_KEY (64+ random characters)
# - POSTGRES_PASSWORD
# - REDIS_PASSWORD
# - NEO4J_PASSWORD
# - ANTHROPIC_API_KEY (optional)

# 3. Start services
make dev

# 4. Wait ~60s, then initialize
make migrate
docker compose exec api python -c "from app.db.qdrant import init_collections; from app.db.neo4j import init_constraints; import asyncio; asyncio.run(init_collections()); asyncio.run(init_constraints())"

# 5. Create admin user (already created via migration)
# Default: admin@aeimps.local / admin123 (CHANGE THIS!)

# 6. Access
# API: http://localhost:8000/docs
# Frontend: http://localhost:3000
# Grafana: http://localhost:3001 (admin / grafana_secret)
```

## Production Deployment (Docker Swarm)

### Step 1: Initialize Swarm

```bash
# On manager node
docker swarm init

# On worker nodes (if multi-node)
docker swarm join --token <token> <manager-ip>:2377
```

### Step 2: Create Docker Secrets

```bash
# Navigate to project directory
cd aeimps

# Run deployment script (creates secrets interactively)
bash scripts/deploy-swarm.sh

# Or create secrets manually:
echo "your-postgres-password" | docker secret create postgres_password -
echo "your-redis-password" | docker secret create redis_password -
echo "your-neo4j-password" | docker secret create neo4j_password -
echo "your-64-char-secret-key" | docker secret create secret_key -
echo "your-anthropic-api-key" | docker secret create anthropic_api_key -
echo "your-grafana-password" | docker secret create grafana_admin_password -
```

### Step 3: Build Images

```bash
# Build application images
docker build -t aeimps-api:latest -f backend/Dockerfile backend/
docker build -t aeimps-frontend:latest -f frontend/Dockerfile frontend/
docker build -t aeimps-backup:latest -f infrastructure/backup/Dockerfile infrastructure/backup/
```

### Step 4: Deploy Stack

```bash
docker stack deploy -c docker-stack.yml aeimps
```

### Step 5: Verify Deployment

```bash
# Check service status
docker stack services aeimps

# View logs
docker service logs -f aeimps_api

# Check health
curl http://localhost/api/v1/admin/health
```

### Step 6: Run Database Migrations

```bash
docker exec $(docker ps -q -f name=aeimps_api) alembic upgrade head
```

### Step 7: Change Default Admin Password

```bash
# Login at http://localhost/auth/login
# Email: admin@aeimps.local
# Password: admin123

# Then immediately change via API or create new admin user
```

## Configuration

### Environment Variables (docker-stack.yml)

Key variables:
- `APP_URL`: Base URL for SAML and redirects
- `ENVIRONMENT`: production/staging/development
- `LOG_LEVEL`: INFO/DEBUG/WARNING
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Token lifetime (default: 60)
- `BACKUP_RETENTION_DAYS`: Backup retention (default: 7)

### SSL/TLS Configuration

Add nginx service to docker-stack.yml with SSL certificates:

```yaml
nginx:
  image: nginx:alpine
  ports:
    - "443:443"
  volumes:
    - ./infrastructure/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - /etc/letsencrypt:/etc/letsencrypt:ro
```

## SSO Configuration

### Okta Setup

1. Login to Okta admin console
2. Create new SAML 2.0 app integration
3. Configure:
   - Single sign-on URL: `https://your-domain.com/api/v1/auth/saml/acs`
   - Audience URI: `https://your-domain.com/api/v1/auth/saml/metadata`
4. Download metadata or copy entity ID, SSO URL, and certificate
5. Add via admin API:

```bash
curl -X POST https://your-domain.com/api/v1/admin/saml-config \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "Okta SSO",
    "provider": "okta",
    "entity_id": "http://www.okta.com/...",
    "sso_url": "https://your-org.okta.com/app/...",
    "x509_cert": "MIID...",
    "attribute_mapping": {
      "email": "email",
      "name": "displayName",
      "groups": "groups"
    },
    "role_mapping": {
      "AEIMPS_Admins": "admin",
      "AEIMPS_Managers": "manager"
    }
  }'
```

### Azure AD Setup

Similar to Okta:
- Enterprise Application → New Application → SAML
- Reply URL: `https://your-domain.com/api/v1/auth/saml/acs`
- Configure group claims in token

## Backup & Disaster Recovery

### Automated Backups

Backups run daily at 2 AM (configurable via `BACKUP_SCHEDULE`).

View backup status:
```bash
docker service logs aeimps_backup
ls -lh /var/lib/docker/volumes/aeimps_backup_data/_data/
```

### Manual Backup

```bash
docker exec $(docker ps -q -f name=aeimps_backup) /usr/local/bin/backup.sh
```

### Restore from Backup

```bash
# 1. Stop services
docker stack rm aeimps

# 2. Restore data
docker run --rm -v aeimps_backup_data:/backups \
  -v aeimps_postgres_data:/var/lib/postgresql/data \
  --network aeimps-net \
  aeimps-backup:latest /usr/local/bin/restore.sh /backups/20260609

# 3. Restart services
docker stack deploy -c docker-stack.yml aeimps
```

## Monitoring & Alerting

### Access Dashboards

- **Grafana**: http://localhost:3001 (admin / <grafana_password>)
- **Prometheus**: http://localhost:9090
- **API Metrics**: http://localhost:8000/metrics

### Configure AlertManager

Edit `infrastructure/prometheus/alertmanager.yml`:

```yaml
route:
  receiver: 'email'
receivers:
  - name: 'email'
    email_configs:
      - to: 'ops@your-domain.com'
        from: 'alerts@your-domain.com'
        smarthost: 'smtp.gmail.com:587'
        auth_username: 'alerts@your-domain.com'
        auth_password: '<app-password>'
```

## User Management

### Create Users via API

```bash
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "email": "user@example.com",
    "full_name": "John Doe",
    "password": "SecurePass123!",
    "role": "analyst"
  }'
```

### Roles & Permissions

- **Admin**: Full system access, user management
- **Manager**: Document management, agent workflows
- **Analyst**: Search, agent workflows, read documents
- **Viewer**: Read-only access

## Scaling

### Horizontal Scaling

Scale API and workers:
```bash
docker service scale aeimps_api=4
docker service scale aeimps_worker-doc-processor=2
```

### Add Worker Nodes

```bash
# On new node
docker swarm join --token <worker-token> <manager-ip>:2377

# Label node for specific workloads (optional)
docker node update --label-add gpu=true worker-node-1
```

## Troubleshooting

### Service Won't Start

```bash
# Check service logs
docker service logs aeimps_api

# Check events
docker service ps aeimps_api --no-trunc

# Verify secrets
docker secret ls
```

### Database Connection Issues

```bash
# Test PostgreSQL
docker exec $(docker ps -q -f name=aeimps_postgres) \
  psql -U aeimps -d aeimps -c "SELECT 1"

# Check database logs
docker service logs aeimps_postgres
```

### Performance Issues

```bash
# Check resource usage
docker stats

# View Grafana dashboards
# Navigate to: http://localhost:3001/d/system-overview
```

## Security Checklist

- [ ] Changed default admin password
- [ ] Configured SSL/TLS certificates
- [ ] Set strong SECRET_KEY (64+ random characters)
- [ ] Enabled firewall (allow only 80, 443, 22)
- [ ] Configured backup encryption
- [ ] Set up log rotation
- [ ] Reviewed audit logs regularly
- [ ] Configured SSO/SAML for production
- [ ] Set resource quotas per user
- [ ] Enabled rate limiting

## Maintenance

### Update Application

```bash
# Build new images
docker build -t aeimps-api:v2 backend/

# Update service (rolling update)
docker service update --image aeimps-api:v2 aeimps_api

# Rollback if needed
docker service rollback aeimps_api
```

### Database Maintenance

```bash
# Vacuum and analyze
docker exec $(docker ps -q -f name=aeimps_postgres) \
  psql -U aeimps -d aeimps -c "VACUUM ANALYZE"

# Check database size
docker exec $(docker ps -q -f name=aeimps_postgres) \
  psql -U aeimps -d aeimps -c "SELECT pg_size_pretty(pg_database_size('aeimps'))"
```

## Support

For issues:
1. Check logs: `docker service logs <service-name>`
2. Review metrics in Grafana
3. Check audit logs for security issues
4. Verify backups are running

## Appendix

### Useful Commands

```bash
# Stack management
docker stack ls
docker stack ps aeimps
docker stack rm aeimps

# Service management
docker service ls
docker service ps aeimps_api
docker service logs -f aeimps_api

# Secret management
docker secret ls
docker secret rm old_secret
docker secret create new_secret -

# Volume management
docker volume ls
docker volume inspect aeimps_postgres_data

# Network management
docker network ls
docker network inspect aeimps-net
```

### Port Reference

- 80/443: HTTP/HTTPS (nginx)
- 8000: API (internal)
- 3000: Frontend (internal)
- 3001: Grafana
- 5432: PostgreSQL (internal)
- 6379: Redis (internal)
- 6333: Qdrant (internal)
- 7474/7687: Neo4j (internal)
- 9090: Prometheus (internal)
