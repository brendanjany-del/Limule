#!/bin/bash
##############################################################################
# Limule - Script de déploiement complet pour VPS OVH Rocky Linux 9
#
# Usage : sudo bash deploy.sh
#
# Ce script installe et configure :
#   1. Docker + Docker Compose
#   2. Git + clone du repo
#   3. PostgreSQL + Redis + App + Worker (via Docker Compose)
#   4. Nginx reverse proxy + Let's Encrypt HTTPS (limulidae.fr)
#   5. Firewall (firewalld)
#   6. Seed de la BDD avec les données d'exemple
#
# VPS : Rocky Linux 9 - OVH
# Domaine : limulidae.fr
##############################################################################

set -euo pipefail

# ── Configuration ──
DOMAIN="limulidae.fr"
APP_DIR="/opt/limule"
REPO_URL="https://github.com/brendanjany-del/Limule.git"
BRANCH="claude/banking-data-pipeline-e8e8x"
DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
APP_SECRET=$(openssl rand -base64 32 | tr -d '/+=' | head -c 48)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

##############################################################################
# Vérifications préalables
##############################################################################

if [[ $EUID -ne 0 ]]; then
    fail "Ce script doit être exécuté en root (sudo bash deploy.sh)"
fi

info "Déploiement Limule sur ${DOMAIN}"
info "Mot de passe BDD généré : ${DB_PASSWORD}"
echo ""

##############################################################################
# 1. Mise à jour du système
##############################################################################

info "Étape 1/7 - Mise à jour du système..."
dnf update -y -q
dnf install -y -q git curl wget vim firewalld
log "Système à jour"

##############################################################################
# 2. Installation de Docker
##############################################################################

info "Étape 2/7 - Installation de Docker..."

if command -v docker &>/dev/null; then
    warn "Docker déjà installé ($(docker --version))"
else
    dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    dnf install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin

    systemctl enable docker
    systemctl start docker

    # Permettre à l'utilisateur rocky d'utiliser Docker
    usermod -aG docker rocky 2>/dev/null || true

    log "Docker installé ($(docker --version))"
fi

# Vérifier Docker Compose
docker compose version &>/dev/null || fail "Docker Compose non disponible"
log "Docker Compose OK"

##############################################################################
# 3. Clone du repo
##############################################################################

info "Étape 3/7 - Récupération du code source..."

if [[ -d "${APP_DIR}" ]]; then
    warn "Répertoire ${APP_DIR} existant, mise à jour..."
    cd "${APP_DIR}"
    git fetch origin "${BRANCH}"
    git checkout "${BRANCH}"
    git pull origin "${BRANCH}"
else
    git clone -b "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
    cd "${APP_DIR}"
fi

log "Code source récupéré dans ${APP_DIR}"

##############################################################################
# 4. Configuration de l'application
##############################################################################

info "Étape 4/7 - Configuration de l'application..."

# Fichier .env pour Docker Compose
cat > "${APP_DIR}/.env" <<ENVEOF
# Généré automatiquement par deploy.sh le $(date -Iseconds)
POSTGRES_USER=limule
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=limule
DATABASE_URL=postgresql+asyncpg://limule:${DB_PASSWORD}@db:5432/limule
DATABASE_URL_SYNC=postgresql+psycopg2://limule:${DB_PASSWORD}@db:5432/limule
REDIS_URL=redis://redis:6379/0
DATA_INPUT_DIR=/app/data/input
DATA_OUTPUT_DIR=/app/data/output
APP_SECRET=${APP_SECRET}
ENVEOF

chmod 600 "${APP_DIR}/.env"

# Docker Compose de production (override)
cat > "${APP_DIR}/docker-compose.prod.yml" <<'DCEOF'
services:
  db:
    image: postgres:16-alpine
    restart: always
    env_file: .env
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U limule"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    restart: always
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redisdata:/data

  app:
    build: .
    restart: always
    env_file: .env
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - ./data:/app/data

  worker:
    build: .
    restart: always
    command: celery -A app.worker worker -l info -c 2
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - ./data:/app/data

volumes:
  pgdata:
  redisdata:
DCEOF

# Créer les répertoires de données
mkdir -p "${APP_DIR}/data/input" "${APP_DIR}/data/output"
chown -R 1000:1000 "${APP_DIR}/data" 2>/dev/null || true

log "Configuration créée (.env + docker-compose.prod.yml)"

##############################################################################
# 5. Lancement des conteneurs
##############################################################################

info "Étape 5/7 - Construction et lancement des conteneurs..."

cd "${APP_DIR}"
docker compose -f docker-compose.prod.yml build --quiet
docker compose -f docker-compose.prod.yml up -d

# Attendre que PostgreSQL soit prêt
info "Attente de PostgreSQL..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.prod.yml exec -T db pg_isready -U limule &>/dev/null; then
        break
    fi
    sleep 2
