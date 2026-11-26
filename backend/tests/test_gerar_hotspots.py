"""Smoke test do pipeline US20 (scripts/gerar_hotspots.py).

O teste roda o script de verdade em um diretório temporário, usando a série
US04 versionada. Ele é pulado no CI de ML, que não instala o stack geoespacial.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("libpysal")
pytest.importorskip("esda")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gerar_hotspots  # noqa: E402

PAINEL = Path(__file__).resolve().parents[1] / "app" / "data" / "painel" / "painel_bairro_se.csv"


def _primeiro_par(geometria: dict):
    coords = geometria["coordinates"]
    while isinstance(coords, list) and isinstance(coords[0], list):
        coords = coords[0]
    return coords


def test_gerar_hotspots_uma_temporada(tmp_path):
    codigo = gerar_hotspots.main([
        "--temporadas", "2024",
        "--permutacoes", "99",
        "--saida", str(tmp_path),
    ])
    assert codigo == 0

    geojson_path = tmp_path / "us20_lisa_2024.geojson"
    assert geojson_path.exists()
    dados = json.loads(geojson_path.read_text(encoding="utf-8"))
    assert len(dados["features"]) == 94

    props = dados["features"][0]["properties"]
    assert set(props) == set(gerar_hotspots.COLUNAS_SAIDA)
    assert props["temporada"] == 2024
    assert props["cluster"] in {"HH", "LH", "LL", "HL", "ns"}
    assert props["cluster_bh"] in {"HH", "LH", "LL", "HL", "ns"}
    assert isinstance(props["hotspot"], bool)
    assert isinstance(props["hotspot_bh"], bool)

    primeiro_par = _primeiro_par(dados["features"][0]["geometry"])
    assert -180 <= primeiro_par[0] <= 180
    assert -90 <= primeiro_par[1] <= 90

    lido = gpd.read_file(geojson_path)
    assert len(lido) == 94
    assert lido.crs.to_epsg() == 4326
    assert not lido.geometry.is_empty.any()

    lisa = pd.read_csv(tmp_path / "us20_lisa_bairro_temporada.csv")
    assert len(lisa) == 94
    assert lisa["key"].is_unique
    assert set(lisa["temporada"]) == {2024}
    assert lisa["casos"].sum() > 0

    moran = pd.read_csv(tmp_path / "us20_moran_global.csv")
    assert len(moran) == 1
    assert int(moran.loc[0, "n_bairros"]) == 94
    assert int(moran.loc[0, "permutacoes"]) == 99
    assert int(moran.loc[0, "seed"]) == 42
    assert -1 <= moran.loc[0, "I"] <= 1
    assert 0 <= moran.loc[0, "p_perm"] <= 1

    contagem = pd.read_csv(tmp_path / "us20_contagem_lisa.csv")
    assert set(contagem["categoria"]) == {"HH", "LH", "LL", "HL", "ns"}
    assert int(contagem["sem_bh"].sum()) == 94
    assert int(contagem["com_bh"].sum()) == 94

    hh = int(contagem.loc[contagem["categoria"] == "HH", "sem_bh"].iloc[0])
    hh_bh = int(contagem.loc[contagem["categoria"] == "HH", "com_bh"].iloc[0])

    ds = pd.read_csv(tmp_path / "us20_hh_por_ds.csv")
    assert set(ds["ds"].astype(str)) == {str(i) for i in range(1, 9)}
    assert int(ds["hh_sem_bh"].sum()) == hh
    assert int(ds["hh_com_bh"].sum()) == hh_bh

    meta = json.loads((tmp_path / "us20_meta.json").read_text(encoding="utf-8"))
    assert meta["fonte"] == "historico"
    assert "US04" in meta["fonte_descricao"]
    assert meta["temporadas"] == [2024]
    assert meta["n_bairros"] == 94
    assert meta["permutacoes"] == 99
    assert meta["seed"] == 42
    assert meta["pesos"]["esquema_usado"] == "queen"
    assert "cobertura" in meta
    assert meta["cobertura"]["casos_por_temporada"]["2024"] > 0
    assert "bibliotecas" in meta
    assert "us20_meta.json" in meta["saidas"]


@pytest.mark.skipif(not PAINEL.exists(), reason="painel US14 não gerado neste ambiente")
def test_gerar_hotspots_fonte_painel(tmp_path):
    codigo = gerar_hotspots.main([
        "--fonte", "painel",
        "--temporadas", "2024",
        "--permutacoes", "99",
        "--saida", str(tmp_path),
    ])
    assert codigo == 0

    meta = json.loads((tmp_path / "us20_meta.json").read_text(encoding="utf-8"))
    assert meta["fonte"] == "painel"
    assert "US14" in meta["fonte_descricao"]
    assert meta["temporadas"] == [2024]
    assert (tmp_path / "us20_lisa_2024.geojson").exists()
