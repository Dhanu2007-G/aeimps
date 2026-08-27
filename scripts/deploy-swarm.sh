#!/bin/bash
# Deploy AEIMPS to Docker Swarm

set -e

STACK_NAME="aeimps"
COMPOSE_FILE="docker-stack.yml"

echo "=== AEIMPS Docker Swarm Deployment ==="

# Check if Swarm is initialized
if ! docker info | grep -q "Swarm: active"; then
    echo "Docker Swarm is not initialized. Run: docker swarm init"
    exit 1
fi

# Create secrets if they don't exist
echo "Creating Docker secrets..."

create_secret() {
    local secret_name=$1
    local prompt=$2
    
    if docker secret ls | grep -q "$secret_name"; then
        echo "✓ Secret $secret_name already exists"
    else
        echo -n "$prompt"
        read -s secret_value
        echo
        echo "$secret_value" | docker secret create "$secret_name" -
        echo "✓ Created secret $secret_name"
    fi
}

create_secret "postgres_password" "Enter PostgreSQL password: "
create_secret "redis_password" "Enter Redis password: "
create_secret "neo4j_password" "Enter Neo4j password: "
create_secret "secret_key" "Enter application secret key (64+ chars): "
create_secret "anthropic_api_key" "Enter Anthropic API key (optional, press Enter to skip): "
create_secret "grafana_admin_password" "Enter Grafana admin password: "

# Build images
echo ""
echo "Building images..."
docker build -t aeimps-api:latest -f backend/Dockerfile backend/
docker build -t aeimps-frontend:latest -f frontend/Dockerfile frontend/
docker build -t aeimps-backup:latest -f infrastructure/backup/Dockerfile infrastructure/backup/

# Deploy stack
echo ""
echo "Deploying stack..."
docker stack deploy -c "$COMPOSE_FILE" "$STACK_NAME"

echo ""
echo "=== Deployment complete! ==="
echo ""
echo "Check status:"
echo "  docker stack services $STACK_NAME"
echo "  docker stack ps $STACK_NAME"
echo ""
echo "View logs:"
echo "  docker service logs -f ${STACK_NAME}_api"
echo ""
echo "Remove stack:"
echo "  docker stack rm $STACK_NAME"
