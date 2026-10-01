"""
Geolocalizacao de enderecos.

Usa provedores em cascata, do mais preciso para o mais generico:
  1. google    - Google Maps Geocoding API (precisa de GOOGLE_MAPS_API_KEY)
  2. nominatim - OpenStreetMap, sem chave
  3. distrito  - posicao aproximada pelo numero do distrito

Cada busca devolve tambem o "nivel" de precisao, para o sistema
poder avisar o usuario de onde veio a coordenada.
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests

from encaminhamento.config import DATA_DIR, GOOGLE_MAPS_API_KEY, GEO_PROVEDORES

logger = logging.getLogger(__name__)

CIDADE = {
    "cidade": "São João da Barra",
    "uf": "RJ",
    "pais": "Brazil",
    "lat": -21.6344,
    "lon": -41.0499,
}

# Distritos de Sao Joao da Barra que sabemos posicionar
DISTRITOS = {
    "1": (-21.6344, -41.0490),  # Centro
    "3": (-21.7015, -41.0338),  # Grussai
    "4": (-21.7191, -41.0944),  # Cajueiro
    "5": (-21.8935, -41.0550),  # Mato Escuro
}

NIVEL = {
    "exata": "endereco completo",
    "rua": "rua e numero",
    "localidade": "bairro/localidade",
    "distrito": "distrito (aproximado)",
    "centro": "centro da cidade (aproximado)",
}


def _numero_distrito(texto: str) -> Optional[str]:
    if not texto:
        return None
    m = re.search(r"(\d)\s*[º°o]?\s*distrito", str(texto), flags=re.IGNORECASE)
    return m.group(1) if m else None


def _localidade(texto: str) -> str:
    """
    Pega a localidade de um endereco.

    Resolve os formatos mais comuns:
      'R. Cardoso s/n, Cardoso, nº 414'            -> 'Cardoso'
      'Estrada Principal s/n, Mato Escuro'          -> 'Mato Escuro'
      'R. Ernani Alves nº 396, Atafona'             -> 'Atafona'
      'BR 356 s/n, Grussaí, 3º Distrito'            -> 'Grussaí'
      'Centro - Grussaí, 3º Distrito'                -> 'Grussaí'
    """
    if not texto:
        return ""

    s = str(texto)

    # "s/n", "sn", "s.n." e "sem numero" nao separam bairro: troca por espaco
    s = re.sub(r"\bs\s*/?\s*n\.?\b|\bsem\s+n[uú]mero\b", " ", s, flags=re.IGNORECASE)
    # Remove o numero do lote
    s = re.sub(r"[,\s]*\bn?[º°o]?\s*\.?\s*\d+\s*(?:[-/]\s*\d+)?\s*$", "", s, flags=re.IGNORECASE)
    # Remove marcas de distrito em qualquer posicao (aceita 3º, 3°, 3o ou 3)
    s = re.sub(r"[,;\s]*\b\d+\s*[º°o]?\s*distrito\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"[,;\s]*\bdistritos?\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bs[aã]o jo[aã]o da barra\b", " ", s, flags=re.IGNORECASE)

    # Pega a ultima parte util
    if "-" in s:
        parte = s.rsplit("-", 1)[-1]
    else:
        partes = [p.strip() for p in s.split(",") if p.strip()]
        parte = partes[-1] if partes else ""

    return parte.strip(" ,.-")


def _sem_numero(texto: str) -> str:
    """Remove o numero do final do endereco."""
    return re.sub(
        r"[,\s]*n?[º°]?\s*\d+\s*(?:[-/]\s*\d+)?\s*$", "", texto, flags=re.IGNORECASE
    )


def _so_rua(texto: str) -> str:
    """Pega so o nome da rua, sem numero e sem localidade."""
    rua = str(texto).split("-")[0]
    rua = re.sub(r"[,\s]*n?[º°]?\s*\d+\s*(?:[-/]\s*\d+)?\s*$", "", rua, flags=re.IGNORECASE)
    return rua.strip(" ,.-")


class GeocodingService:
    """Geolocaliza enderecos consultando provedores em cascata."""

    NOMINATIM = "https://nominatim.openstreetmap.org/search"
    GOOGLE = "https://maps.googleapis.com/maps/api/geocode/json"
    CACHE = DATA_DIR / "geocode_cache.json"

    def __init__(
        self,
        cache_file: str = None,
        progresso: Callable = None,
        api_key: str = None,
    ):
        self.cache_file = Path(cache_file) if cache_file else self.CACHE
        self.progresso = progresso
        self.api_key = api_key if api_key is not None else GOOGLE_MAPS_API_KEY
        self.provedores = [p.strip() for p in GEO_PROVEDORES.split(",") if p.strip()]
        self._ultima = 0.0
        self._cache: Dict[str, Tuple[float, float]] = self._carregar_cache()

    # ------------------------------------------------------------------
    def tem_google(self) -> bool:
        return bool(self.api_key) and "google" in self.provedores

    def provedores_ativos(self) -> List[str]:
        ativos = []
        for p in self.provedores:
            if p == "google" and not self.api_key:
                continue
            ativos.append(p)
        return ativos or ["distrito"]

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def _carregar_cache(self) -> Dict[str, Tuple[float, float]]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    return {k: tuple(v) for k, v in json.load(f).items()}
            except Exception:
                pass
        return {}

    def _salvar_cache(self):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({k: list(v) for k, v in self._cache.items()}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def limpar_cache(self):
        self._cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()

    def _do_cache(self, chave: str) -> Optional[Tuple[float, float]]:
        return self._cache.get(chave.strip().lower())

    def _no_cache(self, chave: str, coords: Tuple[float, float]):
        self._cache[chave.strip().lower()] = coords
        self._salvar_cache()

    # ------------------------------------------------------------------
    def _avisar(self, atual, total, endereco, status, resultado=None):
        if self.progresso:
            self.progresso(atual, total, endereco, status, resultado)

    def _esperar(self):
        decorrido = time.time() - self._ultima
        if decorrido < 1.1:
            time.sleep(1.1 - decorrido)

    # ------------------------------------------------------------------
    # Provedores
    # ------------------------------------------------------------------
    def _google(self, consulta: str) -> Optional[Tuple[float, float]]:
        try:
            r = requests.get(
                self.GOOGLE,
                params={"address": consulta, "key": self.api_key, "language": "pt-BR"},
                timeout=20,
            )
            self._ultima = time.time()
            dados = r.json()
            if dados.get("status") == "OK" and dados.get("results"):
                loc = dados["results"][0]["geometry"]["location"]
                return (float(loc["lat"]), float(loc["lng"]))
        except Exception as e:
            logger.debug("google falhou em %r: %s", consulta, e)
        return None

    def _nominatim(self, consulta: str) -> Optional[Tuple[float, float]]:
        chave = consulta.lower()
        achado = self._do_cache(chave)
        if achado:
            return achado

        self._esperar()
        try:
            r = requests.get(
                self.NOMINATIM,
                params={
                    "q": consulta,
                    "format": "json",
                    "limit": 1,
                    "viewbox": f"{CIDADE['lon'] - 0.4},{CIDADE['lat'] + 0.4},"
                               f"{CIDADE['lon'] + 0.4},{CIDADE['lat'] - 0.4}",
                    "bounded": 0,
                    "addressdetails": 1,
                },
                timeout=20,
                headers={"User-Agent": "EncaminhamentoAlunos/1.0 (educacao)"},
            )
            self._ultima = time.time()
            if r.status_code == 200 and r.json():
                res = r.json()[0]
                coords = (float(res["lat"]), float(res["lon"]))
                self._no_cache(chave, coords)
                return coords
        except Exception as e:
            logger.debug("nominatim falhou em %r: %s", consulta, e)
        return None

    @staticmethod
    def _espalhar(
        coords: Tuple[float, float],
        raio: float,
        semente: str = "",
    ) -> Tuple[float, float]:
        """
        Desloca o ponto de forma deterministica dentro de um raio.

        A semente garante que escolas diferentes no mesmo distrito fiquem em
        pontos diferentes, e que o resultado seja sempre o mesmo entre execucoes.
        """
        import math

        lat, lon = coords
        base = int(abs(lat * 1e5) + abs(lon * 1e5))
        semente_num = sum(ord(c) * (i + 1) for i, c in enumerate(semente))

        angulo = ((base + semente_num * 37) % 360) * math.pi / 180
        dist = raio * (0.25 + ((base + semente_num) % 100) / 120)
        return (
            round(lat + dist * math.cos(angulo) / 111.0, 6),
            round(lon + dist * math.sin(angulo) / (111.0 * math.cos(math.radians(lat))), 6),
        )

    # ------------------------------------------------------------------
    # Cascata
    # ------------------------------------------------------------------
    def geocode(
        self,
        endereco: str,
        distrito: str = None,
        abertura: float = 0.0,
        semente: str = "",
    ) -> Tuple[Optional[Tuple[float, float]], str, str]:
        """
        Geolocaliza um endereco.

        Retorna ((lat, lon), nivel, provedor), onde nivel esta em NIVEL
        e provedor em ('google', 'nominatim', 'distrito').
        """
        if not endereco:
            return None, "", ""

        texto = str(endereco).strip()
        cidade = f"{CIDADE['cidade']}, {CIDADE['uf']}, {CIDADE['pais']}"
        localidade = _localidade(texto)
        numero = _numero_distrito(texto) or _numero_distrito(distrito or "")

        # Consultas em ordem de preferencia
        consultas = [
            (f"{texto}, {cidade}", "exata"),
            (f"{_sem_numero(texto)}, {cidade}", "rua"),
        ]
        if localidade and any(c.isalpha() for c in localidade):
            consultas.append((f"{localidade}, {cidade}", "localidade"))
        rua = _so_rua(texto)
        if rua and any(c.isalpha() for c in rua) and rua.lower() != texto.lower():
            consultas.append((f"{rua}, {cidade}", "rua"))

        for provedor in self.provedores_ativos():
            if provedor == "distrito":
                break
            metodo = self._google if provedor == "google" else self._nominatim
            for consulta, nivel in consultas:
                coords = metodo(consulta)
                if coords:
                    if nivel in ("localidade", "rua") and abertura:
                        coords = self._espalhar(coords, abertura, semente or consulta)
                    return coords, nivel, provedor

        # Ultimo recurso: distrito
        if numero in DISTRITOS:
            base = DISTRITOS[numero]
            if abertura:
                base = self._espalhar(base, max(abertura, 0.5), semente or texto)
            return base, "distrito", "distrito"

        centro = (CIDADE["lat"], CIDADE["lon"])
        if abertura:
            centro = self._espalhar(centro, max(abertura, 0.8), semente or texto)
        return centro, "centro", "distrito"

    # ------------------------------------------------------------------
    # Processamento em lote
    # ------------------------------------------------------------------
    def geocode_escolas(self, escolas: List[dict]) -> dict:
        """
        escolas: [{'id', 'nome', 'endereco', 'distrito'}]
        Devolve um resumo com o nivel de cada escola.
        """
        total = len(escolas)
        resumo = {"exata": 0, "rua": 0, "localidade": 0, "distrito": 0, "centro": 0}
        sem = 0

        for i, e in enumerate(escolas, 1):
            endereco = e.get("endereco") or e.get("nome", "")
            self._avisar(i, total, endereco, "buscando...")

            coords, nivel, provedor = self.geocode(
                endereco, distrito=e.get("distrito"), abertura=0.35,
                semente=str(e.get("id", "")) + e.get("nome", ""),
            )
            resumo[nivel] = resumo.get(nivel, 0) + 1
            e["lat"], e["lon"] = coords
            e["nivel"] = nivel
            e["provedor"] = provedor

            self._avisar(i, total, endereco, f"{nivel}", coords)
            if i % 5 == 0:
                self._salvar_cache()

        self._salvar_cache()
        return {"total": total, "por_nivel": resumo, "sem_coordenada": sem}

    def geocode_alunos(self, alunos: List[dict]) -> dict:
        total = len(alunos)
        resumo = {"exata": 0, "rua": 0, "localidade": 0, "distrito": 0, "centro": 0}

        for i, a in enumerate(alunos, 1):
            endereco = a.get("endereco") or ""
            self._avisar(i, total, endereco, "buscando...")

            coords, nivel, provedor = self.geocode(
                endereco, abertura=0.25, semente=str(a.get("id", "")) + endereco
            )
            resumo[nivel] = resumo.get(nivel, 0) + 1
            a["lat"], a["lon"] = coords
            a["nivel"] = nivel

            self._avisar(i, total, endereco, nivel, coords)
            if i % 5 == 0:
                self._salvar_cache()

        self._salvar_cache()
        return {"total": total, "por_nivel": resumo}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia em quilometros entre dois pontos (Haversine)."""
    import math

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * math.asin(math.sqrt(a)) * 6371


_servico = None


def get_geocoding_service(progresso: Callable = None, api_key: str = None) -> GeocodingService:
    global _servico
    if _servico is None:
        _servico = GeocodingService()
    if progresso:
        _servico.progresso = progresso
    if api_key is not None:
        _servico.api_key = api_key
    return _servico
