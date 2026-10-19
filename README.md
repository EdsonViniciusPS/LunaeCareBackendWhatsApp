# Lunae Care — Backend WhatsApp

Módulo de integração WhatsApp multiempresa para as clínicas do **Lunae Care**.

---

## 🚀 Status do Roadmap de Implementação

- [x] **Fase 1 — Fundação e Prova de Conceito:** FastAPI assíncrono, SQLAlchemy 2.0 (asyncpg), Alembic, Docker Compose, Redis, Worker e integração com Evolution API (modo mock e real).
- [x] **Fase 2 — Multiempresa e Segurança:** Autenticação via JWT Bearer com resolução estrita de `clinic_id`, criptografia AES-GCM de tokens de instância em repouso e chaves HMAC exclusivas por webhook.
- [x] **Fase 3 — Mensagens e Eventos:** Envio de mensagens com controle de idempotência (`X-Idempotency-Key`), filas Redis RQ, recebimento e deduplicação de webhooks (`MESSAGES_UPSERT`), recibos de entrega/leitura (`MESSAGES_UPDATE`) e histórico paginado.
- [x] **Fase 4 — Agenda Inteligente e Automações:** CRUD de regras de automação, receptor de eventos da agenda (`appointment.created`, `appointment.rescheduled`, `appointment.cancelled`), lembretes agendados (24h/configuráveis), cancelamento em cascata, detecção automática de opt-out/opt-in (LGPD) e botão de pausa centralizada.
- [x] **Fase 5 — Preparação para Produção:** Rate limiting por clínica (Sliding Window via Redis com fallback em memória), headers de segurança HTTP (Clickjacking/MIME sniffing), filtro de sanitização de logs (LGPD e mascaramento de tokens/QR codes), métricas operacionais agregadas (`/metrics` e `/metrics/system-health`), isolamento de redes no Docker e scripts de backup/restauração do PostgreSQL.

---

## 📁 Estrutura do Projeto

```text
LunaeCareBackendWhatsApp/
├── app/
│   ├── main.py                     # Inicialização da aplicação, CORS e security headers
│   ├── core/
│   │   ├── config.py               # Configurações Pydantic Settings (.env)
│   │   ├── crypto.py               # Criptografia AES-256-GCM para repouso
│   │   ├── database.py             # Conexão assíncrona SQLAlchemy (engine, sessions)
│   │   ├── logging_filter.py       # Filtro sanitizador de segredos e QR codes
│   │   ├── rate_limiter.py         # Rate limiter por clínica (anti-ban e proteção)
│   │   ├── security.py             # Tokens JWT, chaves HMAC e proteção de webhooks
│   │   └── tenancy.py              # Extração e validação do TenantContext (JWT)
│   ├── models/
│   │   ├── connection.py           # Entidade whatsapp_connections
│   │   └── entities.py             # Entidades: contatos, conversas, msgs, eventos, jobs, automações, preferências
│   ├── schemas/
│   │   ├── connection.py           # Schemas Pydantic de conexões
│   │   ├── conversation.py         # Schemas de conversas e contatos
│   │   ├── message.py              # Schemas de envio e histórico de mensagens
│   │   ├── automation.py           # Schemas de automações, agenda e opt-out
│   │   └── health.py               # Schema de health check
│   ├── providers/
│   │   ├── base.py                 # Contrato abstrato WhatsAppProvider
│   │   └── evolution.py            # Adaptador HTTP para Evolution API com modo mock
│   ├── repositories/
│   │   ├── connection_repository.py# Repositório de conexões com isolamento
│   │   ├── contact_repository.py   # Repositório de contatos por clínica
│   │   ├── conversation_repository.py # Repositório de conversas por clínica
│   │   ├── message_repository.py   # Repositório de mensagens com idempotência
│   │   ├── automation_repository.py# Repositório de regras com toggle_all
│   │   ├── job_repository.py       # Repositório de jobs agendados e cancelamento
│   │   ├── consent_repository.py   # Repositório de consentimento LGPD
│   │   └── webhook_event_repository.py # Deduplicação durável de eventos
│   ├── services/
│   │   ├── connection_service.py   # Ciclo de vida das conexões
│   │   ├── messaging_service.py    # Regras de envio, conversas e idempotência
│   │   ├── scheduling_service.py   # Orquestração da agenda e lembretes
│   │   ├── consent_service.py      # Detecção de opt-out/opt-in e LGPD
│   │   └── webhook_service.py      # Processamento de conexões, upsert e recibos
│   ├── api/
│   │   └── v1/
│   │       ├── connections.py      # /api/v1/whatsapp/connections
│   │       ├── conversations.py    # /api/v1/whatsapp/conversations
│   │       ├── messages.py         # /api/v1/whatsapp/messages
│   │       ├── automations.py      # /api/v1/whatsapp/automations
│   │       ├── metrics.py          # /api/v1/whatsapp/metrics e system-health
│   │       ├── webhooks.py         # /api/v1/whatsapp/webhooks/evolution/{key}
│   │       └── health.py           # /api/v1/health
│   └── workers/
│       ├── main.py                 # Runner do worker assíncrono (Redis/RQ)
│       ├── queue.py                # Despacho de jobs para fila
│       └── tasks.py                # Tarefas assíncronas de envio, recibos e lembretes
├── migrations/
│   ├── env.py                      # Configuração dinâmica de migrations assíncronas
│   └── versions/
│       ├── 001_initial_tables.py   # Tabelas iniciais do módulo
│       ├── 002_add_message_idempotency_key.py # Índice de idempotência para mensagens
│       └── 003_add_job_appointment_and_payload.py # Metadados e índices de jobs
├── scripts/
│   ├── backup.ps1                  # Script de backup do PostgreSQL
│   └── restore.ps1                 # Script de restauração do PostgreSQL
├── tests/
│   ├── conftest.py                 # Fixtures com SQLite em memória e mock provider
│   ├── helpers.py                  # Helpers para geração de tokens JWT nos testes
│   ├── test_connections.py        # Ciclo de vida das conexões
│   ├── test_health.py             # Health check e rota raiz
│   ├── test_messaging.py          # Envio, idempotência, isolamento, webhooks e recibos
│   ├── test_automations.py        # Regras, agenda inteligente, lembretes e opt-out
│   ├── test_production_readiness.py # Rate limiting, headers de segurança e observabilidade
│   ├── test_security_webhooks.py  # Criptografia, chaves HMAC e segurança de webhooks
│   └── test_tenancy_isolation.py  # Isolamento estrito entre clínicas
├── compose.yaml                    # Orquestração local segura (rede whatsapp-internal)
├── Dockerfile                      # Imagem de produção Python 3.11 slim
├── .env.example                    # Modelo de variáveis de ambiente
├── pyproject.toml                  # Configurações do projeto e pytest
└── requirements.txt                # Dependências fixadas
```

