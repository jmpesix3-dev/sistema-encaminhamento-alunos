import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'encaminhamento.db'}")
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").lower() == "true"

EXCEL_IMPORT_DIR = DATA_DIR / "import"
EXCEL_EXPORT_DIR = DATA_DIR / "export"
PDF_EXPORT_DIR = DATA_DIR / "pdf"
BACKUP_DIR = DATA_DIR / "backup"

# Retençao de arquivos gerados (evita encher o disco com exportacoes
# repetidas). Mantem apenas os N mais recentes por diretorio.
RESUMO_KEEP_N = int(os.getenv("RESUMO_KEEP_N", "5"))
EXPORT_KEEP_N = int(os.getenv("EXPORT_KEEP_N", "5"))

for d in [EXCEL_IMPORT_DIR, EXCEL_EXPORT_DIR, PDF_EXPORT_DIR, BACKUP_DIR]:
    d.mkdir(exist_ok=True)

# Nome do sistema. Fica aqui para nao ter o texto espalhado em
# varios arquivos: mudar o nome e mudar so esta linha.
NOME_SISTEMA = "Encaminhamento Escolar de Alunos"
APP_TITLE = NOME_SISTEMA
APP_ICON = "📋"
PAGE_LAYOUT = "wide"

# Atualizacao -------------------------------------------------------
# Repositorio de onde o sistema busca as versoes novas. O endereco e
# fixo no codigo: o usuario nao informa nenhuma URL.
REPOSITORIO = os.getenv("REPOSITORIO", "jmpesix3-dev/sistema-encaminhamento-alunos")
BRANCH = os.getenv("BRANCH", "master")

# A API publica do GitHub permite 60 requisicoes por hora por IP.
# Com 6 horas de intervalo, mesmo abrindo o sistema muitas vezes por
# dia sai apenas uma consulta.
INTERVALO_VERIFICACAO_HORAS = int(os.getenv("INTERVALO_VERIFICACAO_HORAS", "6"))

# Geolocalizacao -----------------------------------------------------
# Chave do Google Maps Geocoding API. Sem a chave, o sistema usa
# o OpenStreetMap (Nominatim) e, em ultimo caso, a posicao por distrito.
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# Ordem de tentativa: Google primeiro (preciso), depois o gratuito.
GEO_PROVEDORES = os.getenv("GEO_PROVEDORES", "google,nominatim,distrito")


# -------------------------------------------------------------------
# SMTP: le do banco de dados (tabela system_configs) com fallback para
# variaveis de ambiente (.env). Isso permite configurar via interface
# sem editar o arquivo .env manualmente.
# -------------------------------------------------------------------

def _get_config_from_db(key: str, default: str = None) -> str:
    """Lê uma configuração do banco, com fallback para variável de ambiente."""
    try:
        from encaminhamento.database import get_session
        from encaminhamento.database.crud import get_system_config
        with get_session() as session:
            val = get_system_config(session, key)
            if val is not None and val != "":
                return val
    except Exception:
        pass
    return default or ""


SMTP_HOST = _get_config_from_db("SMTP_HOST", os.getenv("SMTP_HOST", "smtp.gmail.com"))
SMTP_PORT = int(_get_config_from_db("SMTP_PORT", os.getenv("SMTP_PORT", "587")))
SMTP_USER = _get_config_from_db("SMTP_USER", os.getenv("SMTP_USER", ""))
SMTP_PASSWORD = _get_config_from_db("SMTP_PASSWORD", os.getenv("SMTP_PASSWORD", ""))
SMTP_USE_TLS = _get_config_from_db("SMTP_USE_TLS", os.getenv("SMTP_USE_TLS", "true")).lower() == "true"
EMAIL_FROM = _get_config_from_db("EMAIL_FROM", os.getenv("EMAIL_FROM", SMTP_USER))