# 🚀 Guia Rápido: Como Colocar no Ar na VPS Hostinger

Este guia é um passo a passo **direto ao ponto** ("receita de bolo") para você configurar e colocar o backend do WhatsApp no ar na sua VPS da Hostinger com Ubuntu.

---

## 📋 O que você precisa antes de começar

1. **IP da sua VPS Hostinger** (ex: `185.123.45.67`)
2. **Senha do usuário root da VPS** (ou sua chave SSH)
3. **Um subdomínio** para a API (ex: `api-whatsapp.seudominio.com.br`)

---

## Passo 1: Apontar seu Domínio na Hostinger (2 minutos)

1. Entre no painel da Hostinger (**hPanel**) $\rightarrow$ vá em **Domínios** $\rightarrow$ selecione seu domínio $\rightarrow$ **DNS / Servidores de Nomes**.
2. Adicione um novo registro:
   - **Tipo:** `A`
   - **Nome:** `api-whatsapp` *(ou o nome que preferir)*
   - **Aponta para:** O IP da sua VPS Hostinger *(ex: `185.123.45.67`)*
   - **TTL:** 300
3. Clique em **Adicionar Registro**.

> 💡 *Aguarde de 5 a 15 minutos para que o apontamento se espalhe na internet.*

---

## Passo 2: Entrar na sua VPS pelo Terminal (1 minuto)

Abra o terminal do seu computador (PowerShell, CMD ou terminal Linux/Mac) e digite:

```bash
ssh root@SEU_IP_AQUI
```
*(Digite sua senha da VPS quando solicitado).*

---

## Passo 3: Baixar o Projeto e Preparar o Servidor (3 minutos)

Cole estes comandos no terminal da VPS. Eles vão baixar o código e instalar tudo o que o servidor precisa de forma 100% automática (Docker, Nginx, Firewall, Memória Swap, etc.):

```bash
# 1. Cria a pasta e baixa o projeto
mkdir -p /opt/lunaecare
cd /opt/lunaecare
git clone https://github.com/EdsonViniciusPS/LunaeCareBackendWhatsApp.git
cd LunaeCareBackendWhatsApp

# 2. Executa a instalação automática de dependências
sudo bash scripts/setup_vps.sh
```

---

## Passo 4: Gerar as Senhas e Configurações (1 minuto)

Para você não ter que ficar inventando e copiando senhas na mão, criamos um gerador automático. Basta rodar:

```bash
bash scripts/generate_env.sh
```

O script vai te fazer duas perguntas rápidas:
1. **Segredo JWT:** se tiver o JWT do Lunae Care, cole-o. Se não tiver ainda, aperte **Enter** que ele gera uma chave forte para você.
2. **Domínio do Frontend:** confirme o domínio do seu frontend (ex: `https://app.lunaecare.com.br`) ou aperte **Enter**.

Pronto! Seu arquivo `.env` seguro está criado.

---

## Passo 5: Configurar o Domínio e Ativar o SSL HTTPS Grátis (2 minutos)

Substitua `api-whatsapp.seudominio.com.br` pelo seu subdomínio real nos comandos abaixo:

```bash
# 1. Copia o arquivo do Nginx
sudo cp nginx/lunaecare-whatsapp.conf /etc/nginx/sites-available/lunaecare-whatsapp.conf

# 2. Troca o domínio no arquivo (coloque o SEU subdomínio no lugar de api-whatsapp.seudominio.com.br)
sudo sed -i 's/api-whatsapp.seudominio.com.br/api-whatsapp.seudominio.com.br/g' /etc/nginx/sites-available/lunaecare-whatsapp.conf

# 3. Emite o certificado SSL gratuito Let's Encrypt
sudo certbot --nginx -d api-whatsapp.seudominio.com.br

# 4. Ativa o site no Nginx e recarrega
sudo ln -sf /etc/nginx/sites-available/lunaecare-whatsapp.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

---

## Passo 6: Ligar o Sistema (1 minuto)

Agora basta rodar o script de deploy:

```bash
bash scripts/deploy.sh
```

O script vai:
- Fazer o build dos containers
- Criar e atualizar as tabelas do PostgreSQL com Alembic automaticamente
- Ligar a Evolution API, Redis, Worker e API FastAPI
- Fazer um teste de saúde para confirmar que está tudo online

---

## Passo 7: Deixar Automático no Boot e com Backup Diário (1 minuto)

Para garantir que o sistema ligue sozinho caso a Hostinger reinicie a VPS e faça backups automáticos todo dia:

```bash
# 1. Iniciar automaticamente se a VPS reiniciar
sudo cp scripts/systemd/lunaecare-whatsapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lunaecare-whatsapp.service

# 2. Configura backup automático diário às 03:00 da manhã
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/lunaecare/LunaeCareBackendWhatsApp/scripts/backup.sh >> /var/log/lunae_backup.log 2>&1") | crontab -
```

---

## 🎉 Pronto! Como testar se deu certo?

Abra o seu navegador ou Postman e acesse:

1. **Teste Simples de Saúde:**
   `https://api-whatsapp.seudominio.com.br/api/v1/health`  
   👉 *Deve responder:* `{"status": "healthy"}`

2. **Teste dos Componentes (Banco + Redis + Evolution):**
   `https://api-whatsapp.seudominio.com.br/api/v1/whatsapp/metrics/system-health`  
   👉 *Deve responder com todos em "connected".*

---

## 🛠️ Comandos Úteis do Dia a Dia

Sempre que precisar, acesse a pasta do projeto (`cd /opt/lunaecare/LunaeCareBackendWhatsApp`):

| O que você quer fazer? | Comando para rodar no terminal |
|---|---|
| **Ver o que está acontecendo (logs ao vivo)** | `docker compose logs -f` |
| **Ver logs só da API** | `docker compose logs -f lunaecare-whatsapp` |
| **Ver logs dos disparos/lembretes** | `docker compose logs -f whatsapp-worker` |
| **Reiniciar todos os serviços** | `docker compose restart` |
| **Parar tudo** | `docker compose down` |
| **Ligar tudo** | `docker compose up -d` |
| **Atualizar o sistema (após alterações no GitHub)** | `bash scripts/deploy.sh` |
| **Fazer backup manual agora** | `bash scripts/backup.sh` |
| **Restaurar um backup** | `bash scripts/restore.sh backups/nome_do_arquivo.sql.gz` |
