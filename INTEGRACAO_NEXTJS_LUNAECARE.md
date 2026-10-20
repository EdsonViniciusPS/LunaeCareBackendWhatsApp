# 🔌 Guia de Integração: Lunae Care (Next.js) ↔ Backend WhatsApp

Este documento contém todas as instruções, tipos TypeScript, exemplos práticos de código e componentes prontos para integrar a plataforma **Lunae Care (Next.js)** com a API de mensageria WhatsApp em produção.

---

## 🌐 1. Dados da API em Produção

- **Base URL:** `https://api-whatsapp.lunaesolutions.com.br`
- **Protocolo:** HTTPS / REST / JSON
- **Healthcheck:** `GET https://api-whatsapp.lunaesolutions.com.br/api/v1/health`

---

## 🔑 2. Autenticação e Segurança Multi-tenant

O backend utiliza o modelo **Multi-tenant estrito**: toda requisição originada no frontend/backend do Lunae Care identifica a clínica exclusivamente através de um **Token JWT Bearer**.

### Estrutura Obrigatória do JWT:
```json
{
  "sub": "user_12345",
  "clinic_id": "clinica_bela_vista_01",
  "iss": "lunaecare",
  "aud": "lunaecare-whatsapp",
  "exp": 1799999999
}
```

> 🛡️ **Segurança:** O JWT **deve ser gerado no lado do servidor (Server Actions / Route Handlers do Next.js)** para que o `JWT_SECRET` nunca seja exposto no navegador do usuário.

---

## ⚙️ 3. Variáveis de Ambiente no Next.js (`.env.local` / `.env.production`)

Adicione no seu projeto Next.js do Lunae Care:

```env
# URL da API do WhatsApp
NEXT_PUBLIC_WHATSAPP_API_URL=https://api-whatsapp.lunaesolutions.com.br
WHATSAPP_API_URL=https://api-whatsapp.lunaesolutions.com.br

# Segredo JWT compartilhado (o mesmo configurado no backend WhatsApp)
WHATSAPP_JWT_SECRET=vinissd1998

# Chave secreta interna (para chamadas do sistema/agenda backend-to-backend)
WHATSAPP_INTERNAL_API_KEY=sua_chave_internal_api_key_aqui
```

---

## 📦 4. Utilitário de Geração de Token JWT (`lib/whatsapp-auth.ts`)

Instale a biblioteca padrão de JWT do ecossistema Next.js (compatível com Node.js e Edge Runtime):
```bash
npm install jose
```

Crie o arquivo `lib/whatsapp-auth.ts`:

```typescript
import { SignJWT } from "jose";

export async function generateWhatsAppToken(clinicId: string, userId: string = "system"): Promise<string> {
  const secret = new TextEncoder().encode(process.env.WHATSAPP_JWT_SECRET);

  return new SignJWT({
    sub: userId,
    clinic_id: clinicId,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuer("lunaecare")
    .setAudience("lunaecare-whatsapp")
    .setExpirationTime("2h")
    .sign(secret);
}
```

---

## 🛠️ 5. Cliente de Integração Completo (`lib/whatsapp-client.ts`)

Crie o arquivo `lib/whatsapp-client.ts` com todas as chamadas tipadas:

