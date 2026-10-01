"""
Validação de coordenadas.

Usado na tela de Escolas para recusar pontos fora do município, o que
protege contra erro de digitação e coordenada colada de outro lugar.
"""
from typing import Optional, Tuple

# Limites aproximados de São João da Barra
LAT_MIN, LAT_MAX = -22.20, -21.50
LON_MIN, LON_MAX = -41.50, -40.70

CENTRO = (-21.6344, -41.0499)


def dentro_de_sao_joao_da_barra(
    lat: float,
    lon: float,
    margem: float = 0.5,
) -> bool:
    """Confere se o ponto fica dentro do municipio (ou perto)."""
    if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
        return True

    # Margem de tolerancia a partir do centro
    return abs(lat - CENTRO[0]) <= margem and abs(lon - CENTRO[1]) <= margem


def validar_coordenada(
    lat: Optional[float],
    lon: Optional[float],
) -> Tuple[bool, str]:
    """
    Valida um par de coordenadas.

    Devolve (ok, mensagem).
    """
    if lat is None or lon is None:
        return False, "Coordenada vazia"

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False, "Coordenada nao e um numero"

    if not (-90 <= lat <= 90):
        return False, f"Latitude fora do intervalo: {lat}"

    if not (-180 <= lon <= 180):
        return False, f"Longitude fora do intervalo: {lon}"

    if not dentro_de_sao_joao_da_barra(lat, lon):
        return False, "Ponto parece estar fora de Sao Joao da Barra"

    return True, "ok"
