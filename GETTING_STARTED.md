# Getting AEIMPS Fully Functional - Step-by-Step Guide

## Current Status
✅ Code is 90% complete
⚠️ System needs: dependency installation, migration, configuration, testing

## Step-by-Step Execution Plan

---

## Phase 1: Fix Dependencies & Build Issues (30 minutes)

### 1. Install Missing Python Dependencies

```bash
cd aeimps/backend

# Add missing dependencies to pyproject.toml
cat >> pyproject.toml <<'EOF'

# Additional dependencies for production features
dependencies = [
    # ... (existing dependencies)
    "python-jose[cryptography]>=3.3.0",
    "python3-saml>=1.16.0",
]
EOF

# Install all dependencies
pip install -e .
```

### 2. Fix Import Issues

The code has potential import issues. Let's verify:

```bash
# Test imports
cd aeimps/backend
python -c "
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import User, UserRole
from app.services.auth_service import AuthService
print('✓ All imports working')
"
```

**If errors occur:** Check these common issues:
- Missing `__init__.py` files in new directories
- Circular import issues
- Missing pydantic model imports

### 3. Update .env File

```bash
cd aeimps
cp .env.example .env

# Edit .env with these MINIMUM required values:
cat > .env <<'EOF'
# Core
ENVIRONMENT=development
LOG_LEVEL=INFO
SECRET_KEY=your-super-secret-key-minimum-64-characters-long-change-this-now
APP_URL=http://localhost:8000

# Database
POSTGRES_DB=aeimps
POSTGRES_USER=aeimps
POSTGRES_PASSWORD=aeimps_dev_password

# Redis
REDIS_PASSWORD=redis_dev_password

# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_dev_password

# AI (optional for testing)
ANTHROPIC_API_KEY=your-key-or-leave-empty
MOCK_MODELS=true

# JWT
JWT_SECRET_KEY=another-64-character-secret-for-jwt-tokens-change-this
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Files
RAW_FILES_PATH=/data/raw
MODEL_CACHE_PATH=/data/models
MAX_FILE_SIZE_MB=100

# Grafana
GRAFANA_PASSWORD=admin123
EOF
```

---

## Phase 2: Database Setup & Migration (15 minutes)

### 1. Start Infrastructure Services

```bash
cd aeimps

# Start only databases first
docker compose up -d postgres redis neo4j qdrant

# Wait for services to be ready (30 seconds)
sleep 30

# Verify services are up
docker compose ps
```

### 2. Run Database Migrations

```bash
# Make sure backend is accessible
cd backend

# Run migration
alembic upgrade head

# If error: "No such file or directory: alembic.ini"
# Make sure you're in backend/ directory
```

**Expected Output:**
```
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Add user auth, RBAC, audit logging
```

### 3. Verify Database Tables

```bash
docker compose exec postgres psql -U aeimps -d aeimps -c "
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
"
```

**Expected tables:**
- users
- audit_logs
- resource_quotas
- retention_policies
- saml_configs
- api_keys
- documents
- document_chunks
- agent_sessions
- etc.

### 4. Verify Default Admin User

```bash
docker compose exec postgres psql -U aeimps -d aeimps -c "
SELECT email, role, status FROM users;
"
```

**Expected:** admin@aeimps.local with role 'admin' and status 'active'

---

## Phase 3: Start All Services (10 minutes)

### 1. Build and Start Everything

```bash
cd aeimps

# Build images
docker compose build

# Start all services
docker compose up -d

# Check status
docker compose ps

# Follow logs
docker compose logs -f api
```

### 2. Wait for Services to Initialize

```bash
# Check API health
curl http://localhost:8000/api/v1/admin/health

# Should return JSON with service statuses
```

### 3. Initialize Qdrant Collections

```bash
docker compose exec api python -c "
import asyncio
from app.db.qdrant import init_collections
asyncio.run(init_collections())
print('✓ Qdrant collections initialized')
"
```

