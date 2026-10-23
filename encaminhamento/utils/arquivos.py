"""
Utilitarios para nomes de arquivo e gerenciamento de exportacoes.

Nomes de escola vem de planilha e podem ter quebra de linha, barra ou
caractere invalido. Sem limpar, o arquivo exportado nao abre.
"""
import os
import re
from pathlib import Path
from typing import Optional

INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def nome_seguro(texto: Optional[str], padrao: str = "arquivo", maximo: int = 120) -> str:
    """
    Devolve um texto seguro para usar em nome de arquivo.

    Troca quebra de linha e caractere invalido por underline, corta
    o que for longo demais e evita nome vazio.
    """
    if not texto:
        return padrao

    limpo = INVALIDOS.sub("_", str(texto))
    # quebra de linha isolada vira underline, e nao dois
    limpo = re.sub(r"[\r\n]+", "_", limpo)
    limpo = re.sub(r"\s{2,}", " ", limpo).strip(" ._-")

    if len(limpo) > maximo:
        limpo = limpo[:maximo].rstrip(" ._-")

    return limpo or padrao


def manter_arquivos_recentes(
    diretorio: Path,
    padrao: str,
    manter: int,
    nomes_preservar: Optional[list[str]] = None,
) -> int:
    """
    Mantem apenas os `manter` arquivos mais recentes em `diretorio`
    correspondentes a `padrao` (glob). Exclui os mais antigos por
    data de modificacao (st_mtime).

    Retorna a quantidade de arquivos removidos.

    `nomes_preservar` e uma lista de nomes de arquivo que nunca sao
    removidos (ex.: modeloupload_template.xlsx).
    """
    if manter <= 0:
        return 0

    nomes_preservar = set(nomes_preservar or [])
    arquivos = [
        f for f in diretorio.glob(padrao)
        if f.is_file() and f.name not in nomes_preservar
    ]

    if len(arquivos) <= manter:
        return 0

    # mais antigos primeiro (menor mtime)
    arquivos.sort(key=lambda f: f.stat().st_mtime)

    removidos = 0
    for f in arquivos[: len(arquivos) - manter]:
        try:
            f.unlink()
            removidos += 1
        except OSError:
            pass

    return removidos
