#!/bin/bash
# AEIMPS Quick Start - Automated Setup

set -e

echo "🚀 AEIMPS Quick Start Setup"
echo "============================"

# Check if running from correct directory
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: Please run this script from the aeimps/ directory"
    exit 1
fi

# Step 1: Create .env if missing
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    
    # Generate random SECRET_KEY
    SECRET_KEY=$(openssl rand -base64 48)
    sed -i.bak "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
    
    echo "✓ .env created with random SECRET_KEY"
    echo "⚠️  Review and update .env with your values"
else
    echo "✓ .env file already exists"
fi

# Step 2: Create data directories
echo ""
echo "📁 Creating data directories..."
mkdir -p data/raw data/models
echo "✓ Directories created"

# Step 3: Start infrastructure services
echo ""
echo "🐳 Starting infrastructure services..."
docker compose up -d postgres redis neo4j qdrant

echo "⏳ Waiting for databases to be ready (30 seconds)..."
sleep 30

# Step 4: Check database health
echo ""
echo "🔍 Checking database connectivity..."
if docker compose exec -T postgres pg_isready -U aeimps > /dev/null 2>&1; then
    echo "✓ PostgreSQL is ready"
else
    echo "❌ PostgreSQL not ready. Check logs: docker compose logs postgres"
    exit 1
fi

# Step 5: Run migrations
echo ""
echo "🗄️  Running database migrations..."
docker compose run --rm api alembic upgrade head
echo "✓ Migrations complete"

# Step 6: Initialize Qdrant and Neo4j
echo ""
echo "🔧 Initializing Qdrant collections..."
docker compose run --rm api python -c "
import asyncio
from app.db.qdrant import init_collections
asyncio.run(init_collections())
print('✓ Qdrant initialized')
" || echo "⚠️  Qdrant initialization failed (may not be critical)"

echo ""
echo "🔧 Initializing Neo4j constraints..."
docker compose run --rm api python -c "
import asyncio
from app.db.neo4j import init_constraints
asyncio.run(init_constraints())
print('✓ Neo4j initialized')
" || echo "⚠️  Neo4j initialization failed (may not be critical)"

# Step 7: Start all services
echo ""
echo "🚀 Starting all services..."
docker compose up -d

echo "⏳ Waiting for services to start (20 seconds)..."
sleep 20

# Step 8: Verify API
echo ""
echo "🔍 Verifying API health..."
if curl -sf http://localhost:8000/api/v1/admin/health > /dev/null 2>&1; then
    echo "✓ API is healthy"
else
    echo "⚠️  API health check failed (may still be starting)"
fi

# Step 9: Display access information
echo ""
echo "=============================="
echo "✅ Setup Complete!"
echo "=============================="
echo ""
echo "Access Points:"
echo "  • API:      http://localhost:8000"
echo "  • API Docs: http://localhost:8000/docs"
echo "  • Frontend: http://localhost:3000"
echo "  • Grafana:  http://localhost:3001"
echo ""
echo "Default Admin Login:"
echo "  Email:    admin@aeimps.local"
echo "  Password: admin123"
echo "  ⚠️  CHANGE THIS PASSWORD IMMEDIATELY!"
echo ""
echo "Next Steps:"
echo "  1. Test login:"
echo "     curl -X POST http://localhost:8000/api/v1/auth/login \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"email\":\"admin@aeimps.local\",\"password\":\"admin123\"}'"
echo ""
echo "  2. Run demo:"
echo "     bash scripts/demo.sh"
echo ""
echo "  3. View logs:"
echo "     docker compose logs -f api"
echo ""
echo "  4. Run verification:"
echo "     bash scripts/verify.sh"
echo ""
echo "Documentation:"
echo "  • Getting Started: GETTING_STARTED.md"
echo "  • Deployment:      docs/DEPLOYMENT.md"
echo "  • Production:      PRODUCTION_READINESS.md"
echo ""
