import re
from typing import Optional
from encaminhamento.database.models import School
from encaminhamento.database import get_session
from encaminhamento.database.crud import find_or_create_school


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

    return None


def get_or_create_school_from_name(
    name: str,
    is_origin: bool = True,
    is_destination: bool = True,
) -> int:
    """
    Devolve o id da escola com esse nome.
    Procura por equivalencia; cria a escola se nao encontrar.
    """
    from encaminhamento.database.crud import get_school_by_name, find_or_create_school

    nome = (name or "").strip()
    if not nome:
        return None

    with get_session() as session:
        exata = get_school_by_name(session, nome)
        if exata:
            return exata.id

    # Procura por equivalencia (fora da sessao para nao aninhar)
    achado = match_school_name(nome)
    if achado:
        return achado

    with get_session() as session:
        nova = find_or_create_school(
            session, nome, is_origin=is_origin, is_destination=is_destination
        )
        return nova.id


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