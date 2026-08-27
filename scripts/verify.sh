#!/bin/bash
# AEIMPS System Verification Script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 AEIMPS System Verification"
echo "=============================="

ERRORS=0
WARNINGS=0

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((ERRORS++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

# 1. Check Docker
echo -e "\n[1/10] Docker Environment"
if command -v docker &> /dev/null; then
    check_pass "Docker installed: $(docker --version | cut -d' ' -f3)"
else
    check_fail "Docker not installed"
fi

if docker compose version &> /dev/null; then
    check_pass "Docker Compose available"
else
    check_fail "Docker Compose not available"
fi

# 2. Check File Structure
echo -e "\n[2/10] File Structure"
[ -f "docker-compose.yml" ] && check_pass "docker-compose.yml exists" || check_fail "docker-compose.yml missing"
[ -f ".env" ] && check_pass ".env file exists" || check_warn ".env file missing (run: cp .env.example .env)"
[ -d "backend" ] && check_pass "backend/ directory exists" || check_fail "backend/ directory missing"
[ -d "frontend" ] && check_pass "frontend/ directory exists" || check_fail "frontend/ directory missing"

# 3. Check Database Migration Files
echo -e "\n[3/10] Database Migrations"
[ -f "backend/alembic/versions/001_initial_schema.py" ] && check_pass "Initial migration exists" || check_fail "Initial migration missing"
[ -f "backend/alembic/versions/002_add_auth_rbac_audit.py" ] && check_pass "Auth/RBAC migration exists" || check_fail "Auth/RBAC migration missing"

# 4. Check Python Dependencies
echo -e "\n[4/10] Python Dependencies"
if [ -f "backend/pyproject.toml" ]; then
    if grep -q "python-jose" backend/pyproject.toml; then
        check_pass "python-jose dependency added"
    else
        check_warn "python-jose missing in pyproject.toml"
    fi
    if grep -q "python3-saml" backend/pyproject.toml; then
        check_pass "python3-saml dependency added"
    else
        check_warn "python3-saml missing in pyproject.toml"
    fi
fi

# 5. Check Services
echo -e "\n[5/10] Docker Services"
if docker compose ps | grep -q "Up"; then
    check_pass "Docker services are running"
    
    # Check specific services
    docker compose ps | grep -q "postgres.*Up" && check_pass "PostgreSQL running" || check_warn "PostgreSQL not running"
    docker compose ps | grep -q "redis.*Up" && check_pass "Redis running" || check_warn "Redis not running"
    docker compose ps | grep -q "api.*Up" && check_pass "API service running" || check_warn "API service not running"
else
    check_warn "Docker services not running (run: docker compose up -d)"
fi

# 6. Check API Health
echo -e "\n[6/10] API Health Check"
if curl -sf http://localhost:8000/api/v1/admin/health > /dev/null 2>&1; then
    check_pass "API responding at http://localhost:8000"
else
    check_warn "API not responding (may still be starting)"
fi

# 7. Check Database Connection
echo -e "\n[7/10] Database Connection"
if docker compose exec -T postgres pg_isready -U aeimps > /dev/null 2>&1; then
    check_pass "PostgreSQL accepting connections"
    
    # Check if tables exist
    TABLES=$(docker compose exec -T postgres psql -U aeimps -d aeimps -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
    if [ "$TABLES" -gt 10 ]; then
        check_pass "Database tables exist ($TABLES tables)"
    else
        check_warn "Database tables missing (run: make migrate)"
    fi
else
    check_warn "Cannot connect to PostgreSQL"
fi

# 8. Check Admin User
echo -e "\n[8/10] Default Admin User"
if docker compose exec -T postgres psql -U aeimps -d aeimps -t -c "SELECT email FROM users WHERE role='admin' LIMIT 1;" 2>/dev/null | grep -q "admin@aeimps.local"; then
    check_pass "Default admin user exists (admin@aeimps.local)"
else
    check_warn "Admin user not found (migration may not have run)"
fi

# 9. Check Documentation
echo -e "\n[9/10] Documentation Files"
[ -f "docs/DEPLOYMENT.md" ] && check_pass "DEPLOYMENT.md exists" || check_fail "DEPLOYMENT.md missing"
[ -f "docs/ENCRYPTION.md" ] && check_pass "ENCRYPTION.md exists" || check_fail "ENCRYPTION.md missing"
[ -f "PRODUCTION_READINESS.md" ] && check_pass "PRODUCTION_READINESS.md exists" || check_fail "PRODUCTION_READINESS.md missing"
[ -f "GETTING_STARTED.md" ] && check_pass "GETTING_STARTED.md exists" || check_fail "GETTING_STARTED.md missing"

# 10. Check Configuration Files
echo -e "\n[10/10] Configuration Files"
[ -f "docker-stack.yml" ] && check_pass "Docker Swarm stack file exists" || check_fail "docker-stack.yml missing"
[ -f "infrastructure/prometheus/alerts.yml" ] && check_pass "Prometheus alerts configured" || check_fail "alerts.yml missing"
[ -f "infrastructure/grafana/dashboards/system-overview.json" ] && check_pass "Grafana dashboard exists" || check_fail "Grafana dashboard missing"

# Summary
echo -e "\n=============================="
echo "Verification Summary"
echo "=============================="

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "System is ready. Next steps:"
    echo "1. Start services: docker compose up -d"
    echo "2. Run migrations: make migrate"
    echo "3. Run demo: bash demo.sh"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ $WARNINGS warning(s) found${NC}"
    echo ""
    echo "System is mostly ready. Address warnings above."
    exit 0
else
    echo -e "${RED}✗ $ERRORS error(s) found${NC}"
    echo -e "${YELLOW}⚠ $WARNINGS warning(s) found${NC}"
    echo ""
    echo "Please fix errors before proceeding."
    echo "See GETTING_STARTED.md for detailed instructions."
    exit 1
fi
