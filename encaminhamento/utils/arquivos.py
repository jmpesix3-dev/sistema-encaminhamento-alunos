"""
Utilitarios para nomes de arquivo.

Nomes de escola vem de planilha e podem ter quebra de linha, barra ou
caractere invalido. Sem limpar, o arquivo exportado nao abre.
"""
import re
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
