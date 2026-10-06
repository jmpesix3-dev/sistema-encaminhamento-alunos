"""
Consultas do painel de controle.

Centraliza os numeros do sistema e a lista de pendencias, para que o
painel e o aviso do menu lateral leiam sempre a mesma fonte.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from sqlalchemy import func, select

from encaminhamento.database import get_session
from encaminhamento.database.models import (
    ForwardingBatch, School, Student, StudentStatus, BatchStatus,
)

ROTULO_STATUS_ALUNO = {
    "draft": "Rascunho",
    "pending": "Pendente",
    "sent": "Enviado",
    "confirmed": "Confirmado",
    "cancelled": "Cancelado",
}

ROTULO_STATUS_LOTE = {
    "draft": "Rascunho",
    "generated": "PDF gerado",
    "sent": "Enviado",
    "completed": "Concluido",
}

# Ordem natural do fluxo
ORDEM_ALUNO = ["draft", "pending", "sent", "confirmed", "cancelled"]
ORDEM_LOTE = ["draft", "generated", "sent", "completed"]

# Cor de cada etapa, usada no painel
COR_STATUS = {
    "draft": "#9aa5b1",       # cinza: ainda nao comecou
    "pending": "#f0a30a",     # ambar: esperando
    "generated": "#2f7ed8",   # azul: PDF pronto
    "sent": "#7c5cd6",        # roxo: em transito
    "confirmed": "#1f9d55",   # verde: resolvido
    "completed": "#1f9d55",   # verde: resolvido
    "cancelled": "#d64545",   # vermelho: cancelado
}

# Situacoes do painel de controle: contagem rapida de alunos por
# categoria, cada uma clicavel para ir ate a lista correspondente.
# Lista de tuplas (chave, rotulo, cor) para iterar no painel e testes.
SITUACAO_ALUNO = [
    ("alunos", "Alunos", COR_STATUS.get("sent", "#7c5cd6")),
    ("encaminhados", "Encaminhados", "#1f9d55"),
    ("pendente", "Pendente", "#f0a30a"),
    ("info_pendente", "Informação Pendente", "#d64545"),
]

COR_SITUACAO = {chave: cor for chave, _, cor in SITUACAO_ALUNO}


@dataclass
class Pendencia:
    """Uma pendencia do sistema, com a acao que resolve.

    `estado` usa os nomes de chave SEM o prefixo `ir_`, que e added
    automaticamente por `ir_para()` ao navegar.
    """
    chave: str
    titulo: str
    quantidade: int
    descricao: str
    pagina: str
    estado: dict = field(default_factory=dict)
    criticidade: int = 2  # 1 = trava o processo, 2 = atrapalha, 3 = informativa

    def tem_acao(self) -> bool:
        return bool(self.pagina)


@dataclass
class Resumo:
    """Numeros gerais do sistema."""
    escolas: int = 0
    alunos: int = 0
    alocados: int = 0
    sem_vaga: int = 0
    lotes: int = 0
    por_status_aluno: dict = field(default_factory=dict)
    por_status_lote: dict = field(default_factory=dict)
    relacao_escolas: List[dict] = field(default_factory=list)
    pendencias: List[Pendencia] = field(default_factory=list)

    @property
    def total_pendencias(self) -> int:
        return sum(p.quantidade for p in self.pendencias)


def _demanda(session, destino_id: int) -> int:
    """Quantos alunos apontaram esta escola como destino (1a ou 2a opcao)."""
    total = session.execute(
        select(func.count(Student.id)).where(Student.destination_school_1_id == destino_id)
    ).scalar() or 0
    total += session.execute(
        select(func.count(Student.id)).where(Student.destination_school_2_id == destino_id)
    ).scalar() or 0
    return total


def montar_resumo() -> Resumo:
    """Reune indicadores, relacao de escolas e pendencias."""
    resumo = Resumo()

    with get_session() as session:
        resumo.escolas = session.execute(select(func.count(School.id))).scalar() or 0
        resumo.alunos = session.execute(select(func.count(Student.id))).scalar() or 0
        resumo.alocados = session.execute(
            select(func.count(Student.id))
            .where(Student.allocated_school_id.isnot(None))
        ).scalar() or 0
        resumo.lotes = session.execute(
            select(func.count(ForwardingBatch.id))
        ).scalar() or 0

        for status in ORDEM_ALUNO:
            resumo.por_status_aluno[status] = session.execute(
                select(func.count(Student.id)).where(Student.status == StudentStatus(status))
            ).scalar() or 0

        for status in ORDEM_LOTE:
            resumo.por_status_lote[status] = session.execute(
                select(func.count(ForwardingBatch.id))
                .where(ForwardingBatch.status == BatchStatus(status))
            ).scalar() or 0

        alocados_por_escola = dict(session.execute(
            select(Student.allocated_school_id, func.count(Student.id))
            .where(Student.allocated_school_id.isnot(None))
            .group_by(Student.allocated_school_id)
        ).all())

        origem_por_escola = dict(session.execute(
            select(Student.origin_school_id, func.count(Student.id))
            .where(Student.origin_school_id.isnot(None))
            .group_by(Student.origin_school_id)
        ).all())

        escolas = session.execute(
            select(School).order_by(School.name)
        ).scalars().all()

        relacao = []
        for e in escolas:
            procura = _demanda(session, e.id)
            vinculados = alocados_por_escola.get(e.id, 0)
            capacidade = e.oferta or 0
            relacao.append({
                "id": e.id,
                "escola": e.name,
                "modalidade": e.modalidade or "",
                "distrito": e.distrito or "",
                "endereco": e.address or "",
                "alunos_origem": origem_por_escola.get(e.id, 0),
                "alunos_procura": procura,
                "alocados": vinculados,
                "capacidade": capacidade,
                "vagas_livres": capacidade - vinculados,
                "ocupacao": (vinculados / capacidade) if capacidade else None,
                "geolocalizada": e.latitude is not None,
                "telefone": e.phone or "",
                "email": e.email or "",
            })

        resumo.relacao_escolas = relacao

        # ---------------- pendencias ----------------
        pendencias = []

        # 1) Escolas sem capacidade
        sem_capacidade = [e for e in relacao if e["capacidade"] == 0]
        if sem_capacidade:
            pendencias.append(Pendencia(
                chave="escolas_sem_capacidade",
                titulo="Escolas sem capacidade definida",
                quantidade=len(sem_capacidade),
                descricao="A alocacao nao roda sem saber quantos alunos cada escola comporta.",
                pagina="Escolas",
                estado={"capacidade": True},
                criticidade=1,
            ))

        # 2) Escolas sem geolocalizacao
        sem_geo = [e for e in relacao if not e["geolocalizada"]]
        if sem_geo:
            pendencias.append(Pendencia(
                chave="escolas_sem_geo",
                titulo="Escolas sem geolocalizacao",
                quantidade=len(sem_geo),
                descricao="Sem coordenadas a escola nao pode receber alunos por proximidade.",
                pagina="Escolas",
                estado={"localizacao": True},
                criticidade=1,
            ))

        # 3) Alunos sem coordenada
        sem_coord = session.execute(
            select(func.count(Student.id)).where(Student.latitude.is_(None))
        ).scalar() or 0
        if sem_coord:
            pendencias.append(Pendencia(
                chave="alunos_sem_coordenada",
                titulo="Alunos sem geolocalizar",
                quantidade=sem_coord,
                descricao="Sem coordenada o aluno nao entra na ordenacao por proximidade.",
                pagina="Auto_Allocation",
                estado={"alocacao": "coordenadas"},
                criticidade=2,
            ))

        # 4) Alunos sem vaga
        sem_vaga = resumo.alunos - resumo.alocados
        resumo.sem_vaga = sem_vaga
        if sem_vaga:
            pendencias.append(Pendencia(
                chave="alunos_sem_vaga",
                titulo="Alunos sem vaga",
                quantidade=sem_vaga,
                descricao="Nao entraram em nenhuma escola. Increase a capacidade ou revise as opcoes.",
                pagina="Alunos",
                estado={"aluno_status": "sem_vaga"},
                criticidade=2,
            ))

        # 5) Alunos sem 2a opcao
        sem_segunda = session.execute(
            select(func.count(Student.id))
            .where(Student.destination_school_2_id.is_(None))
        ).scalar() or 0
        if sem_segunda:
            pendencias.append(Pendencia(
                chave="alunos_sem_segunda",
                titulo="Alunos sem 2a opcao",
                quantidade=sem_segunda,
                descricao="Se a 1a escolha lotar, nao tem para onde ser_realocado.",
                pagina="Alunos",
                estado={"aluno_status": "sem_segunda"},
                criticidade=3,
            ))

        # 6) Lotes sem PDF
        lotes_sem_pdf = session.execute(
            select(func.count(ForwardingBatch.id))
            .where(ForwardingBatch.pdf_path.is_(None))
        ).scalar() or 0
        if lotes_sem_pdf:
            pendencias.append(Pendencia(
                chave="lotes_sem_pdf",
                titulo="Lotes sem PDF",
                quantidade=lotes_sem_pdf,
                descricao="O encaminhamento so pode ser enviado depois de gerar o PDF.",
                pagina="Batch_Management",
                estado={"lote_status": "sem_pdf"},
                criticidade=2,
            ))

        # 7) Lotes nao enviados
        lotes_nao_enviados = session.execute(
            select(func.count(ForwardingBatch.id))
            .where(
                ForwardingBatch.status == BatchStatus.GENERATED,
                ForwardingBatch.sent_at.is_(None),
            )
        ).scalar() or 0
        if lotes_nao_enviados:
            pendencias.append(Pendencia(
                chave="lotes_nao_enviados",
                titulo="Lotes nao enviados",
                quantidade=lotes_nao_enviados,
                descricao="PDF pronto, mas a escola de destino ainda nao recebeu.",
                pagina="Automation",
                estado={"email": True},
                criticidade=2,
            ))

        # 8) Escolas sobrecarregadas
        sobrecarregadas = [
            e for e in relacao
            if e["capacidade"] > 0 and e["alunos_procura"] > e["capacidade"]
        ]
        if sobrecarregadas:
            pendencias.append(Pendencia(
                chave="escolas_sobrecarregadas",
                titulo="Escolas com demanda acima da capacidade",
                quantidade=len(sobrecarregadas),
                descricao="Mais alunos apontam para elas do que cabem. Parte ficara sem vaga.",
                pagina="Auto_Allocation",
                estado={"alocacao": "previa"},
                criticidade=2,
            ))

        # 9) Escolas com vagas ociosas
        ociosas = [
            e for e in relacao
            if e["capacidade"] > 0 and e["alocados"] == 0 and e["alunos_procura"] > 0
        ]
        if ociosas:
            pendencias.append(Pendencia(
                chave="escolas_ociosas",
                titulo="Escolas com vagas e sem alunacao",
                quantidade=len(ociosas),
                descricao="Tem procura e capacidade, mas nenhum aluno foi alocado.",
                pagina="Auto_Allocation",
                estado={"alocacao": "previa"},
                criticidade=3,
            ))

    # 10) Versao nova no GitHub
    nova_versao = _pendencia_atualizacao()
    if nova_versao:
        pendencias.append(nova_versao)

    resumo.pendencias = sorted(pendencias, key=lambda p: (p.criticidade, -p.quantidade))
    return resumo


# ======================================================================
# Situacao de alunos — 4 cards do painel
# ======================================================================
# Ficam fora de montar_resumo() de proposito: sao chamados sob demanda
# pelo painel e servem tambem para navegar ate a pagina de Alunos.

def contar_situacao_aluno() -> dict:
    """
    Contagens rapidas para os 4 cards do painel:

    - alunos:        total de alunos cadastrados
    - encaminhados:  alunos com escola alocada (allocated_school_id IS NOT NULL)
    - pendente:      alunos sem alocacao (total - encaminhados)
    - info_pendente: alunos com endereco ou 1a escola de destino faltando
    """
    with get_session() as session:
        total = session.execute(select(func.count(Student.id))).scalar() or 0
        encaminhados = session.execute(
            select(func.count(Student.id))
            .where(Student.allocated_school_id.isnot(None))
        ).scalar() or 0

        info_pendente = session.execute(
            select(func.count(Student.id)).where(
                (Student.address.is_(None))
                | (Student.address == "")
                | (Student.destination_school_1_id.is_(None))
            )
        ).scalar() or 0

        return {
            "alunos": total,
            "encaminhados": encaminhados,
            "pendente": total - encaminhados,
            "info_pendente": info_pendente,
        }


def detalhar_situacao_aluno(situacao: str) -> List[dict]:
    """
    Lista de alunos de uma situacao para exibicao detalhada.

    `situacao` usa as chaves de SITUACAO_ALUNO.
    Devolve lista de dicionarios prontos para dataframe.
    """
    with get_session() as session:
        if situacao == "alunos":
            alunos = session.execute(
                select(Student).order_by(Student.name)
            ).scalars().all()
        elif situacao == "encaminhados":
            alunos = session.execute(
                select(Student)
                .where(Student.allocated_school_id.isnot(None))
                .order_by(Student.name)
            ).scalars().all()
        elif situacao == "pendente":
            alunos = session.execute(
                select(Student)
                .where(Student.allocated_school_id.is_(None))
                .order_by(Student.name)
            ).scalars().all()
        elif situacao == "info_pendente":
            alunos = session.execute(
                select(Student)
                .where(
                    (Student.address.is_(None))
                    | (Student.address == "")
                    | (Student.destination_school_1_id.is_(None))
                )
                .order_by(Student.name)
            ).scalars().all()
        else:
            return []

        linhas = []
        for a in alunos:
            linhas.append({
                "Aluno": a.name,
                "Origem": a.origin_school.name if a.origin_school else "",
                "1ª opção": a.destination_school_1.name if a.destination_school_1 else "",
                "Endereço": (a.address or "")[:50],
                "Alocado em": a.allocated_school.name if a.allocated_school else "",
                "Status": ROTULO_STATUS_ALUNO.get(a.status.value, a.status.value),
            })
        return linhas


def _pendencia_atualizacao():
    """
    Versao nova disponivel no GitHub.

    Le apenas o cache: a consulta de rede acontece uma vez por sessao,
    em app.py. Assim o painel nunca fica lento ao abrir.
    """
    from encaminhamento.services import atualizacao

    if not atualizacao.ha_atualizacao():
        return None

    dados = atualizacao.estado()
    commit = (dados.get("commit_remoto") or "")[:7]
    mensagem = dados.get("mensagem", "")
    data = dados.get("data_commit", "")

    quando = ""
    if data:
        try:
            quando = datetime.fromisoformat(
                data.replace("Z", "+00:00")
            ).strftime("%d/%m/%Y")
        except ValueError:
            quando = ""

    descricao = mensagem or "Ha uma versao nova disponivel."
    if quando:
        descricao += f"  ({quando})"

    return Pendencia(
        chave="atualizacao",
        titulo="Nova versão disponível",
        quantidade=1,
        descricao=f"{descricao}  —  versão {commit}",
        pagina="Atualizar",
        estado={"atualizar": commit},
        # criticidade 0: fica acima de tudo, para o botao aparecer
        criticidade=0,
    )


# ======================================================================
# Detalhe das pendencias
# ======================================================================
# Ficam fora de montar_resumo() de proposito: o menu lateral conta as
# pendencias em toda pagina, e estas consultas so interessam quando o
# cartao e aberto no painel.

MOTIVOS_SEM_VAGA = {
    "nao_rodou": "Alocação ainda não foi executada",
    "sem_coordenada": "Sem coordenada — não ordenável por distância",
    "sem_destino": "Nenhum destino informado",
    "sem_capacidade": "Escola de destino sem capacidade definida",
    "primeira_lotada": "1ª opção lotada, sem 2ª opção",
    "ambas_lotadas": "1ª e 2ª opções lotadas",
    "capacidade": "Não coube na capacidade",
}


def _alunos_sem_vaga(session):
    """
    Lista os alunos sem escola definida, com o motivo de cada um.

    A ordem das verificacoes importa: quando a alocacao nunca rodou,
    dizer que a escola lotou seria mentira.
    """
    # Existe algum aluno alocado? Se nao, a alocacao nunca rodou.
    algum_alocado = session.execute(
        select(func.count(Student.id))
        .where(Student.allocation_status == "allocated")
    ).scalar() or 0

    # Alunos apontados por escola de destino
    demanda = {}
    for destino_id in session.execute(
        select(Student.destination_school_1_id)
        .where(Student.destination_school_1_id.isnot(None))
        .union(
            select(Student.destination_school_2_id)
            .where(Student.destination_school_2_id.isnot(None))
        )
    ).scalars().all():
        primeira = session.execute(
            select(func.count(Student.id)).where(
                Student.destination_school_1_id == destino_id)
        ).scalar() or 0
        segunda = session.execute(
            select(func.count(Student.id)).where(
                Student.destination_school_2_id == destino_id)
        ).scalar() or 0
        demanda[destino_id] = primeira + segunda

    def sem_capacidade(escola_id):
        if not escola_id:
            return False
        escola = session.get(School, escola_id)
        return bool(escola) and not escola.oferta

    def lotada(escola_id):
        if not escola_id:
            return False
        escola = session.get(School, escola_id)
        if not escola or not escola.oferta:
            return False
        return demanda.get(escola_id, 0) >= escola.oferta

    linhas = []
    alunos = session.execute(
        select(Student).where(Student.allocated_school_id.is_(None))
    ).scalars().all()

    for a in alunos:
        if not algum_alocado:
            motivo = MOTIVOS_SEM_VAGA["nao_rodou"]
        elif a.latitude is None:
            motivo = MOTIVOS_SEM_VAGA["sem_coordenada"]
        elif not a.destination_school_1_id:
            motivo = MOTIVOS_SEM_VAGA["sem_destino"]
        elif not a.destination_school_2_id:
            if sem_capacidade(a.destination_school_1_id):
                motivo = MOTIVOS_SEM_VAGA["sem_capacidade"]
            elif lotada(a.destination_school_1_id):
                motivo = MOTIVOS_SEM_VAGA["primeira_lotada"]
            else:
                motivo = MOTIVOS_SEM_VAGA["capacidade"]
        else:
            s1 = sem_capacidade(a.destination_school_1_id)
            s2 = sem_capacidade(a.destination_school_2_id)
            if s1 and s2:
                motivo = "Nenhuma das opções tem capacidade definida"
            elif s1:
                motivo = "1ª opção sem capacidade definida"
            elif s2:
                motivo = "2ª opção sem capacidade definida"
            elif lotada(a.destination_school_1_id) and lotada(a.destination_school_2_id):
                motivo = MOTIVOS_SEM_VAGA["ambas_lotadas"]
            else:
                motivo = MOTIVOS_SEM_VAGA["capacidade"]

        linhas.append({
            "Aluno": a.name,
            "Origem": a.origin_school.name if a.origin_school else "",
            "1ª opção": a.destination_school_1.name if a.destination_school_1 else "",
            "2ª opção": a.destination_school_2.name if a.destination_school_2 else "",
            "Motivo": motivo,
        })

    return linhas


def detalhar_pendencia(chave: str) -> List[dict]:
    """
    Linhas de detalhe de uma pendencia, prontas para exibicao.

    Devolve lista de dicionarios, um por item afetado.
    """
    with get_session() as session:
        if chave == "escolas_sem_capacidade":
            linhas = []
            for e in session.execute(
                select(School).where(School.oferta == 0).order_by(School.name)
            ).scalars().all():
                procura = session.execute(
                    select(func.count(Student.id)).where(
                        (Student.destination_school_1_id == e.id)
                        | (Student.destination_school_2_id == e.id)
                    )
                ).scalar() or 0
                linhas.append({
                    "Escola": e.name,
                    "Distrito": e.distrito or "",
                    "Alunos apontam": procura,
                })
            return linhas

        if chave == "escolas_sem_geo":
            linhas = []
            for e in session.execute(
                select(School).where(School.latitude.is_(None)).order_by(School.name)
            ).scalars().all():
                linhas.append({
                    "Escola": e.name,
                    "Distrito": e.distrito or "",
                    "Endereço": (e.address or "")[:50],
                })
            return linhas

        if chave == "alunos_sem_coordenada":
            linhas = []
            for a in session.execute(
                select(Student).where(Student.latitude.is_(None)).order_by(Student.name)
            ).scalars().all():
                linhas.append({
                    "Aluno": a.name,
                    "Origem": a.origin_school.name if a.origin_school else "",
                    "Endereço": (a.address or "")[:45],
                })
            return linhas

        if chave == "alunos_sem_vaga":
            return _alunos_sem_vaga(session)

        if chave == "alunos_sem_segunda":
            linhas = []
            for a in session.execute(
                select(Student).where(Student.destination_school_2_id.is_(None))
                .order_by(Student.name)
            ).scalars().all():
                linhas.append({
                    "Aluno": a.name,
                    "Origem": a.origin_school.name if a.origin_school else "",
                    "1ª opção": (a.destination_school_1.name
                                 if a.destination_school_1 else ""),
                })
            return linhas

        if chave == "lotes_sem_pdf":
            linhas = []
            for b in session.execute(
                select(ForwardingBatch).where(ForwardingBatch.pdf_path.is_(None))
                .order_by(ForwardingBatch.created_at.desc())
            ).scalars().all():
                linhas.append({
                    "Lote": f"#{b.id}",
                    "Destino": b.destination_school.name if b.destination_school else "",
                    "Alunos": b.student_count,
                })
            return linhas

        if chave == "lotes_nao_enviados":
            linhas = []
            for b in session.execute(
                select(ForwardingBatch)
                .where(
                    ForwardingBatch.status == BatchStatus.GENERATED,
                    ForwardingBatch.sent_at.is_(None),
                )
                .order_by(ForwardingBatch.created_at.desc())
            ).scalars().all():
                linhas.append({
                    "Lote": f"#{b.id}",
                    "Destino": b.destination_school.name if b.destination_school else "",
                    "Alunos": b.student_count,
                    "PDF gerado": b.updated_at.strftime("%d/%m/%Y") if b.updated_at else "",
                })
            return linhas

        if chave == "escolas_sobrecarregadas":
            linhas = []
            for e in session.execute(
                select(School).where(School.oferta > 0).order_by(School.name)
            ).scalars().all():
                procura = session.execute(
                    select(func.count(Student.id)).where(
                        (Student.destination_school_1_id == e.id)
                        | (Student.destination_school_2_id == e.id)
                    )
                ).scalar() or 0
                if procura > e.oferta:
                    linhas.append({
                        "Escola": e.name,
                        "Procura": procura,
                        "Capacidade": e.oferta,
                        "Excesso": procura - e.oferta,
                    })
            return linhas

        if chave == "escolas_ociosas":
            linhas = []
            for e in session.execute(
                select(School).where(School.oferta > 0).order_by(School.name)
            ).scalars().all():
                procura = session.execute(
                    select(func.count(Student.id)).where(
                        (Student.destination_school_1_id == e.id)
                        | (Student.destination_school_2_id == e.id)
                    )
                ).scalar() or 0
                alocados = session.execute(
                    select(func.count(Student.id)).where(
                        Student.allocated_school_id == e.id)
                ).scalar() or 0
                if procura > 0 and alocados == 0:
                    linhas.append({
                        "Escola": e.name,
                        "Procura": procura,
                        "Capacidade": e.oferta,
                    })
            return linhas

    return []


def detalhar_alunos_por_escola(somente_com_alunos: bool = True) -> List[dict]:
    """
    Alunos por escola de origem, quebrados por etapa.

    Uma linha por escola, com o total, quantos estao em cada etapa,
    quantos ja foram alocados e a capacidade da escola.

    Fica fora de montar_resumo() de proposito: o menu lateral conta as
    pendencias em toda pagina e nao deve pagar por esta consulta.
    """
    with get_session() as session:
        # Uma linha por (escola de origem, status)
        consulta = (
            select(
                School.id,
                School.name,
                School.distrito,
                School.oferta,
                Student.status,
                func.count(Student.id).label("quantidade"),
            )
            .join(Student, Student.origin_school_id == School.id)
            .group_by(School.id, Student.status)
        )
        if somente_com_alunos:
            consulta = consulta.having(func.count(Student.id) > 0)

        contagens = session.execute(consulta).all()

        # Alocados e lotes por escola de destino
        alocados_por_escola = dict(session.execute(
            select(Student.allocated_school_id, func.count(Student.id))
            .where(Student.allocated_school_id.isnot(None))
            .group_by(Student.allocated_school_id)
        ).all())

    # Monta uma linha por escola, juntando as etapas
    por_escola = {}
    for escola_id, nome, distrito, oferta, status, quantidade in contagens:
        linha = por_escola.setdefault(escola_id, {
            "id": escola_id,
            "escola": nome,
            "distrito": distrito or "",
            "capacidade": oferta or 0,
            "total": 0,
            "draft": 0,
            "pending": 0,
            "sent": 0,
            "confirmed": 0,
            "cancelled": 0,
        })
        chave = getattr(status, "value", status)
        linha[chave] = quantidade
        linha["total"] += quantidade

    linhas = []
    for linha in por_escola.values():
        alocados = alocados_por_escola.get(linha["id"], 0)
        capacidade = linha["capacidade"]
        linhas.append({
            "id": linha["id"],
            "Escola": linha["escola"],
            "Distrito": linha["distrito"],
            "Alunos": linha["total"],
            "Rascunho": linha["draft"],
            "Pendente": linha["pending"],
            "Enviado": linha["sent"],
            "Confirmado": linha["confirmed"],
            "Alocados": alocados,
            "Capacidade": capacidade,
            "Vagas livres": capacidade - alocados,
            "Ocupacao": (f"{alocados / capacidade * 100:.0f}%" if capacidade else "-"),
        })

    # Quem mais tem alunos primeiro
    linhas.sort(key=lambda r: (-r["Alunos"], r["Escola"]))
    return linhas


def exportar_resumo(resumo: Resumo, caminho: str) -> str:
    """Gera um .xlsx com indicadores, pendencias e relacao de escolas."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()

    cabecalho = Font(bold=True, size=11, color="FFFFFF")
    preenchimento = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    titulo = Font(bold=True, size=13)
    numero = "#,##0"

    # ---- Indicadores ----
    ws = wb.active
    ws.title = "Indicadores"
    ws["A1"] = "Resumo do encaminhamento de alunos"
    ws["A1"].font = titulo

    linhas = [
        ("Escolas cadastradas", resumo.escolas),
        ("Alunos cadastrados", resumo.alunos),
        ("Alunos alocados", resumo.alocados),
        ("Alunos sem vaga", resumo.sem_vaga),
        ("Lotes criados", resumo.lotes),
        ("", ""),
        ("Situacao dos alunos", ""),
    ]
    for chave, valor in resumo.por_status_aluno.items():
        if valor:
            linhas.append((f"  {ROTULO_STATUS_ALUNO[chave]}", valor))
    linhas.append(("", ""))
    linhas.append(("Situacao dos lotes", ""))
    for chave, valor in resumo.por_status_lote.items():
        if valor:
            linhas.append((f"  {ROTULO_STATUS_LOTE[chave]}", valor))

    for i, (rotulo, valor) in enumerate(linhas, 3):
        ws.cell(row=i, column=1, value=rotulo)
        if isinstance(valor, int):
            ws.cell(row=i, column=2, value=valor).number_format = numero

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 12

    # ---- Pendencias ----
    ws = wb.create_sheet("Pendencias")
    cabecalhos = ["Pendencia", "Quantidade", "Como resolver"]
    for col, texto in enumerate(cabecalhos, 1):
        c = ws.cell(row=1, column=col, value=texto)
        c.font = cabecalho
        c.fill = preenchimento

    if resumo.pendencias:
        for i, p in enumerate(resumo.pendencias, 2):
            ws.cell(row=i, column=1, value=p.titulo)
            ws.cell(row=i, column=2, value=p.quantidade)
            ws.cell(row=i, column=3, value=p.descricao)
    else:
        ws.cell(row=2, column=1, value="Nenhuma pendencia")

    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 62

    # ---- Escolas ----
    ws = wb.create_sheet("Escolas")
    cabecalhos = [
        "Escola", "Distrito", "Modalidade", "Endereco", "Telefone", "E-mail",
        "Alunos (origem)", "Alunos (procura)", "Alocados", "Capacidade",
        "Vagas livres", "Ocupacao", "Geolocalizada",
    ]
    for col, texto in enumerate(cabecalhos, 1):
        c = ws.cell(row=1, column=col, value=texto)
        c.font = cabecalho
        c.fill = preenchimento

    for i, e in enumerate(resumo.relacao_escolas, 2):
        ws.cell(row=i, column=1, value=e["escola"])
        ws.cell(row=i, column=2, value=e["distrito"])
        ws.cell(row=i, column=3, value=e["modalidade"])
        ws.cell(row=i, column=4, value=e["endereco"])
        ws.cell(row=i, column=5, value=e["telefone"])
        ws.cell(row=i, column=6, value=e["email"])
        for col, chave in ((7, "alunos_origem"), (8, "alunos_procura"),
                           (9, "alocados"), (10, "capacidade"), (11, "vagas_livres")):
            ws.cell(row=i, column=col, value=e[chave]).number_format = numero
        ws.cell(row=i, column=12,
                value=f"{e['ocupacao'] * 100:.0f}%" if e["ocupacao"] is not None else "-")
        ws.cell(row=i, column=13, value="Sim" if e["geolocalizada"] else "Nao")

    larguras = [38, 12, 26, 40, 15, 28, 14, 15, 11, 12, 12, 11, 13]
    for col, largura in enumerate(larguras, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = largura

    wb.save(caminho)
    return caminho
