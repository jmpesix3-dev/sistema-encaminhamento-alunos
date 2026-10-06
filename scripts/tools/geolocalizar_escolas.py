"""
Geolocaliza as escolas que ainda nao tem coordenada, usando o campo
'distrito' que veio do escolas.xlsx, e grava o resultado no banco.

Uso:
    python geolocalizar_escolas.py              # so as que faltam coordenada
    python geolocalizar_escolas.py --rezerar    # apaga as coordenadas e refaz
    python geolocalizar_escolas.py --cache      # ignora o cache e refaz tudo
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from encaminhamento.database import init_db, get_session
from encaminhamento.database.crud import list_schools, update_school
from encaminhamento.services.geocoding import get_geocoding_service, NIVEL


def main():
    init_db()

    geo = get_geocoding_service()

    if "--cache" in sys.argv:
        geo.limpar_cache()
        print("Cache limpo.\n")

    if "--rezerar" in sys.argv:
        with get_session() as session:
            for e in list_schools(session):
                update_school(session, e.id, latitude=None, longitude=None)
        print("Coordenadas apagadas.\n")

    print("Provedores ativos:", ", ".join(geo.provedores_ativos()))
    if geo.tem_google():
        print("Google Maps disponivel.\n")
    else:
        print("Sem GOOGLE_MAPS_API_KEY: usando OpenStreetMap + distrito.\n")

    with get_session() as session:
        alvos = [
            {"id": e.id, "nome": e.name, "endereco": e.address or e.name, "distrito": e.distrito}
            for e in list_schools(session)
            if e.latitude is None
        ]

    if not alvos:
        print("Todas as escolas ja tem coordenada.")
        return

    print(f"{len(alvos)} escola(s) sem coordenada\n")

    def progresso(atual, total, endereco, status, resultado=None):
        marca = f"({resultado[0]:.5f}, {resultado[1]:.5f})" if resultado else ""
        end = endereco.replace("\n", " ")[:50]
        print(f"  [{atual:>2}/{total}] {status:<12} {end:<50} {marca}")

    geo.progresso = progresso
    resumo = geo.geocode_escolas(alvos)

    gravadas = 0
    for e in alvos:
        if e.get("lat") is not None:
            with get_session() as session:
                update_school(session, e["id"], latitude=e["lat"], longitude=e["lon"])
            gravadas += 1

    print(f"\nGravadas: {gravadas} escola(s)")
    print("\nPrecisao das coordenadas:")
    for nivel, qtd in resumo["por_nivel"].items():
        if qtd:
            print(f"  {NIVEL.get(nivel, nivel):<32} {qtd}")


if __name__ == "__main__":
    main()