---

## 🛠️ Como Executar Localmente

### 1. Criar e ativar o ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

Copie o arquivo `.env.example` para `.env`:
```powershell
cp .env.example .env
```

### 3. Executar a suíte de testes automatizados (42 testes)

```powershell
pytest -v
```

### 4. Executar a aplicação com hot-reload

```powershell
uvicorn app.main:app --reload --port 8000
```
- Documentação interativa Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- Métricas operacionais: [http://localhost:8000/api/v1/whatsapp/metrics](http://localhost:8000/api/v1/whatsapp/metrics)
- Integridade dos subsistemas: [http://localhost:8000/api/v1/whatsapp/metrics/system-health](http://localhost:8000/api/v1/whatsapp/metrics/system-health)

---

## 🔒 Segurança, Privacidade e LGPD em Produção

1. **Isolamento Multi-tenant Estrito:** Derivado exclusivamente do claim `clinic_id` do JWT Bearer validado criptograficamente com HMAC-SHA256. Qualquer identificador informado externamente por headers ou query é ignorado.
2. **Criptografia em Repouso:** Tokens e credenciais das instâncias do WhatsApp são armazenados com criptografia autenticada AES-256-GCM. A chave de criptografia é mantida fora do banco de dados via variável de ambiente `ENCRYPTION_KEY`.
3. **Webhooks com HMAC Exclusivo:** Cada instância possui uma URL exclusiva com chave derivada via HMAC-SHA256 (`/webhooks/evolution/{provider_key}`). Tentativas com chaves inválidas retornam `403` de forma unificada para prevenir ataques de enumeração.
4. **Idempotência Garantida:**
   - Envio de mensagens suporta o cabeçalho `X-Idempotency-Key` ou parâmetro `idempotency_key`.
   - Webhooks recebidos são deduplicados através de chave única estável persistida em `whatsapp_webhook_events`.
5. **Rate Limiting Anti-Ban:** Controlador de taxa por janela deslizante (Sliding Window) limitando requisições e disparos de mensagens por clínica para evitar sobrecarga e banimento no WhatsApp.
6. **Sanitização de Logs:** O filtro `SensitiveDataSanitizerFilter` intercepta os logs da aplicação e mascara automaticamente dados sensíveis, tokens JWT, senhas e representações base64 de QR Codes.
7. **Rede Docker Privada:** No `compose.yaml`, portas internas da Evolution API, Redis e PostgreSQL não são publicadas publicamente para a Internet, permanecendo isoladas na rede bridge `whatsapp-internal`.

---

## 💾 Backup e Restauração do Banco de Dados

### Gerar Backup
```powershell
.\scripts\backup.ps1 -ContainerName "whatsapp-db" -Database "lunaecare_whatsapp"
```

### Restaurar Backup em Ambiente de Teste
```powershell
.\scripts\restore.ps1 -BackupFile "backups\backup_lunaecare_whatsapp_20261018_233000.sql.gz"
```
