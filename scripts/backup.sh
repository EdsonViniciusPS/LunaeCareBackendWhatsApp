#!/usr/bin/env bash
# ==============================================================================
# Lunae Care Backend WhatsApp - Script de Backup Automático em Produção
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/backups"
RETENTION_DAYS=14
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_ROOT"

# Carrega variáveis do .env se existir
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

DB_USER="${POSTGRES_USER:-lunae_user}"
DB_NAME="${POSTGRES_DB:-lunaecare_whatsapp}"
DB_CONTAINER="whatsapp-db"

SQL_BACKUP="${BACKUP_DIR}/backup_${DB_NAME}_${TIMESTAMP}.sql.gz"
EVOLUTION_BACKUP="${BACKUP_DIR}/backup_evolution_${TIMESTAMP}.tar.gz"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Iniciando backup da base de dados PostgreSQL..."
if docker compose exec -T "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists | gzip > "$SQL_BACKUP"; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup do PostgreSQL salvo com sucesso em: $SQL_BACKUP ($(du -h "$SQL_BACKUP" | cut -f1))"
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERRO ao realizar backup do PostgreSQL!" >&2
    exit 1
fi

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Iniciando backup dos tokens de sessão da Evolution API..."
PROJECT_NAME=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]')
EVOLUTION_VOLUME=$(docker volume ls --format '{{.Name}}' | grep -E "${PROJECT_NAME}_evolution_instances_data|evolution_instances_data" | head -n 1 || echo "")

if [ -n "$EVOLUTION_VOLUME" ]; then
    docker run --rm -v "${EVOLUTION_VOLUME}:/data:ro" -v "${BACKUP_DIR}:/backup" alpine tar -czf "/backup/backup_evolution_${TIMESTAMP}.tar.gz" -C /data .
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup das sessões salvo em: $EVOLUTION_BACKUP"
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Volume da Evolution API não encontrado ou sem sessões para arquivar."
fi

# Rotação de backups antigos
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Limpando backups com mais de ${RETENTION_DAYS} dias..."
find "$BACKUP_DIR" -type f -name "backup_*" -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Rotina de backup finalizada com sucesso."