done

docker compose -f docker-compose.prod.yml exec -T db pg_isready -U limule &>/dev/null \
    || fail "PostgreSQL n'a pas démarré"

log "Conteneurs démarrés"

# Seed de la BDD
info "Seed de la base de données..."
docker compose -f docker-compose.prod.yml exec -T app python -m scripts.seed_database
docker compose -f docker-compose.prod.yml exec -T app python -m scripts.generate_sample_data

log "Base de données initialisée"

##############################################################################
# 6. Nginx + Let's Encrypt
##############################################################################

info "Étape 6/7 - Installation de Nginx + HTTPS..."

dnf install -y -q nginx

# Configuration Nginx
cat > /etc/nginx/conf.d/limule.conf <<NGEOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        allow all;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN} www.${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias /opt/limule/app/static/;
        expires 30d;
    }
}
NGEOF

# Config Nginx temporaire (HTTP only) pour obtenir le certificat
cat > /etc/nginx/conf.d/limule-temp.conf <<TMPEOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        allow all;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
TMPEOF

# Désactiver la config HTTPS temporairement (pas encore de certificat)
mv /etc/nginx/conf.d/limule.conf /etc/nginx/conf.d/limule.conf.disabled

# Supprimer la config par défaut si elle existe
rm -f /etc/nginx/conf.d/default.conf 2>/dev/null || true

mkdir -p /var/www/certbot

# SELinux : autoriser Nginx à faire du proxy
setsebool -P httpd_can_network_connect 1 2>/dev/null || true

systemctl enable nginx
systemctl restart nginx

log "Nginx démarré (HTTP)"

# Let's Encrypt avec certbot
if ! command -v certbot &>/dev/null; then
    dnf install -y -q epel-release
    dnf install -y -q certbot python3-certbot-nginx
fi

info "Obtention du certificat SSL pour ${DOMAIN}..."
certbot certonly --webroot \
    -w /var/www/certbot \
    -d "${DOMAIN}" -d "www.${DOMAIN}" \
    --non-interactive \
    --agree-tos \
    --email "admin@${DOMAIN}" \
    --no-eff-email \
    2>&1 || {
    warn "Certbot a échoué. Le site sera accessible en HTTP uniquement."
    warn "Vous pourrez relancer : certbot certonly --webroot -w /var/www/certbot -d ${DOMAIN}"
    warn "Puis : mv /etc/nginx/conf.d/limule.conf.disabled /etc/nginx/conf.d/limule.conf"
    warn "       rm /etc/nginx/conf.d/limule-temp.conf && systemctl restart nginx"
}

# Si le certificat a été obtenu, activer HTTPS
if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    mv /etc/nginx/conf.d/limule.conf.disabled /etc/nginx/conf.d/limule.conf
    rm -f /etc/nginx/conf.d/limule-temp.conf
    systemctl restart nginx
    log "HTTPS activé pour ${DOMAIN}"

    # Renouvellement automatique
    systemctl enable certbot-renew.timer 2>/dev/null || true
    systemctl start certbot-renew.timer 2>/dev/null || true
    log "Renouvellement automatique du certificat activé"
else
    info "Site accessible en HTTP : http://${DOMAIN}"
fi

##############################################################################
# 7. Firewall
##############################################################################

info "Étape 7/7 - Configuration du firewall..."

systemctl enable firewalld
systemctl start firewalld

firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload

log "Firewall configuré (SSH + HTTP + HTTPS)"

##############################################################################
# Résumé
##############################################################################

echo ""
echo "================================================================="
echo -e "${GREEN}  Déploiement terminé !${NC}"
echo "================================================================="
echo ""
echo -e "  Application   : ${BLUE}https://${DOMAIN}${NC}"
echo -e "  API Swagger   : ${BLUE}https://${DOMAIN}/docs${NC}"
echo ""
echo -e "  BDD PostgreSQL: limule:${DB_PASSWORD}@localhost:5432/limule"
echo -e "  Redis         : localhost:6379"
echo ""
echo "  Commandes utiles :"
echo "    cd ${APP_DIR}"
echo "    docker compose -f docker-compose.prod.yml logs -f     # Logs"
echo "    docker compose -f docker-compose.prod.yml restart app  # Redémarrer"
echo "    docker compose -f docker-compose.prod.yml down         # Arrêter"
echo "    docker compose -f docker-compose.prod.yml up -d        # Démarrer"
echo ""
echo "  Credentials sauvegardés dans : ${APP_DIR}/.env"
echo ""
echo -e "${YELLOW}  N'oubliez pas de supprimer la clé SSH temporaire !${NC}"
echo "    sed -i '/limule-deploy-temp/d' /home/rocky/.ssh/authorized_keys"
echo ""
echo "================================================================="