### 4. Initialize Neo4j Constraints

```bash
docker compose exec api python -c "
import asyncio
from app.db.neo4j import init_constraints
asyncio.run(init_constraints())
print('✓ Neo4j constraints initialized')
"
```

---

## Phase 4: Test Authentication System (15 minutes)

### 1. Test Admin Login

```bash
# Login as admin
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@aeimps.local",
    "password": "admin123"
  }' | jq

# Save the access_token from response
```

**Expected:** JSON with `access_token`, `refresh_token`, and `user` object

### 2. Test Protected Endpoint

```bash
# Replace YOUR_TOKEN with actual token from step 1
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN" | jq
```

**Expected:** User details with email, role, etc.

### 3. Test User Registration

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "full_name": "Test User",
    "password": "TestPass123!",
    "role": "analyst"
  }' | jq
```

### 4. Test RBAC

```bash
# Login as test user (analyst)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"TestPass123!"}' \
  | jq -r .access_token)

# Try to create user (should fail - admin only)
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "another@example.com",
    "full_name": "Another User",
    "password": "Pass123!",
    "role": "viewer"
  }'
```

**Expected:** 403 Forbidden error

---

## Phase 5: Test Core Functionality (20 minutes)

### 1. Test Document Upload

```bash
# Get admin token
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@aeimps.local","password":"admin123"}' \
  | jq -r .access_token)

# Create test document
echo "This is a test document for AEIMPS demo." > test.txt

# Upload document
curl -X POST http://localhost:8000/api/v1/ingest/document \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@test.txt" \
  -F "tags=demo,test"
```

### 2. Test Audit Logs

```bash
# View audit logs
curl http://localhost:8000/api/v1/admin/users/audit-logs \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq
```

**Expected:** List of logged actions including recent API calls

### 3. Test Quota System

```bash
# Check quota usage
curl http://localhost:8000/api/v1/admin/quota/usage \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq
```

### 4. Test API Documentation

Open browser: http://localhost:8000/docs

**Verify:**
- Auth endpoints visible
- User management endpoints visible
- Admin endpoints visible
- All models documented

---

## Phase 6: Create Demo Script (10 minutes)

### Create Automated Demo

```bash
cat > demo.sh <<'EOF'
#!/bin/bash
set -e

echo "🚀 AEIMPS Production MVP Demo"
echo "================================"

BASE_URL="http://localhost:8000"

# 1. Admin Login
echo -e "\n1️⃣ Logging in as Admin..."
ADMIN_TOKEN=$(curl -s -X POST $BASE_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@aeimps.local","password":"admin123"}' \
  | jq -r .access_token)
echo "✓ Admin authenticated"

# 2. Create Users
echo -e "\n2️⃣ Creating demo users..."
curl -s -X POST $BASE_URL/api/v1/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "manager@demo.com",
    "full_name": "Demo Manager",
    "password": "Manager123!",
    "role": "manager"
  }' > /dev/null
echo "✓ Manager created"

curl -s -X POST $BASE_URL/api/v1/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "analyst@demo.com",
    "full_name": "Demo Analyst",
    "password": "Analyst123!",
    "role": "analyst"
  }' > /dev/null
echo "✓ Analyst created"

# 3. Test RBAC
echo -e "\n3️⃣ Testing RBAC permissions..."
ANALYST_TOKEN=$(curl -s -X POST $BASE_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"analyst@demo.com","password":"Analyst123!"}' \
  | jq -r .access_token)

echo "Testing analyst trying to create user (should fail)..."
RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST $BASE_URL/api/v1/admin/users \
  -H "Authorization: Bearer $ANALYST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","full_name":"Test","password":"Pass123!","role":"viewer"}')

if [ "$RESULT" = "403" ]; then
  echo "✓ RBAC working correctly (403 Forbidden)"
else
  echo "✗ RBAC failed (got $RESULT)"
fi

