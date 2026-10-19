# Guia de Deploy em Produção — VPS Hostinger (Ubuntu 22.04 / 24.04 LTS)

**Projeto:** `LunaeCareBackendWhatsApp`  
**Destino:** VPS KVM Hostinger rodando Ubuntu  
**Stack de Produção:** FastAPI (Uvicorn Multi-worker), Worker RQ (Scheduler periódicos), PostgreSQL 16 Alpine, Redis 7 Alpine, Evolution API v2.2.2, Nginx com SSL Let's Encrypt (Certbot) e UFW Firewall.

---

## 1. Visão Geral da Arquitetura em Produção

```
               INTERNET PÚBLICA (HTTPS porta 443)
                             │
                             ▼
              ┌─────────────────────────────┐
              │  Nginx Reverse Proxy + SSL  │  (Let's Encrypt Certbot)
              │  Rate Limit / HSTS / Gzip   │  (Porta 80 -> 443 301 Redirect)
              └──────────────┬──────────────┘
                             │  http://127.0.0.1:8000
                             ▼
┌───────────────────────────────────────────────────────────────┐
│                       DOCKER COMPOSE                          │
│                                                               │
│   ┌───────────────────────────────────────────────────────┐   │
│   │ lunaecare-whatsapp (FastAPI Uvicorn Workers)         │   │
│   │ Porta 8000 (apenas 127.0.0.1 - isolada da internet)  │   │
│   └───────────────┬───────────────────────────┬───────────┘   │
│                   │                           │               │
│                   ▼                           ▼               │
│   ┌───────────────────────────┐   ┌───────────────────────┐   │
│   │ whatsapp-db (Postgres 16) │   │ whatsapp-redis (v7)   │   │
│   │ Volume: whatsapp_db_data  │   │ Sliding window & RQ   │   │
│   └───────────────▲───────────┘   └───────────▲───────────┘   │
│                   │                           │               │
│   ┌───────────────┴───────────┐   ┌───────────┴───────────┐   │
│   │ evolution-api (v2.2.2)    │   │ whatsapp-worker       │   │
│   │ WhatsApp Baileys Engine   │   │ RQ Worker + Scheduler │   │
│   │ (Isolada internamente)    │   │ Disparo de lembretes  │   │
│   └───────────────────────────┘   └───────────────────────┘   │
│                                                               │
│        Rede Interna Bridge: whatsapp-internal                 │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. Requisitos Mínimos da VPS Hostinger

- **Plano Recomendado:** Hostinger VPS KVM 2 (mínimo de 2 vCPUs e 4 GB de RAM) ou superior.
- **Sistema Operacional:** Ubuntu 22.04 LTS 64-bit ou Ubuntu 24.04 LTS 64-bit.
- **Domínio / Subdomínio:** Registro tipo `A` apontando para o IP público da sua VPS:
  - Exemplo: `api-whatsapp.lunaecare.com.br` -> `IP_DA_HOSTINGER_VPS`

---

## 3. Passo a Passo de Instalação e Deploy

### Passo 1 — Conectar via SSH à VPS Hostinger

Abra o terminal do seu computador e conecte-se com o usuário `root`:
```bash
ssh root@<IP_DA_SUA_VPS>
```

---

### Passo 2 — Executar o Provisionamento Automatizado do Servidor

Criamos um script que configura automaticamente na sua VPS:
- Atualização do SO e utilitários essenciais (`curl`, `git`, `htop`, `jq`, `unzip`, `gzip`)
- **Memória Swap de 2GB** com `vm.swappiness=10` (evita travamentos de memória no Docker)
- **Docker Engine Oficial** + **Docker Compose Plugin**
- **Rotação global de logs do Docker** (evita esgotamento de disco com logs de containers)
- **Firewall UFW**: Portas 22 (SSH), 80 (HTTP) e 443 (HTTPS) liberadas; **portas 8000, 5432, 6379 e 8080 bloqueadas para a internet**
- **Fail2ban** ativo contra ataques de força bruta no SSH
- **Nginx** e **Certbot** para gerenciamento de SSL HTTPS

Execute na VPS:
```bash
# Baixa e executa o script de setup
curl -fsSL https://raw.githubusercontent.com/EdsonViniciusPS/LunaeCareBackendWhatsApp/main/scripts/setup_vps.sh -o /tmp/setup_vps.sh || true

