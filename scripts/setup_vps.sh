#!/usr/bin/env bash
# ==============================================================================
# Lunae Care - Script de Provisionamento Inicial para VPS Hostinger Ubuntu
# Suporta: Ubuntu 22.04 LTS e Ubuntu 24.04 LTS
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[AVISO]${NC} $1"; }
log_error() { echo -e "${RED}[ERRO]${NC} $1"; }

if [ "$EUID" -ne 0 ]; then
  log_error "Execute este script como root ou via sudo."
  exit 1
fi

echo -e "${CYAN}"
echo "=================================================================="
echo "    Lunae Care Backend WhatsApp - Configuração de VPS Ubuntu     "
echo "=================================================================="
echo -e "${NC}"

# 1. Atualização do Sistema Operacional
log_info "1/7 Atualizando pacotes do sistema operacional..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -o Dpkg::Options::="--force-confold"

# 2. Instalação de Utilitários Essenciais
log_info "2/7 Instalando dependências e ferramentas essenciais..."
apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    ufw \
    fail2ban \
    htop \
    jq \
    unzip \
    gzip \
    ca-certificates \
    gnupg \
    lsb-release \
    nginx \
    certbot \
    python3-certbot-nginx

log_success "Utilitários instalados com sucesso."

# 3. Configuração de Memória Swap (2GB) se inexistente
log_info "3/7 Verificando memória Swap..."
SWAP_EXISTS=$(swapon --show | wc -l)
if [ "$SWAP_EXISTS" -le 1 ]; then
    log_info "Configurando 2GB de Swap para estabilidade do PostgreSQL e containers..."
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.d/99-swappiness.conf
    log_success "Swap de 2GB ativado."
else
    log_success "Memória Swap já configurada."
fi

# 4. Instalação do Docker Engine e Docker Compose (Repositório Oficial)
log_info "4/7 Instalando Docker Engine oficial..."
if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    log_success "Docker Engine e Docker Compose instalados."
else
    log_success "Docker já está instalado."
fi

# 5. Configuração Global de Rotação de Logs do Docker
log_info "5/7 Configurando rotação global de logs no Docker (/etc/docker/daemon.json)..."
mkdir -p /etc/docker
cat <<EOF > /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "20m",
    "max-file": "5"
  }
}
EOF
systemctl reload docker || systemctl restart docker
log_success "Rotação de logs configurada."

# 6. Configuração de Firewall UFW
log_info "6/7 Configurando Firewall UFW..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP (Let s Encrypt / Nginx)'
ufw allow 443/tcp comment 'HTTPS (Nginx)'
# Assegura que portas internas (8000, 5432, 6379, 8080) NÃO fiquem abertas externamente
ufw --force enable
log_success "Firewall UFW ativo. Portas liberadas: 22 (SSH), 80 (HTTP), 443 (HTTPS)."

# 7. Configuração do Fail2ban para SSH
log_info "7/7 Ativando Fail2ban para proteção contra força bruta em SSH..."
systemctl enable fail2ban
systemctl restart fail2ban
log_success "Fail2ban ativo."

echo ""
echo -e "${GREEN}=================================================================="
echo "    Provisionamento da VPS Hostinger concluído com sucesso!      "
echo "==================================================================${NC}"
echo ""
echo -e "Próximos passos:"
echo -e " 1. Clone o repositório na pasta desejada (ex: ${CYAN}/opt/lunaecare/whatsapp${NC})"
echo -e " 2. Crie o arquivo .env: ${CYAN}cp .env.production.example .env${NC}"
echo -e " 3. Gere chaves seguras com: ${CYAN}openssl rand -hex 32${NC} e preencha no .env"
echo -e " 4. Configure o Nginx e obtenha o certificado SSL Let's Encrypt"
echo -e " 5. Execute: ${CYAN}bash scripts/deploy.sh${NC}"
echo ""
