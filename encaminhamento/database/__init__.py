from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
from encaminhamento.config import DATABASE_URL, DATABASE_ECHO
from encaminhamento.database.models import Base

engine = create_engine(
    DATABASE_URL,
    echo=DATABASE_ECHO,
    future=True,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

# expire_on_commit=False mantem os atributos carregados apos o commit.
# Sem isso, qualquer objeto usado fora do with get_session() dispara
# DetachedInstanceError (o commit expira todos os atributos).
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    # Enable WAL mode for SQLite: see committed writes across connections
    # (critical when the DB is modified by an external script and the
    # Streamlit server needs to see the changes immediately).
    if DATABASE_URL.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, conn_record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA busy_timeout=5000")
    Base.metadata.create_all(bind=engine)

    # Sincroniza status de aluno com a alocacao existente: alunos alocados
    # presos como Rascunho passam a Pendente; sem alocacao como Pendente
    # voltam a Rascunho. Idempotente e seguro em banco vazio.
    from encaminhamento.database.crud import sync_status_aluno_por_alocacao

    with get_session() as session:
        sync_status_aluno_por_alocacao(session)

    # Auto-seed de escolas na primeira inicializacao.
    # So roda quando a tabela schools está vazia; preserva edições manuais.
    _seed_escolas_se_banco_vazio()


def _seed_escolas_se_banco_vazio() -> None:
    """Carrega escolas de data/escolas.xlsx quando o banco está vazio."""
    from encaminhamento.database.crud import list_schools
    from encaminhamento.config import DATA_DIR

    caminho = DATA_DIR / "escolas.xlsx"
    if not caminho.exists():
        return

    with get_session() as session:
        if list_schools(session):
            return

    _executa_seed_escolas(caminho)


def _executa_seed_escolas(caminho) -> None:
    """Le e importa escolas de data/escolas.xlsx — logica movida de importar_escolas.py."""
    import re
    import openpyxl
    from encaminhamento.database.crud import create_school, create_school_alias

    # Siglas (abreviaturas) para cada escola, na mesma ordem das linhas do xlsx.
    # Usadas para match de nomes abreviados (ex: "dofec" -> Domingos Fernandes)
    # em arquivos de importacao (planilhas, scanner CCI, .pnj).
    SIGLAS_POR_ORDEM = [
        "CMAEE",      # 1: C. M. A. E. E
        "CMEACM",     # 2: C. M. E. Aldair Coutinho Machado
        "CMEMMV",     # 3: C. M. E. Marcos Medeiros Valiengo
        "CMENA",      # 4: C. M. E. Nossa Senhora Aparecida
        "CMFAS",      # 5: Creche Municipal Floriano de Azeredo Siqueira
        "CMMAES",     # 6: Creche Municipal Maria Alaide do Espirito Santo
        "CMMCS",      # 7: Creche Municipal Maria da Conceicao dos Santos Campos
        "CMJRP",      # 8: Creche Municipal Professor Joao Rodrigues Pinto
        "CMSOS",      # 9: Creche Municipal Saul de Oliveira e Silva
        "EMASA",      # 10: E. M. Amalia Soares de Almeida
        "EMASP",      # 11: E. M. Amaro de Souza Paes
        "EMAM",       # 12: E. M. Angelo Antonio Mendonca
        "EMBA",       # 13: E. M. Belmiro Ribeiro Alves
        "EMCHS",      # 14: E. M. Chrisanto Henrique de Souza
        "DOFEC",      # 15: E. M. Domingos Fernandes da Costa
        "EMNA",       # 16: E. M. Dr. Newton Alves
        "ESC",        # 17: Educandario Santa Cecilia
        "EMEM",       # 18: E. M. Elysio de Magalhaes
        "EMEJG",      # 19: E. M. Evanir Jose Gaia
        "EMGIM",      # 20: E. M. Guilhermina Inacio Mendonca
        "EMJFB",      # 21: E. M. Joao Flavio Batista
        "CMEA1",      # 22: CMEA 1
        "EMLDM",      # 23: E. M. Luiz Delio Mendonca
        "EMAR",       # 24: E. M. Manoel Alves Rangel
        "EMSG",       # 25: E. M. Manoel de Souza Gomes
        "EMGM",       # 26: E. M. Manoel Grecy Mendonca
        "EMNB",       # 27: E. M. Manoel Nunes Barreto
        "EMMA",       # 28: E. M. Maria Viana de Abreu
        "EMPDGS",     # 29: E. M. Professora Dionelia Goncalves Santos
        "CMEJA",      # 30: CMEJA
        "CIEPGT",     # 31: Ciep 265 Municipalizado Professora Gladys Teixeira
        "EEMFAT",     # 32: E. E. M. Francisco Alves Toledo
        "EEMJBA",     # 33: E. E. M. Joao Batista Alves
        "EEMJSR",     # 34: E. E. M. Joao da Silva Ribeiro
        "EELGSN",     # 35: E. E. M. Luiz Gomes da Silva Neto
        "EEMDB",      # 36: E. E. M. Manoel Ducas de Brito
        "EELMN",      # 37: E. E. M. Manoel Luiz Nogueira
        "CMEA2",      # 38: CMEA 2
    ]

    def _limpar(valor):
        if valor is None:
            return ""
        texto = str(valor).strip()
        if not texto or set(texto) <= {"-", " "}:
            return ""
        return texto

    def _extrair_telefone(texto):
        if not texto:
            return ""
        limpo = re.sub(r"\s+", " ", str(texto))
        match = re.search(r"(\d{4,5})\s*-\s*(\d{4})", limpo)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        match = re.search(r"\b(\d{8,13})\b", limpo)
        return match.group(1) if match else ""

    def _separar_contato(texto):
        if not texto:
            return "", ""
        limpo = re.sub(r"\s+", " ", str(texto)).strip()
        telefone = _extrair_telefone(limpo)
        nome = limpo
        if telefone:
            nome = re.sub(r"[\s\-\.]*" + re.escape(telefone), "", nome)
            nome = re.sub(r"\s+", " ", nome).strip(" -.,")
        if not any(c.isalpha() for c in nome):
            nome = ""
        return nome, telefone

    wb = openpyxl.load_workbook(str(caminho), data_only=True)
    ws = wb.active

    linha_cabecalho = None
    for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), 1):
        celulas = [str(v).strip().upper() for v in row if v]
        if "ESCOLA" in celulas:
            linha_cabecalho = idx
            break
    if linha_cabecalho is None:
        print("Seed: cabeçalho 'Escola' não encontrado em escolas.xlsx — nada importado.")
        return

    criadas = 0
    aliases_criados = 0
    sigla_idx = 0
    with get_session() as session:
        for row in ws.iter_rows(min_row=linha_cabecalho + 1, values_only=True):
            numero = row[0]
            nome = _limpar(row[1] if len(row) > 1 else None)
            if not nome or not isinstance(numero, (int, float)):
                continue

            modalidade = _limpar(row[2] if len(row) > 2 else None)
            endereco = _limpar(row[3] if len(row) > 3 else None)
            distrito = _limpar(row[4] if len(row) > 4 else None)
            contato_bruto = _limpar(row[5] if len(row) > 5 else None)
            telefone = _limpar(row[7] if len(row) > 7 else None)
            email = _limpar(row[8] if len(row) > 8 else None)

            nome_contato, telefone_do_contato = _separar_contato(contato_bruto)
            if not telefone:
                telefone = telefone_do_contato

            endereco_completo = f"{endereco}, {distrito} Distrito" if endereco and distrito else endereco

            escola = create_school(
                session, nome,
                address=endereco_completo,
                distrito=distrito,
                modalidade=modalidade,
                contato=nome_contato,
                phone=telefone,
                email=email,
                is_origin=True,
                is_destination=True,
                oferta=0,
            )
            criadas += 1

            # Vincula sigla à escola recém-criada (ordem posicional do xlsx)
            if sigla_idx < len(SIGLAS_POR_ORDEM):
                sigla = SIGLAS_POR_ORDEM[sigla_idx]
                try:
                    create_school_alias(session, escola.id, sigla)
                    aliases_criados += 1
                except IntegrityError:
                    session.rollback()
                sigla_idx += 1

    print(f"Seed: {criadas} escola(s) importada(s) de escolas.xlsx.")
    if aliases_criados:
        print(f"Seed: {aliases_criados} sigla(s) vinculada(s) às escolas.")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()