# Caso o repositório seja privado ou prefira clonar primeiro:
mkdir -p /opt/lunaecare
cd /opt/lunaecare
git clone https://github.com/EdsonViniciusPS/LunaeCareBackendWhatsApp.git
cd LunaeCareBackendWhatsApp

# Executa o provisionamento da VPS:
sudo bash scripts/setup_vps.sh
```

---

### Passo 3 — Configurar o Arquivo `.env` de Produção

Copie o modelo de produção pronto para o arquivo `.env`:
```bash
cp .env.production.example .env
```

Agora, gere chaves criptográficas seguras com o comando nativo `openssl`:
```bash
echo "INTERNAL_API_KEY: $(openssl rand -hex 32)"
echo "WEBHOOK_SECRET:   $(openssl rand -hex 32)"
echo "ENCRYPTION_KEY:   $(openssl rand -hex 32)"
echo "EVOLUTION_KEY:    $(openssl rand -hex 32)"
echo "POSTGRES_PASS:    $(openssl rand -hex 24)"
```

Edite o arquivo `.env`:
```bash
nano .env
```

Preencha os campos com os valores gerados:
```ini
ENVIRONMENT=production
DEBUG=false
PORT=8000
API_BIND_ADDRESS=127.0.0.1
WEB_CONCURRENCY=2
CORS_ORIGINS=https://app.lunaecare.com.br

INTERNAL_API_KEY=<SUA_CHAVE_GERADA_32_BYTES>
WEBHOOK_SECRET=<SUA_CHAVE_GERADA_32_BYTES>
JWT_SECRET=<MESMA_CHAVE_DO_CORE_LUNAECARE_32_BYTES>
ENCRYPTION_KEY=<SUA_CHAVE_GERADA_32_BYTES>

POSTGRES_USER=lunae_user
POSTGRES_PASSWORD=<SUA_SENHA_FORTE_POSTGRES>
POSTGRES_DB=lunaecare_whatsapp

DATABASE_URL=postgresql+asyncpg://lunae_user:<SUA_SENHA_FORTE_POSTGRES>@whatsapp-db:5432/lunaecare_whatsapp
DATABASE_SYNC_URL=postgresql+psycopg2://lunae_user:<SUA_SENHA_FORTE_POSTGRES>@whatsapp-db:5432/lunaecare_whatsapp

REDIS_URL=redis://whatsapp-redis:6379/0
SCHEDULER_INTERVAL_SECONDS=60

WHATSAPP_PROVIDER=evolution
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_API_KEY=<SUA_CHAVE_EVOLUTION_32_BYTES>
EVOLUTION_WEBHOOK_URL=http://lunaecare-whatsapp:8000/api/v1/whatsapp/webhooks/evolution
EVOLUTION_MOCK_MODE=false
```

Salve e feche o arquivo (`Ctrl + O`, `Enter`, `Ctrl + X`).

---

### Passo 4 — Configurar DNS e Nginx com SSL Let's Encrypt

1. No **hPanel da Hostinger** (ou Cloudflare/Registro.br), crie o apontamento:
   - **Tipo:** `A`
   - **Nome:** `api-whatsapp` (ou subdomínio desejado)
   - **Destino / IP:** IP da sua VPS Hostinger
   - **TTL:** 300 segundos

2. Copie o arquivo de configuração do Nginx fornecido no projeto:
```bash
sudo cp nginx/lunaecare-whatsapp.conf /etc/nginx/sites-available/lunaecare-whatsapp.conf
```

3. Substitua `api-whatsapp.seudominio.com.br` pelo seu domínio real no arquivo:
```bash
sudo sed -i 's/api-whatsapp.seudominio.com.br/SEU_DOMINIO_AQUI/g' /etc/nginx/sites-available/lunaecare-whatsapp.conf
```

4. Emita o certificado SSL gratuito com Certbot:
```bash
sudo certbot --nginx -d SEU_DOMINIO_AQUI --non-interactive --agree-tos -m suporte@seudominio.com.br
```

5. Ative o site no Nginx e teste a sintaxe:
```bash
sudo ln -sf /etc/nginx/sites-available/lunaecare-whatsapp.conf /etc/nginx/sites-enabled/
# Remove site default se existir
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

### Passo 5 — Executar o Deploy Automatizado

Execute o script de deploy:
```bash
bash scripts/deploy.sh
```

