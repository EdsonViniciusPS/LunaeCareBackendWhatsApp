"""
Módulo de regras de ciclo de vida e máquina de estados para mensagens WhatsApp.
Garante que transições de status sejam estritamente monotônicas, prevenindo
que webhooks atrasados ou fora de ordem revertam o estado da mensagem.
"""
from typing import Optional


# Hierarquia linear dos estados de entrega bem-sucedida de mensagens outbound
MESSAGE_STATUS_RANKS = {
    "queued": 10,
    "sent": 20,
    "delivered": 30,
    "read": 40,
}


def should_transition_message_status(current_status: Optional[str], new_status: str) -> bool:
    """
    Avalia se uma mensagem pode transicionar de `current_status` para `new_status`.

    Regras:
    1. Se current_status for None, qualquer status inicial é permitido.
    2. A sequência 'queued' -> 'sent' -> 'delivered' -> 'read' é estritamente crescente.
       Nunca é permitido regredir (ex: 'read' -> 'delivered' ou 'delivered' -> 'sent').
    3. 'failed' é um estado de erro:
       - Pode ser definido a partir de 'queued' ou 'sent'.
       - Não pode sobrescrever uma mensagem que já atingiu 'delivered' ou 'read'.
    4. Se o status já for 'failed', não permite retornar para 'queued' ou 'sent'.
    """
    if not current_status:
        return True

    curr = current_status.lower()
    target = new_status.lower()

    if curr == target:
        return True

    # Mensagens já lidas ou entregues nunca devem ser marcadas como 'failed' por webhooks atrasados
    if target == "failed" and curr in ("delivered", "read"):
        return False

    # Mensagens em falha não voltam para queued ou sent
    if curr == "failed" and target in ("queued", "sent"):
        return False

    curr_rank = MESSAGE_STATUS_RANKS.get(curr)
    target_rank = MESSAGE_STATUS_RANKS.get(target)

    # Se ambos os status estão na escala de rank linear (queued -> sent -> delivered -> read)
    if curr_rank is not None and target_rank is not None:
        return target_rank >= curr_rank

    return True
