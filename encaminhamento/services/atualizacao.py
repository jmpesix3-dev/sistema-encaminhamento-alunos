"""
Atualizacao do sistema.

Quem usa o sistema baixou um ZIP do GitHub, sem pasta .git, entao nao ha
como ler o commit local. A versao instalada e guardada no momento da
instalacao: na primeira execucao o sistema pergunta ao GitHub qual e o
commit atual e anota como "instalado". Depois disso, cada verificacao
compara.

O endereco do repositorio vem do config, nunca do usuario.
"""
import json
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import requests

from encaminhamento.config import (
    BRANCH,
    DATA_DIR,
    INTERVALO_VERIFICACAO_HORAS,
    REPOSITORIO,
)

logger = logging.getLogger(__name__)

ARQUIVO_ESTADO = DATA_DIR / "atualizacao.json"
ARQUIVO_REQUISITOS = Path(__file__).resolve().parent.parent.parent / "requirements.txt"

TIMEOUT = 15

# Extensoes que a atualizacao pode trocar
EXTENSOES = {".py", ".bat", ".sh", ".md", ".txt"}
ARQUIVOS_FIXOS = {".env.example", "requirements.txt"}

# Pastas e arquivos que NUNCA podem ser tocados pela atualizacao.
#   venv/                 -> tem caminho da maquina onde foi criado
#   encaminhamento/data/  -> banco, coordenadas, exportacoes
#   .env                  -> chave do Google e do email
PROTEGIDOS = {"venv", ".venv", "data", ".env", "PYTHON_ENCONTRADO.txt"}

# Apaga da atualizacao: caches e lixo que nao fazem falta no destino
DESCARTAVEIS = {"__pycache__", ".git"}


def _estado_inicial() -> dict:
    return {
        "commit_instalado": None,
        "commit_remoto": None,
        "mensagem": "",
        "data_commit": "",
        "ultima_verificacao": None,
        "disponivel": False,
        "erro": "",
    }


def estado() -> dict:
    """Le o estado salvo, sem sair a rede."""
    dados = _estado_inicial()
    if ARQUIVO_ESTADO.exists():
        try:
            with open(ARQUIVO_ESTADO, encoding="utf-8") as f:
                salvo = json.load(f)
            if isinstance(salvo, dict):
                dados.update(salvo)
        except (OSError, ValueError) as exc:
            logger.debug("estado de atualizacao ilegivel: %s", exc)
    return dados


def _salvar(dados: dict) -> None:
    try:
        ARQUIVO_ESTADO.parent.mkdir(parents=True, exist_ok=True)
        with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.debug("nao consegui gravar o estado: %s", exc)


def _pode_verificar(forcar: bool) -> bool:
    """Respeita o intervalo de horas para nao estourar o limite do GitHub."""
    if forcar:
        return True
    dados = estado()
    ultima = dados.get("ultima_verificacao")
    if not ultima:
        return True
    try:
        quando = datetime.fromisoformat(ultima)
    except ValueError:
        return True
    return datetime.now() - quando > timedelta(hours=INTERVALO_VERIFICACAO_HORAS)


