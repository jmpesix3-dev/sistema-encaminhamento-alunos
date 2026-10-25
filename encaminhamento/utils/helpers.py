import re
from typing import List, Optional
from encaminhamento.database.models import School
from encaminhamento.database import get_session
from encaminhamento.database.crud import find_or_create_school, list_schools, get_school_by_name


PREFIXOS_SIGLA = [
    "EM", "EE", "CM", "CME", "MUNICIPAL", "ESTADUAL",
    "DE", "DA", "DO", "DAS", "DOS",
]


EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')


def parse_email_list(raw: str) -> List[str]:
    """
    Extrai enderecos de email de um texto livre.

    Suporta separadores por linha, virgula, ponto-e-virgula e espaco.
    Mantem a ordem e remove duplicatas.
    """
    if not raw:
        return []
    matches = EMAIL_RE.findall(raw)
    return list(dict.fromkeys(matches))


def validar_emails(raw: str) -> dict:
    """
    Separa enderecos validos de invalidos num texto livre.

    Suporta os mesmos separadores de ``parse_email_list``.
    Retorna ``{"validos": [...], "invalidos": [...]}``.
    """
    validos: List[str] = []
    invalidos: List[str] = []
    if not raw:
        return {"validos": validos, "invalidos": invalidos}
    for token in re.split(r"[,\s;]+", raw.strip()):
        token = token.strip()
        if not token:
            continue
        if EMAIL_RE.fullmatch(token):
            validos.append(token)
        else:
            invalidos.append(token)
    validos = list(dict.fromkeys(validos))
    invalidos = list(dict.fromkeys(invalidos))
    return {"validos": validos, "invalidos": invalidos}


ORDINAIS = re.compile(r"^\s*\d+\s*[ªº°]\s*", re.IGNORECASE)
PREFIXOS = re.compile(r"^(E\.?\s*E\.?\s*M\.?|E\.?\s*M\.?|C\.?\s*M\.?|EMEF|EM|CM|C\.?\s*E\.?)\s*", re.IGNORECASE)


def normalize_school_name(name: str) -> str:
    """Normaliza o nome da escola para comparar nomes parecidos."""
    if not name:
        return ""

    texto = str(name).strip()

    # Remove ordinais do inicio (1ª, 2ª, 3º ...)
    texto = ORDINAIS.sub("", texto)

    # Remove prefixos repetidos (E. E. M., C. M., EM, ...)
    anterior = None
    while anterior != texto:
        anterior = texto
        texto = PREFIXOS.sub("", texto, count=1).strip()

    texto = re.sub(r"\s+", " ", texto)
    return texto.strip(" .-").upper()


def _remover_prefixos(nome: str) -> List[str]:
    """Remove prefixos genéricos e retorna palavras significativas (maiúsculas).

    Remove prefixos multipartidos como 'E. M.', 'E. E.', 'C. M.', 'C. M. E.'
    bem como prefixos simples como 'Municipal', 'Estadual', 'de', 'da', 'do', etc.
    """
    texto = str(nome)
    texto = re.sub(r"\s+", " ", texto).strip().upper()

    texto = re.sub(r"^E\.?\s*E\.?\s*M\.?\s*", "", texto)
    texto = re.sub(r"^C\.?\s*M\.?\s*E\.?\s*", "", texto)
    texto = re.sub(r"^E\.?\s*M\.?\s*", "", texto)
    texto = re.sub(r"^C\.?\s*M\.?\s*", "", texto)

    for prefixo in PREFIXOS_SIGLA:
        if prefixo not in ("EM", "EE", "CM", "CME"):
            texto = re.sub(rf"\b{re.escape(prefixo)}\b", "", texto)

    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    palavras = [p for p in texto.split() if p]
    return [p.upper() for p in palavras]


def gerar_siglas_variacoes(nome: str) -> List[str]:
    """Gera variações de sigla a partir do nome da escola.

    Remove prefixos genéricos (E. M., E. E., C. M., C. M. E., Municipal,
    Estadual, de, da, do, das, dos) e produz:
      - v1: iniciais (primeira letra de cada palavra, max 6 chars)
      - v2: primeiras 2 palavras (max 10 chars)
      - v3: nome completo sem prefixos (max 25 chars)
      - v4: prefixo original + 1ª palavra sem prefixo (max 6 chars)

    Todas em maiúsculas, sem espaços.
    """
    if not nome:
        return []

    palavras = _remover_prefixos(nome)
    if not palavras:
        return []

    # v1: iniciais — primeira letra de cada palavra, max 6 chars
    v1 = "".join(p[0] for p in palavras if p)[:6]
    # v2: primeiras 2 palavras (max 10 chars)
    v2 = "".join(palavras[:2])[:10]
    # v3: nome completo sem prefixos (max 25 chars)
    v3 = "".join(palavras)[:25]
    # v4: prefixo original + 1ª palavra sem prefixo (max 6 chars)
    texto_original = re.sub(r"\s+", " ", str(nome)).strip().split()
    if texto_original:
        prefixo_original = texto_original[0].upper().replace(".", "")
        v4 = (prefixo_original + palavras[0])[:6]
    else:
        v4 = palavras[0][:6]

    # Remove vazias e duplicatas, mantendo ordem
    result = []
    for sigla in (v1, v2, v3, v4):
        sigla = sigla.strip().replace(" ", "").upper()
        if sigla and sigla not in result:
            result.append(sigla)
    return result