```typescript
import { generateWhatsAppToken } from "./whatsapp-auth";

const BASE_URL = process.env.WHATSAPP_API_URL || "https://api-whatsapp.lunaesolutions.com.br";

export interface WhatsAppConnection {
  id: string;
  clinic_id: string;
  provider: string;
  provider_instance_id: string;
  phone_number?: string;
  status: "pending" | "connecting" | "connected" | "disconnected";
  connected_at?: string;
  created_at: string;
}

export interface ConnectResponse {
  connection_id: string;
  status: string;
  qrcode?: string;       // Data URL: "data:image/png;base64,iVBOR..."
  pairing_code?: string; // Código de 8 dígitos para parear sem QR code
  message: string;
}

export interface SendMessagePayload {
  connectionId: string;
  recipient: string;     // Ex: "5511999998888" (somente números com DDI + DDD)
  content: string;
  idempotencyKey?: string;
}

export interface AgendaEventPayload {
  event: "appointment.created" | "appointment.rescheduled" | "appointment.cancelled";
  appointment_id: string;
  patient_id?: string;
  patient_name: string;
  phone_number: string;
  professional_name: string;
  appointment_datetime: string; // ISO 8601: "2026-10-25T14:30:00-03:00"
}

// -----------------------------------------------------------------------------
// 1. Conexões & Pareamento via QR Code
// -----------------------------------------------------------------------------

export async function createWhatsAppConnection(clinicId: string, phoneNumber?: string): Promise<WhatsAppConnection> {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/connections`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ phone_number: phoneNumber }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listWhatsAppConnections(clinicId: string): Promise<WhatsAppConnection[]> {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/connections`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getWhatsAppConnection(clinicId: string, connectionId: string): Promise<WhatsAppConnection> {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/connections/${connectionId}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function connectWhatsApp(clinicId: string, connectionId: string): Promise<ConnectResponse> {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/connections/${connectionId}/connect`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function disconnectWhatsApp(clinicId: string, connectionId: string): Promise<void> {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/connections/${connectionId}/disconnect`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
}

// -----------------------------------------------------------------------------
// 2. Envio de Mensagens Diretas
// -----------------------------------------------------------------------------

export async function sendWhatsAppMessage(clinicId: string, payload: SendMessagePayload) {
  const token = await generateWhatsAppToken(clinicId);
  const idempotencyKey = payload.idempotencyKey || crypto.randomUUID();

  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/messages/send`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      "X-Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({
      connection_id: payload.connectionId,
      recipient: payload.recipient,
      content: payload.content,
      type: "text",
      idempotency_key: idempotencyKey,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// -----------------------------------------------------------------------------
// 3. Agenda Inteligente & Disparos Automáticos
// -----------------------------------------------------------------------------

export async function triggerAgendaEvent(clinicId: string, event: AgendaEventPayload) {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/automations/agenda-events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(event),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// -----------------------------------------------------------------------------
// 4. Pausar ou Retomar Todas as Automações da Clínica (Botão de Emergência)
// -----------------------------------------------------------------------------

export async function toggleAllAutomations(clinicId: string, enabled: boolean) {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`${BASE_URL}/api/v1/whatsapp/automations/toggle-all`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

---

## 💻 6. Componente React: Conectar WhatsApp com QR Code

Crie o componente `components/WhatsAppConnectModal.tsx` para permitir que o administrador da clínica escaneie o QR Code na tela:

```tsx
"use client";

import React, { useState, useEffect } from "react";

interface Props {
  clinicId: string;
  connectionId: string;
  onConnected?: () => void;
}

export function WhatsAppConnectModal({ clinicId, connectionId, onConnected }: Props) {
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("Iniciando...");
  const [loading, setLoading] = useState(false);

  // Inicia o pareamento e obtém o QR Code
  async function handleStartConnect() {
    try {
      setLoading(true);
      setStatus("Gerando QR Code no WhatsApp...");
      
      // Chama a Route Handler interna do Next.js
      const res = await fetch(`/api/whatsapp/connect?connectionId=${connectionId}`);
      const data = await res.json();

      if (data.qrcode) {
        setQrCode(data.qrcode);
        setStatus("Aproxime a câmera do seu celular no WhatsApp > Dispositivos conectados");
      }
      if (data.pairing_code) {
        setPairingCode(data.pairing_code);
      }
    } catch (err) {
      setStatus("Erro ao iniciar conexão. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  // Verifica o status periodicamente até conectar
  useEffect(() => {
    if (!qrCode) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/whatsapp/status?connectionId=${connectionId}`);
        const data = await res.json();
        
        if (data.status === "connected") {
          setStatus("WhatsApp conectado com sucesso!");
          setQrCode(null);
          clearInterval(interval);
          if (onConnected) onConnected();
        }
      } catch (err) {
        // Ignora erros transitórios
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [qrCode, connectionId, onConnected]);

  return (
    <div className="p-6 bg-white rounded-xl shadow-lg border max-w-md mx-auto text-center">
      <h2 className="text-xl font-bold mb-2">Conectar WhatsApp da Clínica</h2>
      <p className="text-sm text-gray-500 mb-4">{status}</p>

      {qrCode ? (
        <div className="flex flex-col items-center gap-3">
          {/* O backend já entrega a string data URL pronta para a tag img */}
          <img
            src={qrCode}
            alt="QR Code WhatsApp"
            className="w-64 h-64 border p-2 rounded-lg shadow-sm"
          />
          {pairingCode && (
            <p className="text-sm font-semibold">
              Ou use o código: <span className="tracking-widest bg-gray-100 p-1 rounded font-mono">{pairingCode}</span>
            </p>
          )}
        </div>
      ) : (
        <button
          onClick={handleStartConnect}
          disabled={loading}
          className="px-6 py-2.5 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors"
        >
          {loading ? "Carregando..." : "Gerar QR Code"}
        </button>
      )}
    </div>
  );
}
```

---

## 📅 7. Disparo Automático ao Criar Consulta no Lunae Care

Sempre que uma consulta for agendada, reagendada ou cancelada no sistema de agendamento do Lunae Care, basta disparar o evento:

```typescript
// Exemplo em uma Server Action ou API Route de Agendamento (app/actions/appointments.ts)
import { triggerAgendaEvent } from "@/lib/whatsapp-client";

export async function createAppointmentAction(formData: AppointmentFormData) {
  // 1. Salva a consulta no banco de dados do Lunae Care
  const appointment = await db.appointments.create({ ... });

  // 2. Dispara a notificação e agendamento de lembrete no WhatsApp
  try {
    await triggerAgendaEvent(appointment.clinic_id, {
      event: "appointment.created",
      appointment_id: appointment.id,
      patient_id: appointment.patient_id,
      patient_name: appointment.patient_name,
      phone_number: appointment.patient_phone, // Ex: "5511999998888"
      professional_name: appointment.doctor_name,
      appointment_datetime: appointment.scheduled_at.toISOString(),
    });
  } catch (error) {
    console.error("Erro ao agendar lembretes no WhatsApp:", error);
    // Não interrompe o fluxo principal caso o WhatsApp oscile
  }

  return { success: true, appointment };
}
```

### O que o Backend do WhatsApp faz automaticamente com esse evento?
1. Normaliza o telefone do paciente e verifica se ele não solicitou opt-out (**LGPD**).
2. Agenda o lembrete de 24 horas antes na tabela `whatsapp_jobs`.
3. Se a consulta for daqui a menos de 24 horas, o worker dispara a confirmação imediatamente.
4. Se o evento for `appointment.cancelled`, ele **cancela em cascata** todos os lembretes futuros agendados para essa consulta.

---

## 🚫 8. Conformidade com a LGPD (Opt-out Automático)

Você não precisa programar regras de cancelamento no frontend. O backend possui detector semântico nativo integrado aos webhooks:

- Se o paciente responder **"PARAR"**, **"SAIR"**, **"NÃO QUERO MAIS"**:
  - O paciente é marcado como `opted_out`.
  - Todos os lembretes futuros agendados para o telefone dele são **cancelados instantaneamente**.
  - O sistema envia uma mensagem confirmando o descadastro e informando que para reativar basta enviar **"VOLTAR"**.
- Se responder **"VOLTAR"** ou **"REATIVAR"**:
  - O consentimento é restaurado como `opted_in`.

---

## 📊 9. Painel de Métricas e Status para a Clínica

Para exibir cards de status na Dashboard da Clínica:

```typescript
import { generateWhatsAppToken } from "@/lib/whatsapp-auth";

export async function getClinicWhatsAppMetrics(clinicId: string) {
  const token = await generateWhatsAppToken(clinicId);
  const res = await fetch(`https://api-whatsapp.lunaesolutions.com.br/api/v1/whatsapp/metrics`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return res.json();
}
```

Retorno:
```json
{
  "clinic_id": "clinica_01",
  "connections": {
    "total": 1,
    "by_status": { "connected": 1 }
  },
  "messages": {
    "total": 1450,
    "sent": 1400,
    "delivered": 1380,
    "read": 1250,
    "failed": 20
  },
  "opt_outs": 4
}
```

---

## ✅ Resumo de Rotas Disponíveis

| Método | Endpoint | Finalidade |
|---|---|---|
| `POST` | `/api/v1/whatsapp/connections` | Criar nova conexão |
| `GET` | `/api/v1/whatsapp/connections` | Listar conexões da clínica |
| `POST` | `/api/v1/whatsapp/connections/{id}/connect` | Gerar QR Code de pareamento |
| `POST` | `/api/v1/whatsapp/connections/{id}/disconnect` | Desconectar WhatsApp |
| `POST` | `/api/v1/whatsapp/messages/send` | Enviar mensagem direta com Idempotência |
| `GET` | `/api/v1/whatsapp/conversations` | Listar conversas da clínica |
| `GET` | `/api/v1/whatsapp/conversations/{id}/messages` | Histórico de mensagens |
| `POST` | `/api/v1/whatsapp/automations/agenda-events` | Disparo de eventos da agenda médica |
| `POST` | `/api/v1/whatsapp/automations/toggle-all` | Pausar/retomar todas as automações |
| `GET` | `/api/v1/whatsapp/metrics` | Métricas operacionais da clínica |
| `GET` | `/api/v1/health` | Healthcheck básico |
| `GET` | `/api/v1/whatsapp/metrics/system-health` | Saúde completa (Banco, Redis e Evolution) |
