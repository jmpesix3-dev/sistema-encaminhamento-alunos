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

for d in [EXCEL_IMPORT_DIR, EXCEL_EXPORT_DIR, PDF_EXPORT_DIR, BACKUP_DIR]:
    d.mkdir(exist_ok=True)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

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