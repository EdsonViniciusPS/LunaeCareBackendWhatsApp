#!/usr/bin/env bash
# ==============================================================================
# Lunae Care Backend WhatsApp - Script de Restauração de Backup
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

DB_USER="${POSTGRES_USER:-lunae_user}"
DB_NAME="${POSTGRES_DB:-lunaecare_whatsapp}"
DB_CONTAINER="whatsapp-db"

BACKUP_FILE="${1:-}"

if [ -z "$BACKUP_FILE" ]; then
    echo -e "${RED}[ERRO]${NC} Especifique o arquivo de backup a ser restaurado."
    echo -e "Uso: $0 backups/backup_lunaecare_whatsapp_YYYYMMDD_HHMMSS.sql.gz [backup_evolution_YYYYMMDD.tar.gz]"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}[ERRO]${NC} Arquivo de backup não encontrado: $BACKUP_FILE"
    exit 1
fi

echo -e "${YELLOW}=================================================================="
echo "    ATENÇÃO: RESTAURAÇÃO DE BASE DE DADOS EM PRODUÇÃO           "
echo "==================================================================${NC}"
echo -e "Você está prestes a sobrescrever a base de dados: ${CYAN}${DB_NAME}${NC}"
echo -e "A partir do arquivo: ${CYAN}${BACKUP_FILE}${NC}"
echo ""
read -p "Tem certeza absoluta de que deseja continuar? (digite 'CONFIRMAR'): " CONFIRMATION

if [ "$CONFIRMATION" != "CONFIRMAR" ]; then
    echo -e "${YELLOW}Operação abortada pelo usuário.${NC}"
    exit 0
fi

echo -e "${CYAN}Restaurando base de dados PostgreSQL...${NC}"
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gzip -dc "$BACKUP_FILE" | docker compose exec -T "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
else
    cat "$BACKUP_FILE" | docker compose exec -T "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
fi

echo -e "${GREEN}[OK] Banco de dados restaurado com sucesso!${NC}"

# Restauração opcional do volume da Evolution API
EVOLUTION_BACKUP="${2:-}"
if [ -n "$EVOLUTION_BACKUP" ] && [ -f "$EVOLUTION_BACKUP" ]; then
    echo -e "${CYAN}Restaurando dados de sessão da Evolution API...${NC}"
    PROJECT_NAME=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]')
    EVOLUTION_VOLUME=$(docker volume ls --format '{{.Name}}' | grep -E "${PROJECT_NAME}_evolution_instances_data|evolution_instances_data" | head -n 1 || echo "")
    
    if [ -n "$EVOLUTION_VOLUME" ]; then
        docker run --rm -v "${EVOLUTION_VOLUME}:/data" -v "$(dirname "$EVOLUTION_BACKUP"):/backup" alpine sh -c "rm -rf /data/* && tar -xzf /backup/$(basename "$EVOLUTION_BACKUP") -C /data"
        docker compose restart evolution-api
        echo -e "${GREEN}[OK] Volume da Evolution API restaurado e serviço reiniciado!${NC}"
    fi
fi

# Reinicia a aplicação para atualizar pools de conexão e validar migrações
echo -e "${CYAN}Reiniciando containers da aplicação...${NC}"
docker compose restart lunaecare-whatsapp whatsapp-worker

echo -e "${GREEN}Processo de restauração finalizado com sucesso!${NC}"