def _buscar_commit() -> Optional[dict]:
    """Consulta o ultimo commit do repositorio."""
    url = f"https://api.github.com/repos/{REPOSITORIO}/commits/{BRANCH}"
    try:
        resposta = requests.get(
            url,
            timeout=TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resposta.status_code != 200:
            return None
        dados = resposta.json()
        return {
            "sha": dados.get("sha", ""),
            "mensagem": (dados.get("commit", {}).get("message", "")
                         .splitlines() or [""])[0],
            "data": dados.get("commit", {}).get("committer", {}).get("date", ""),
        }
    except requests.RequestException as exc:
        logger.debug("consulta de commit falhou: %s", exc)
        return None


def verificar(forcar: bool = False) -> dict:
    """
    Confere se ha versao nova.

    Nao sai a rede se a ultima consulta foi recente, a menos que forcar=True.
    Sem internet, devolve o estado anterior com o erro registrado.
    """
    if not _pode_verificar(forcar):
        return estado()

    dados = estado()
    remoto = _buscar_commit()

    if remoto is None:
        dados["erro"] = "Nao foi possivel consultar o GitHub (sem internet?)"
        _salvar(dados)
        return dados

    dados["erro"] = ""
    dados["ultima_verificacao"] = datetime.now().isoformat(timespec="seconds")
    dados["commit_remoto"] = remoto["sha"]
    dados["mensagem"] = remoto["mensagem"]
    dados["data_commit"] = remoto["data"]

    # Primeira execucao: registra o que esta instalado agora
    if not dados.get("commit_instalado"):
        dados["commit_instalado"] = remoto["sha"]
        dados["disponivel"] = False
        _salvar(dados)
        return dados

    dados["disponivel"] = remoto["sha"] != dados["commit_instalado"]
    _salvar(dados)
    return dados


def ha_atualizacao() -> bool:
    """Tem versao nova? Le apenas o cache."""
    return bool(estado().get("disponivel"))


def _le_requisitos() -> str:
    try:
        return ARQUIVO_REQUISITOS.read_text(encoding="utf-8")
    except OSError:
        return ""


def _copiar_relevantes(origem: Path, destino: Path) -> Tuple[int, bool]:
    """
    Copia so os arquivos de codigo, nunca dados nem ambiente.

    Devolve (quantidade copiada, requirements mudou).
    """
    # Compara o requirements.txt do ZIP com o que esta instalado
    requisitos_zip = ""
    origem_requisitos = origem / "requirements.txt"
    if origem_requisitos.exists():
        try:
            requisitos_zip = origem_requisitos.read_text(encoding="utf-8")
        except OSError:
            requisitos_zip = ""

    requisitos_antes = ""
    destino_requisitos = destino / "requirements.txt"
    if destino_requisitos.exists():
        try:
            requisitos_antes = destino_requisitos.read_text(encoding="utf-8")
        except OSError:
            requisitos_antes = ""

    copiados = 0

    for item in origem.rglob("*"):
        if item.is_dir():
            continue

        relativo = item.relative_to(origem)
        partes = relativo.parts

        # Proibido atravessar venv, data, .env
        if qualquer_parte_protegida(partes):
            continue

        # Fora do pacote, so arquivos da raiz (instalar.bat, iniciar.py...)
        if partes[0] != "encaminhamento":
            permitido = len(partes) == 1 and (
                item.name in ARQUIVOS_FIXOS
                or item.suffix in EXTENSOES
            )
        else:
            permitido = item.suffix in EXTENSOES

        if not permitido:
            continue
        if item.name in DESCARTAVEIS or item.suffix == ".pyc":
            continue

        alvo = destino / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, alvo)
        copiados += 1

    # Compara depois de copiar: se o ZIP traz requirements, ele substitui
    destino_requisitos = destino / "requirements.txt"
    if destino_requisitos.exists():
        try:
            requisitos_depois = destino_requisitos.read_text(encoding="utf-8")
        except OSError:
            requisitos_depois = ""
        mudou = requisitos_antes.strip() != requisitos_depois.strip()
    else:
        mudou = bool(requisitos_zip.strip()) and requisitos_zip.strip() != requisitos_antes.strip()

    return copiados, mudou


def qualquer_parte_protegida(partes: tuple) -> bool:
    """True se o caminho atravessa algo que nao pode ser trocado."""
    for parte in partes:
        if parte in PROTEGIDOS:
            return True
    return False


def aplicar() -> dict:
    """
    Baixa a versao nova e troca so o codigo.

    A extracao acontece numa pasta temporaria: se algo falhar antes da
    copia, nada foi tocado.
    """
    dados = verificar(forcar=True)

    if dados.get("erro"):
        return {
            "ok": False,
            "mensagem": dados["erro"],
        }

    if not dados.get("disponivel"):
        return {
            "ok": False,
            "mensagem": "O sistema ja esta na versao mais recente.",
        }

    url_zip = f"https://github.com/{REPOSITORIO}/archive/refs/heads/{BRANCH}.zip"
    destino = Path(__file__).resolve().parent.parent.parent

    try:
        with tempfile.TemporaryDirectory() as temporaria:
            caminho_zip = Path(temporaria) / "atualizacao.zip"

            with requests.get(
                url_zip, timeout=120, stream=True, allow_redirects=True
            ) as resposta:
                if resposta.status_code != 200:
                    return {
                        "ok": False,
                        "mensagem": f"Falha no download (HTTP {resposta.status_code}).",
                    }
                with open(caminho_zip, "wb") as f:
                    for pedaco in resposta.iter_content(chunk_size=65536):
                        f.write(pedaco)

            pasta_extraida = Path(temporaria) / "extraido"
            with zipfile.ZipFile(caminho_zip) as z:
                z.extractall(pasta_extraida)

            # O ZIP vem com uma pasta raiz (repo-branch)
            subpastas = [p for p in pasta_extraida.iterdir() if p.is_dir()]
            if not subpastas:
                return {"ok": False, "mensagem": "ZIP com conteudo inesperado."}
            raiz_zip = subpastas[0]

            copiados, mudou_requisitos = _copiar_relevantes(raiz_zip, destino)

    except requests.RequestException as exc:
        return {"ok": False, "mensagem": f"Falha de internet: {exc}"}
    except (OSError, zipfile.BadZipFile) as exc:
        return {"ok": False, "mensagem": f"Falha ao extrair: {exc}"}

    # Marca como instalado
    dados = estado()
    dados["commit_instalado"] = dados.get("commit_remoto")
    dados["disponivel"] = False
    dados["erro"] = ""
    _salvar(dados)

    return {
        "ok": True,
        "arquivos": copiados,
        "requisitos_mudaram": mudou_requisitos,
        "commit": (dados.get("commit_instalado") or "")[:7],
        "mensagem": dados.get("mensagem", ""),
    }


def reiniciar_registro():
    """Esquece a versao instalada (util para teste)."""
    dados = _estado_inicial()
    _salvar(dados)
    return dados
