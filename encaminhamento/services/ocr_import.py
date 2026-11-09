"""
OCR de alunos a partir de fotos ou scans (JPG/PNG).

Extrai texto da imagem com easyocr e tenta parsear registros de alunos
procurando rotulos tipo:
  Nome do aluno: ...
  Endereco: ...
  Destino 1: ...
  Destino 2: ...
  Assinatura: ...
"""

from typing import List, Optional
from PIL import Image
import io
import re


def ocr_image_to_text(file_bytes: bytes) -> str:
    """
    Executa OCR nos bytes de uma imagem e retorna o texto extraido.

    Requer easyocr (pip install easyocr). Na primeira execucao,
    o easyocr baixa os modelos de ML (~100 MB).
    """
    import easyocr
    import numpy as np

    reader = easyocr.Reader(["pt"], gpu=False)
    imagem = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    img_array = np.array(imagem)

    resultados = reader.readtext(img_array)
    linhas = [texto for (_, texto, _) in resultados]
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Rotulos que o parser procura (case-insensitive, com tolerancia a espacos)
# ---------------------------------------------------------------------------
NOME_RE = re.compile(r"nome\s*(?:do\s*aluno\s*|da\s*aluna\s*)?\s*[:]\s*(.*)", re.IGNORECASE)
ENDERECO_RE = re.compile(r"endereco\s*[:]\s*(.*)", re.IGNORECASE)
DESTINO1_RE = re.compile(r"destino\s*1\s*[:]\s*(.*)", re.IGNORECASE)
DESTINO2_RE = re.compile(r"destino\s*2\s*[:]\s*(.*)", re.IGNORECASE)
ASSINATURA_RE = re.compile(r"assinatura\s*[:]\s*(.*)", re.IGNORECASE)


def _extrair_valor(linha: str, padrao: re.Pattern) -> Optional[str]:
    """Extrai o valor apos o rotulo, ou None se nao houver correspondencia."""
    m = padrao.search(linha)
    if not m:
        return None
    return m.group(1).strip()


def _eh_vazio(valor: Optional[str]) -> bool:
    return not valor or not valor.strip()


def parse_ocr_text(texto: str) -> List[dict]:
    """
    Converte o texto bruto do OCR em uma lista de dicionarios de alunos.

    Cada aluno eh um bloco que comeca com um rotulo de "Nome". Os campos
    seguintes (endereco, destino 1, destino 2, assinatura) sao buscados
    nas linhas seguintes ate encontrar o proximo "Nome".

    Retorna lista de dicts com chaves:
      nome, endereco, destino_1, destino_2, assinatura (bool)
    """
    alunos: List[dict] = []
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    atual: Optional[dict] = None

    for linha in linhas:
        nome = _extrair_valor(linha, NOME_RE)
        if nome:
            # Salva o aluno anterior se existir
            if atual is not None:
                alunos.append(atual)
            atual = {
                "nome": nome,
                "endereco": "",
                "destino_1": "",
                "destino_2": "",
                "assinatura": False,
            }
            continue

        if atual is None:
            continue

        endereco = _extrair_valor(linha, ENDERECO_RE)
        if endereco is not None:
            atual["endereco"] = endereco
            continue

        destino1 = _extrair_valor(linha, DESTINO1_RE)
        if destino1 is not None:
            atual["destino_1"] = destino1
            continue

        destino2 = _extrair_valor(linha, DESTINO2_RE)
        if destino2 is not None:
            atual["destino_2"] = destino2
            continue

        assinatura = _extrair_valor(linha, ASSINATURA_RE)
        if assinatura is not None:
            atual["assinatura"] = assinatura.lower() not in ("não", "nao", "n", "0", "falso", "false")
            continue

    # Salva o ultimo aluno
    if atual is not None:
        alunos.append(atual)

    return alunos


def extrair_alunos_da_imagem(file_bytes: bytes) -> List[dict]:
    """
    Ponto de entrada unico: recebe bytes de uma imagem JPG/PNG e retorna
    a lista de alunos extraidos por OCR + parse.
    """
    texto = ocr_image_to_text(file_bytes)
    return parse_ocr_text(texto)