O script realizará:
1. Validação de segurança do `.env` (bloqueia o startup se detectar chaves padrão `change_me`)
2. Pull das imagens atualizadas de PostgreSQL, Redis e Evolution API
3. Build da aplicação Python FastAPI
4. Execução automática das migrações do banco com `alembic upgrade head`
5. Inicialização de todos os containers com restart automático
6. Verificação do Healthcheck em `http://127.0.0.1:8000/api/v1/health`
7. Consulta das métricas em `/api/v1/whatsapp/metrics/system-health`

---

### Passo 6 — Configurar Inicialização Automática no Boot (Systemd)

Para garantir que a stack Docker Compose suba automaticamente caso a VPS seja reiniciada pela Hostinger:

```bash
sudo cp scripts/systemd/lunaecare-whatsapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lunaecare-whatsapp.service
```

---

### Passo 7 — Configurar Backup Automático Diário

Configure o agendamento no `crontab` para executar o backup todas as noites às 03:00 da manhã:

```bash
# Torna o script executável
chmod +x scripts/backup.sh scripts/restore.sh

# Adiciona ao crontab do root
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/lunaecare/LunaeCareBackendWhatsApp/scripts/backup.sh >> /var/log/lunae_backup.log 2>&1") | crontab -
```

O script de backup:
- Executa `pg_dump` no PostgreSQL e gera arquivos `.sql.gz` com timestamp
- Compacta os dados de instâncias da Evolution API em `.tar.gz`
- Remove automaticamente backups mais antigos que 14 dias
- Salva no diretório `/opt/lunaecare/LunaeCareBackendWhatsApp/backups`

---

## 4. Validação Pós-Deploy e Testes em Produção

Após finalizar o deploy, teste os endpoints a partir do seu navegador ou terminal externo:

### 1. Healthcheck Básico
```bash
curl -i https://SEU_DOMINIO_AQUI/api/v1/health
```
Resposta esperada (HTTP 200):
```json
{"status":"healthy"}
```

### 2. Saúde Integrada dos Serviços
```bash
curl -i https://SEU_DOMINIO_AQUI/api/v1/whatsapp/metrics/system-health
```
Resposta esperada (HTTP 200):
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "provider": "connected"
}
```

### 3. Verificar Headers de Segurança HTTP
```bash
curl -I https://SEU_DOMINIO_AQUI/
```
Verifique a presença obrigatória dos seguintes headers:
- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

---

## 5. Operação e Manutenção Diária

### Visualizar logs ao vivo de todos os serviços:
```bash
docker compose logs -f
```

### Visualizar logs específicos:
```bash
# Apenas API FastAPI:
docker compose logs -f lunaecare-whatsapp

# Apenas Worker e Scheduler de lembretes:
docker compose logs -f whatsapp-worker

# Evolution API (conexões e Baileys):
docker compose logs -f evolution-api

# Banco de dados PostgreSQL:
docker compose logs -f whatsapp-db
```

### Atualizar o código para uma nova versão:
Sempre que fizer novos commits ou merges na branch principal, basta executar:
```bash
cd /opt/lunaecare/LunaeCareBackendWhatsApp
bash scripts/deploy.sh
```
O script fará o `git pull`, rebuild das imagens, aplicará eventuais novas migrações com Alembic e reiniciará a stack com zero perda de dados.

### Restaurar um backup:
Para restaurar a base a partir de um backup anterior:
```bash
bash scripts/restore.sh backups/backup_lunaecare_whatsapp_YYYYMMDD_HHMMSS.sql.gz
```

---

## 6. Checklist de Segurança para Produção

| Verificação | Ação Realizada |
|---|---|
| **Portas Fechadas** | Apenas portas 22 (SSH), 80 e 443 (Nginx) abertas no UFW. A porta 8000 da API está restrita a `127.0.0.1`. |
| **Credenciais** | Senhas padrão `change_me` removidas. Validação por código aborta inicialização se valores inseguros forem informados. |
| **SSL/TLS** | Certificado SSL Let's Encrypt com TLS 1.2/1.3 e renovação automática via systemd certbot timer. |
| **Limitação de Taxa** | Proteção dupla: Nginx (40 req/s por IP com burst de 20) + FastAPI Redis Sliding Window (40 msgs/min por clínica). |
| **Log Rotation** | Docker configurado para limitar logs a 20MB por arquivo e máximo 5 arquivos, prevenindo esgotamento de disco. |
| **Backup & Retenção** | Backups diários comprimidos com rotação automática de 14 dias. |
