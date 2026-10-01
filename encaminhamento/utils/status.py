"""
Traducao dos status do sistema.

O banco guarda os status em ingles (draft, pending, ...). Este modulo
concentra os rotulos em portugues e as funcoes para converter, para
que nenhuma tela mostre o valor cru.
"""
from typing import Optional

from encaminhamento.database.models import BatchStatus, StudentStatus

# Status de aluno
ALUNO = {
    "draft": "Rascunho",
    "pending": "Pendente",
    "sent": "Enviado",
    "confirmed": "Confirmado",
    "cancelled": "Cancelado",
}

# Status de lote
LOTE = {
    "draft": "Rascunho",
    "generated": "PDF gerado",
    "sent": "Enviado",
    "completed": "Concluído",
}

# Situacao da alocacao (campo allocation_status, em string)
ALOCACAO = {
    "pending": "Aguardando alocação",
    "allocated": "Alocado",
    "waitlist": "Em lista de espera",
}

# Ordem natural do fluxo
ORDEM_ALUNO = ["draft", "pending", "sent", "confirmed", "cancelled"]
ORDEM_LOTE = ["draft", "generated", "sent", "completed"]


def _valor(status) -> str:
    """Pega o valor do enum ou devolve a propria string."""
    if status is None:
        return ""
    return getattr(status, "value", status)


def rotulo_aluno(status) -> str:
    """Traduz o status de aluno para portugues."""
    return ALUNO.get(_valor(status), _valor(status))


def rotulo_lote(status) -> str:
    """Traduz o status de lote para portugues."""
    return LOTE.get(_valor(status), _valor(status))


def rotulo_alocacao(status) -> str:
    """Traduz a situacao da alocacao para portugues."""
    if not status:
        return "Aguardando alocação"
    return ALOCACAO.get(_valor(status), _valor(status))


def opcoes_aluno() -> list:
    """Opcoes de status de aluno em portugues, na ordem do fluxo."""
    return [ALUNO[k] for k in ORDEM_ALUNO]


def opcoes_lote() -> list:
    """Opcoes de status de lote em portugues, na ordem do fluxo."""
    return [LOTE[k] for k in ORDEM_LOTE]


def para_valor_aluno(rotulo: str) -> Optional[StudentStatus]:
    """Converte o rotulo em portugues de volta para o enum."""
    if not rotulo or rotulo == "Todos":
        return None
    for chave, texto in ALUNO.items():
        if texto == rotulo:
            return StudentStatus(chave)
    # Aceita o valor cru tambem, por seguranca
    try:
        return StudentStatus(rotulo)
    except ValueError:
        return None


def para_valor_lote(rotulo: str) -> Optional[BatchStatus]:
    """Converte o rotulo em portugues de volta para o enum."""
    if not rotulo or rotulo == "Todos":
        return None
    for chave, texto in LOTE.items():
        if texto == rotulo:
            return BatchStatus(chave)
    try:
        return BatchStatus(rotulo)
    except ValueError:
        return None
