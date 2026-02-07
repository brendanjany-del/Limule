#!/bin/bash
##############################################################################
# Limule - Script de mise à jour
# Usage : sudo bash /opt/limule/deploy/update.sh
##############################################################################

set -euo pipefail

APP_DIR="/opt/limule"
BRANCH="claude/banking-data-pipeline-e8e8x"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[i]${NC} Mise à jour de Limule..."

cd "${APP_DIR}"

git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull origin "${BRANCH}"

echo -e "${BLUE}[i]${NC} Reconstruction des conteneurs..."
docker compose -f docker-compose.prod.yml build --quiet
docker compose -f docker-compose.prod.yml up -d

echo -e "${GREEN}[✓]${NC} Mise à jour terminée !"
echo -e "  Vérifier : docker compose -f docker-compose.prod.yml logs -f app"
