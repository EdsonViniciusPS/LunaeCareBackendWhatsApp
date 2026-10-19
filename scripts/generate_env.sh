#!/usr/bin/env bash
# ==============================================================================
# Lunae Care - Gerador Automático do arquivo .env para Produção
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_ROOT}/.env"

echo "=========================================================="
echo "    Gerador Automático de Configurações (.env)           "
echo "=========================================================="

if [ -f "$ENV_FILE" ]; then
    read -p "O arquivo .env já existe. Deseja sobrescrever? (s/N): " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[sS]$ ]]; then
        echo "Operação cancelada. O arquivo .env existente foi mantido."
        exit 0
    fi
fi

echo ""
echo "Gerando chaves criptográficas seguras..."
INTERNAL_KEY=$(openssl rand -hex 32)
WEBHOOK_SEC=$(openssl rand -hex 32)
ENCRYPTION_SEC=$(openssl rand -hex 32)
EVOLUTION_KEY=$(openssl rand -hex 32)
DB_PASS=$(openssl rand -hex 24)

echo ""
read -p "Digite o segredo JWT do Lunae Care (pressione Enter para gerar um novo): " USER_JWT
JWT_SEC="${USER_JWT:-$(openssl rand -hex 32)}"

read -p "Digite as URLs do seu frontend separadas por vírgula [padrão: https://app.lunaecare.com.br]: " USER_CORS
CORS_VAL="${USER_CORS:-https://app.lunaecare.com.br}"

cat <<EOF > "$ENV_FILE"
# ==============================================================================
# Lunae Care - Configurações de Produção (Gerado Automaticamente)
# ==============================================================================
ENVIRONMENT=production
DEBUG=false
PORT=8000
API_BIND_ADDRESS=127.0.0.1
WEB_CONCURRENCY=2
CORS_ORIGINS=${CORS_VAL}

# Segurança e Autenticação Interna
INTERNAL_API_KEY=${INTERNAL_KEY}
WEBHOOK_SECRET=${WEBHOOK_SEC}

# Token JWT das Clínicas
JWT_SECRET=${JWT_SEC}
JWT_ALGORITHM=HS256
JWT_ISSUER=lunaecare
JWT_AUDIENCE=lunaecare-whatsapp
JWT_CLINIC_CLAIM=clinic_id

# Criptografia em Repouso (Fernet)
ENCRYPTION_KEY=${ENCRYPTION_SEC}

# Banco de Dados PostgreSQL
POSTGRES_USER=lunae_user
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_DB=lunaecare_whatsapp

DATABASE_URL=postgresql+asyncpg://lunae_user:${DB_PASS}@whatsapp-db:5432/lunaecare_whatsapp
DATABASE_SYNC_URL=postgresql+psycopg2://lunae_user:${DB_PASS}@whatsapp-db:5432/lunaecare_whatsapp

# Redis & Filas
REDIS_URL=redis://whatsapp-redis:6379/0
SCHEDULER_INTERVAL_SECONDS=60

# Provedor WhatsApp (Evolution API)
WHATSAPP_PROVIDER=evolution
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_API_KEY=${EVOLUTION_KEY}
EVOLUTION_WEBHOOK_URL=http://lunaecare-whatsapp:8000/api/v1/whatsapp/webhooks/evolution
EVOLUTION_MOCK_MODE=false
EOF

chmod 600 "$ENV_FILE"

echo ""
echo "[OK] Arquivo .env gerado com sucesso em: $ENV_FILE"
echo "Todas as chaves de segurança foram geradas com entropia criptográfica forte."
echo ""
