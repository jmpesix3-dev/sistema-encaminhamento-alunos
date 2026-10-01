"""Interage com filtros, abas e botoes de cada pagina para achar erro de runtime."""
from streamlit.testing.v1 import AppTest

from gerar_arquivos_teste import gerar, limpar

ARQUIVOS = gerar()

falhas = 0

# Rotulos reais das abas. O AppTest remove os emojis de .options,
# mas o valor do widget os mantem, entao usamos o texto completo.
ABAS = {
    "alunos": ["📤 Carregar Planilha", "✏️ Cadastro Manual",
               "📝 Editar Dados", "📊 Exportar"],
    "escolas": ["📋 Dados", "🎯 Capacidade", "📍 Localização"],
    "lotes": ["➕ Criar Lote", "📋 Gerenciar Lotes"],
    "automacao": ["📄 PDFs", "📧 Emails", "🔄 Status", "🔧 Configuração"],
    "alocacao": ["👁️ Prévia", "▶️ Executar", "📍 Coordenadas"],
}

IGNORAR = ("", "Todos", "Escolha ou digite para buscar...")


def _sel(at, key):
    """Seleciona a primeira opcao real de um selectbox."""
    for s in at.selectbox:
        if s.key == key:
            for i, opt in enumerate(s.options):
                if opt not in IGNORAR:
                    s.select_index(i)
                    return
    raise AssertionError(f"selectbox '{key}' nao encontrado ou sem opcoes")


def _texto(at, key, valor):
    for t in at.text_input:
        if t.key == key:
            t.set_value(valor)
            return
    raise AssertionError(f"text_input '{key}' nao encontrado")


def _aba(at, grupo, indice):
    """Seleciona a aba pelo rotulo real."""
    for c in at.segmented_control:
        c.set_value(ABAS[grupo][indice])
        return
    raise AssertionError("sem segmented_control")


def _botao(at, prefixos):
    """Clica no primeiro botao cujo rotulo comeca com um dos prefixos."""
    for b in at.button:
        for p in prefixos:
            if b.label.startswith(p):
                b.click()
                return
    raise AssertionError(f"nenhum botao comecando com {prefixos}")


def checa(nome, arquivo, acoes):
    global falhas
    print(f"--- {nome} ---")
    try:
        at = AppTest.from_file(arquivo, default_timeout=60)
        at.run()
    except Exception as e:
        falhas += 1
        print(f"   ERRO na carga: {type(e).__name__}: {e}")
        return

    if at.exception:
        falhas += 1
        print(f"   ERRO na carga: {at.exception[0].value}")
        return

    for descricao, acao in acoes:
        try:
            acao(at)
            at.run()
            if at.exception:
                falhas += 1
                print(f"   ERRO apos {descricao}: {at.exception[0].value}")
            else:
                print(f"   OK   {descricao}")
        except AssertionError as e:
            print(f"   pulou {descricao}: {e}")
        except Exception as e:
            falhas += 1
            print(f"   ERRO ao {descricao}: {type(e).__name__}: {e}")


checa("Alunos", ARQUIVOS["alunos"], [
    ("abrir aba editar", lambda at: _aba(at, "alunos", 2)),
    ("selecionar status", lambda at: _sel(at, "ed_status")),
    ("selecionar destino", lambda at: _sel(at, "ed_dest")),
    ("selecionar origem", lambda at: _sel(at, "ed_origem")),
    ("buscar por nome", lambda at: _texto(at, "ed_busca", "Arthur")),
    ("abrir aba exportar", lambda at: _aba(at, "alunos", 3)),
    ("selecionar destino export", lambda at: _sel(at, "ex_dest")),
    ("selecionar status export", lambda at: _sel(at, "ex_status")),
])

checa("Lotes", ARQUIVOS["lotes"], [
    ("selecionar ano", lambda at: _sel(at, "batch_filter_year")),
    ("selecionar status", lambda at: _sel(at, "batch_filter_status")),
    ("selecionar origem", lambda at: _sel(at, "batch_filter_origin")),
    ("selecionar destino", lambda at: _sel(at, "batch_filter_dest")),
    ("selecionar lote", lambda at: _sel(at, "selected_batch_detail")),
])

checa("Escolas", ARQUIVOS["escolas"], [
    ("abrir aba capacidade", lambda at: _aba(at, "escolas", 1)),
    ("abrir aba localizacao", lambda at: _aba(at, "escolas", 2)),
    ("filtrar escola", lambda at: _texto(at, "filtro_escolas", "CMEA")),
    ("limpar filtro", lambda at: _texto(at, "filtro_escolas", "")),
    ("abrir mapa de uma escola", lambda at: _botao(at, ("📍 Ajustar", "📍 Abrir", "Ajustar"))),
    ("fechar mapa", lambda at: _botao(at, ("✕ Fechar", "↩️ Voltar"))),
])

checa("Automação", ARQUIVOS["automacao"], [
    ("abrir aba emails", lambda at: _aba(at, "automacao", 1)),
    ("abrir aba status", lambda at: _aba(at, "automacao", 2)),
    ("abrir aba configuracao", lambda at: _aba(at, "automacao", 3)),
    ("abrir aba pdfs", lambda at: _aba(at, "automacao", 0)),
])

checa("Alocação", ARQUIVOS["alocacao"], [
    ("abrir aba executar", lambda at: _aba(at, "alocacao", 1)),
    ("abrir aba coordenadas", lambda at: _aba(at, "alocacao", 2)),
    ("voltar para previa", lambda at: _aba(at, "alocacao", 0)),
    ("simular alocação", lambda at: _botao(at, ("👁️ Simular",))),
])

limpar()
print()
print(f"ERROS: {falhas}")