def _nome_contido(a: str, b: str) -> bool:
    """True quando um nome normalizado esta contido no outro."""
    if not a or not b:
        return False
    return a in b or b in a


def match_school_name(input_name: str, threshold: float = 0.6) -> Optional[int]:
    """
    Encontra o id da escola que corresponde ao nome informado.
    Retorna None quando nao encontra.
    """
    with get_session() as session:
        lista = [
            {"id": e.id, "norm": normalize_school_name(e.name)}
            for e in list_schools(session)
        ]

    if not lista:
        return None

    alvo = normalize_school_name(input_name)
    if not alvo:
        return None

    # 1) Correspondencia exata
    for item in lista:
        if item["norm"] == alvo:
            return item["id"]

    # 2) Um nome contem o outro
    for item in lista:
        if _nome_contido(alvo, item["norm"]):
            return item["id"]

    # 3) Palavras em comum
    palavras_alvo = set(alvo.split())
    melhor_id = None
    melhor_nota = 0.0

    for item in lista:
        palavras = set(item["norm"].split())
        if not palavras or not palavras_alvo:
            continue
        nota = len(palavras & palavras_alvo) / len(palavras | palavras_alvo)
        if nota > melhor_nota:
            melhor_nota = nota
            melhor_id = item["id"]

    if melhor_id is not None and melhor_nota >= threshold:
        return melhor_id

    # 4) Verificar aliases cadastradas (siglas como "dofec" -> Domingos Fernandes)
    with get_session() as session:
        from encaminhamento.database.crud import find_school_by_alias
        # Tenta com o nome normalizado (para nomes completos de escolas)
        alias_school_id = find_school_by_alias(session, alvo)
        if alias_school_id:
            return alias_school_id
        # Tenta com o nome bruto (siglas como "CMAEE", "dofec" podem ter
        # prefixos removidos pela normalizacao, ex: "CM" removido de "CMAEE")
        bruto = input_name.strip().upper() if input_name else ""
        if bruto and bruto != alvo:
            alias_school_id = find_school_by_alias(session, bruto)
            if alias_school_id:
                return alias_school_id

    return None


def get_or_create_school_from_name(
    name: str,
    is_origin: bool = True,
    is_destination: bool = True,
) -> Optional[int]:
    """
    Devolve o id da escola com esse nome.
    Procura por equivalencia (inclusive aliases). Nao cria escola se nao encontrar.
    """
    nome = (name or "").strip()
    if not nome:
        return None

    with get_session() as session:
        exata = get_school_by_name(session, nome)
        if exata:
            return exata.id

    # Procura por equivalencia (fora da sessao para nao aninhar)
    achado = match_school_name(nome)
    return achado


def parse_address_with_reference(address: str) -> tuple:
    """Parse address into main address and reference point."""
    if not address:
        return "", ""
    
    # Common reference point patterns
    patterns = [
        r'(?:ref\.?|referência|próximo|perto|casa|esquina|em frente|ao lado)\s*[:\-]?\s*(.+)$',
        r'(?:\(|\{)\s*(.+?)\s*(?:\)|\})$',  # Parentheses
    ]
    
    main_address = address.strip()
    reference = ""
    
    for pattern in patterns:
        match = re.search(pattern, address, re.IGNORECASE)
        if match:
            reference = match.group(1).strip()
            main_address = re.sub(pattern, '', address, flags=re.IGNORECASE).strip()
            break
    
    return main_address, reference


def format_student_name(name: str) -> str:
    """Format student name consistently."""
    if not name:
        return ""
    # Remove "Nome Civil:" prefix if present
    name = re.sub(r'^Nome Civil:\s*', '', name, flags=re.IGNORECASE)
    # Title case but preserve prepositions
    words = name.split()
    formatted = []
    prepositions = {'da', 'de', 'do', 'das', 'dos', 'e', 'a', 'o', 'as', 'os'}
    for i, word in enumerate(words):
        if i == 0 or word.lower() not in prepositions:
            formatted.append(word.capitalize())
        else:
            formatted.append(word.lower())
    return " ".join(formatted)