# 4. Check Audit Logs
echo -e "\n4️⃣ Checking audit logs..."
AUDIT_COUNT=$(curl -s $BASE_URL/api/v1/admin/users/audit-logs \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '. | length')
echo "✓ Found $AUDIT_COUNT audit log entries"

# 5. Check Quotas
echo -e "\n5️⃣ Checking resource quotas..."
curl -s $BASE_URL/api/v1/admin/quota/usage \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.documents'

# 6. Test Health Check
echo -e "\n6️⃣ Checking system health..."
curl -s $BASE_URL/api/v1/admin/health | jq '.services | keys'

echo -e "\n✅ Demo Complete!"
echo "================================"
echo "Access points:"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Grafana:   http://localhost:3001 (admin/admin123)"
echo "  Frontend:  http://localhost:3000"
EOF

chmod +x demo.sh
./demo.sh
```

---

## Phase 7: Verify Monitoring (5 minutes)

### 1. Check Prometheus

```bash
# Open Prometheus
open http://localhost:9090

# Run query:
http_requests_total
```

### 2. Check Grafana

```bash
# Open Grafana
open http://localhost:3001

# Login: admin / admin123
# Navigate to Dashboards → AEIMPS System Overview
```

### 3. Verify Metrics Collection

```bash
curl http://localhost:8000/metrics
```

**Should see:** Prometheus metrics format with app metrics

---

## Phase 8: Test Backup System (10 minutes)

### 1. Manual Backup

```bash
docker compose exec backup /usr/local/bin/backup.sh
```

### 2. Verify Backup Files

```bash
docker compose exec backup ls -lh /backups/
```

### 3. Test Verification

```bash
docker compose exec backup /usr/local/bin/verify.sh /backups/$(date +%Y%m%d)
```

---

## Common Issues & Fixes

### Issue 1: Migration Fails

```bash
# Reset and retry
docker compose down -v
docker compose up -d postgres redis
sleep 10
cd backend
alembic upgrade head
```

### Issue 2: Import Errors

```bash
# Fix Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/backend"

# Or add to .env:
echo "PYTHONPATH=/app" >> .env
```

### Issue 3: Services Not Starting

```bash
# Check logs
docker compose logs api

# Restart specific service
docker compose restart api
```

### Issue 4: Can't Connect to Database

```bash
# Verify PostgreSQL is running
docker compose exec postgres pg_isready

# Check connection string in .env
# Should match: postgresql+asyncpg://aeimps:password@postgres:5432/aeimps
```

---

## Production Checklist Before Demo

- [ ] All services running (`docker compose ps`)
- [ ] Database migration complete (`alembic current`)
- [ ] Admin user exists (test login)
- [ ] API documentation accessible (http://localhost:8000/docs)
- [ ] Grafana accessible (http://localhost:3001)
- [ ] Health check returns 200 (curl http://localhost:8000/api/v1/admin/health)
- [ ] Audit logs collecting
- [ ] Backup system tested
- [ ] Demo script runs successfully

---

## Final Demo Flow

1. **Show Authentication**: Login, JWT tokens, refresh
2. **Show RBAC**: Different roles, permission denials
3. **Show Audit Logs**: Every action tracked
4. **Show User Management**: Create/edit/delete users
5. **Show Quotas**: Resource limits by role
6. **Show Monitoring**: Grafana dashboards
7. **Show Backup**: Manual backup, verification
8. **Show API Docs**: Auto-generated documentation

---

## Quick Commands Reference

```bash
# Start system
docker compose up -d

# Stop system
docker compose down

# View logs
docker compose logs -f api

# Run tests
cd backend && pytest tests/

# Access shell
docker compose exec api bash

# Reset everything
docker compose down -v
make dev && make migrate
```

---

## Next Steps After Demo

1. Change default passwords
2. Configure SSL/TLS
3. Set up SSO (Okta/Azure AD)
4. Run load tests
5. Deploy to production (Docker Swarm)

Ready to execute? Start with Phase 1! 🚀
