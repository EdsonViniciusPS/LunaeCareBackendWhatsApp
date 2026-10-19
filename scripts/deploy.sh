#!/usr/bin/env bash
# ==============================================================================
# Lunae Care Backend WhatsApp - Script de Deploy / Atualização em Produção
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[AVISO]${NC} $1"; }
log_error() { echo -e "${RED}[ERRO]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${CYAN}"
echo "=================================================================="
echo "    Iniciando Deploy do Lunae Care WhatsApp Backend              "
echo "=================================================================="
echo -e "${NC}"

# 1. Validação do arquivo .env
if [ ! -f .env ]; then
    log_error "Arquivo .env não encontrado na raiz do projeto ($PROJECT_ROOT/.env)!"
    log_info "Copie o arquivo de exemplo e configure suas chaves de produção:"
    echo "  cp .env.production.example .env"
    echo "  nano .env"
    exit 1
fi

# 2. Verificação de Segurança Pré-deploy
log_info "Validando configurações de segurança no .env..."
if grep -q "change_me" .env || grep -q "substitua_com" .env; then
    log_error "O arquivo .env ainda contém valores padrão ou placeholders inseguros!"
    log_error "Gere chaves criptográficas fortes antes de subir em produção:"
    echo "  openssl rand -hex 32"
    exit 1
fi

# 3. Atualização de Código do Repositório (se for repositório git)
if [ -d .git ]; then
    log_info "Atualizando código fonte via Git..."
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    git pull origin "$CURRENT_BRANCH" || log_warn "Não foi possível puxar via git pull. Prosseguindo com código local."
fi

# 4. Pull das Imagens Base Externas
log_info "Baixando imagens base atualizadas do PostgreSQL, Redis e Evolution API..."
docker compose pull whatsapp-db whatsapp-redis evolution-api

# 5. Build da Imagem da Aplicação
log_info "Construindo imagem Docker da aplicação (FastAPI + Worker)..."
docker compose build --pull

# 6. Inicialização dos Containers
log_info "Iniciando/atualizando serviços do Docker Compose..."
docker compose up -d --remove-orphans

# 7. Aguarda a Saúde dos Serviços (Healthcheck)
log_info "Aguardando serviços ficarem saudáveis e migrações do Alembic executarem..."
RETRIES=30
DELAY=2
BACKEND_HEALTHY=false

for i in $(seq 1 $RETRIES); do
    if curl -s -f http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
        BACKEND_HEALTHY=true
        break
    fi
    echo -n "."
    sleep $DELAY
done
echo ""

if [ "$BACKEND_HEALTHY" = true ]; then
    log_success "Backend FastAPI está online e respondendo em http://127.0.0.1:8000"
else
    log_error "O backend não respondeu ao healthcheck dentro do tempo limite!"
    log_info "Exibindo últimos logs do container lunaecare-whatsapp:"
    docker compose logs --tail=40 lunaecare-whatsapp
    exit 1
fi

# 8. Validação de Saúde Integrada (Banco + Redis + Provedor)
log_info "Consultando endpoint de métricas de saúde operacional (/api/v1/whatsapp/metrics/system-health)..."
HEALTH_PAYLOAD=$(curl -s http://127.0.0.1:8000/api/v1/whatsapp/metrics/system-health || echo "{}")
echo "$HEALTH_PAYLOAD" | jq . 2>/dev/null || echo "$HEALTH_PAYLOAD"

# 9. Status dos Containers
echo ""
log_info "Status dos containers ativos:"
docker compose ps

echo ""
echo -e "${GREEN}=================================================================="
echo "    Deploy concluído com sucesso!                                "
echo "==================================================================${NC}"
echo ""
echo -e "Comandos úteis para monitoramento:"
echo -e "  Acompanhar logs ao vivo: ${CYAN}docker compose logs -f${NC}"
echo -e "  Logs apenas do backend:  ${CYAN}docker compose logs -f lunaecare-whatsapp${NC}"
echo -e "  Logs do worker/scheduler:${CYAN}docker compose logs -f whatsapp-worker${NC}"
echo -e "  Reiniciar serviços:      ${CYAN}docker compose restart${NC}"
echo ""
