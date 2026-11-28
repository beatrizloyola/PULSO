"""Testes da camada de dados da US20 (hotspots por temporada).

Só dependem de pandas: o CI de ML não instala geopandas/libpysal/esda. Os
testes espaciais ficam no arquivo do pipeline, com ``pytest.importorskip``.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))

import hotspots


HISTORICO = Path(__file__).resolve().parents[1] / "app" / "data" / "sinan_bairro_se_2016_2025.csv"
PAINEL = Path(__file__).resolve().parents[1] / "app" / "data" / "painel" / "painel_bairro_se.csv"
PESOS_BAIRRO = (
    Path(__file__).resolve().parents[1]
    / "notebooks" / "saidas" / "us20_sensibilidade_pesos_bairro.csv"
)


@pytest.mark.parametrize(
    "entrada,esperado",
    [(202401, 2024), ("2024-W20", 2024), (202553, 2025), ("2025-W01", 2025)],
)
def test_temporada_da_semana_aceita_formatos(entrada, esperado):
    assert hotspots.temporada_da_semana(entrada) == esperado


@pytest.mark.parametrize("entrada", ["2024", "202460", "202400", "abc", "2024-W2"])
def test_temporada_da_semana_rejeita_invalido(entrada):
    with pytest.raises(ValueError):
        hotspots.temporada_da_semana(entrada)


def test_historico_cobre_2016_2025_com_94_bairros():
    casos = hotspots.carregar_casos_historicos()

    assert sorted(casos["temporada"].unique()) == list(range(2016, 2026))
    # Pau Ferro não tem nenhum caso na série; entra como zero em completar_temporadas.
    assert casos["key"].nunique() == 93
    assert casos["bairro_id"].notna().all()
    assert casos["ds"].notna().all()
    assert set(casos["ds"].unique()) <= {str(i) for i in range(1, 9)}
    assert (casos["casos"] >= 0).all()
    assert casos["fonte"].nunique() == 1
    assert casos["fonte"].iloc[0] == hotspots.FONTE_HISTORICA


def test_historico_perde_poucos_casos_fora_do_lookup():
    brutos = pd.read_csv(HISTORICO)
    casos = hotspots.carregar_casos_historicos()

    total_bruto = int(brutos["casos"].sum())
    total_carregado = int(casos["casos"].sum())
    assert casos.attrs["casos_brutos"] == total_bruto
    assert casos.attrs["casos_fora_lookup"] == total_bruto - total_carregado
    assert total_carregado >= total_bruto * 0.995
    assert casos.attrs["registros_fora_lookup"] > 0


def test_historico_soma_variantes_do_mesmo_bairro(tmp_path):
    """Grafias que normalizam para a mesma chave não podem duplicar o bairro."""
    caminho = tmp_path / "historico.csv"
    pd.DataFrame([
        {"bairro": "AFLITOS", "semana": 202401, "casos": 2, "ano": 2024},
        {"bairro": "Aflitos ", "semana": 202401, "casos": 3, "ano": 2024},
    ]).to_csv(caminho, index=False)

    casos = hotspots.carregar_casos_historicos(caminho)

    assert len(casos) == 1
    assert int(casos.loc[0, "casos"]) == 5


def test_historico_rejeita_ano_incoerente_com_semana(tmp_path):
    caminho = tmp_path / "historico.csv"
    pd.DataFrame([
        {"bairro": "AFLITOS", "semana": 202401, "casos": 1, "ano": 2023},
    ]).to_csv(caminho, index=False)

    with pytest.raises(ValueError, match="ano"):
        hotspots.carregar_casos_historicos(caminho)


def test_historico_inexistente_falha_com_comando(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_sinan_historico"):
        hotspots.carregar_casos_historicos(tmp_path / "nao_existe.csv")


def test_completar_temporadas_zero_fill():
    casos = hotspots.carregar_casos_historicos()
    completos = hotspots.completar_temporadas(casos)

    assert len(completos) == 10 * 94
    assert completos["key"].nunique() == 94
    assert sorted(completos["temporada"].unique()) == list(range(2016, 2026))
    assert completos["casos"].notna().all()
    assert (completos["casos"] >= 0).all()
    assert not completos.duplicated(["temporada", "key"]).any()
    assert completos["casos"].sum() == casos["casos"].sum()
    assert completos["fonte"].nunique() == 1

    em_2024 = completos[completos["temporada"] == 2024]
    assert len(em_2024) == 94
    assert int((em_2024["casos"] > 0).sum()) == 76

    assert list(completos.columns) == hotspots.COLUNAS_CASOS


def test_completar_temporadas_rejeita_duplicata():
    casos = hotspots.carregar_casos_historicos()
    duplicado = pd.concat([casos, casos.head(1)], ignore_index=True)

    with pytest.raises(ValueError, match="duplicado"):
        hotspots.completar_temporadas(duplicado)


def test_resumo_cobertura_e_serializavel():
    casos = hotspots.completar_temporadas(hotspots.carregar_casos_historicos())
    resumo = hotspots.resumo_cobertura(casos)

    assert resumo["temporadas"] == list(range(2016, 2026))
    assert resumo["n_bairros"] == 94
    assert resumo["n_linhas"] == 940
    assert sum(resumo["casos_por_temporada"].values()) == int(casos["casos"].sum())
    assert resumo["bairros_com_casos_por_temporada"]["2024"] == 76
    assert all(isinstance(t, str) for t in resumo["casos_por_temporada"])


@pytest.mark.skipif(not PAINEL.exists(), reason="painel US14 não gerado neste ambiente")
def test_painel_deriva_temporada_e_bairros():
    casos = hotspots.carregar_casos_painel()

    assert set(casos["temporada"].unique()) <= {2024, 2025}
    assert casos["key"].nunique() == 94
    assert casos["bairro_id"].notna().all()
    assert casos["casos"].notna().all()
    assert casos["fonte"].iloc[0] == hotspots.FONTE_PAINEL


@pytest.mark.skipif(not PAINEL.exists(), reason="painel US14 não gerado neste ambiente")
def test_painel_filtra_anos():
    casos = hotspots.carregar_casos_painel(anos=[2024])

    assert set(casos["temporada"].unique()) == {2024}
    assert casos["key"].nunique() == 94


# ---------------------------------------------------------------------------
# Estatística espacial
# ---------------------------------------------------------------------------


def test_classificar_quadrantes_mapeia_as_categorias():
    p = np.array([0.01, 0.01, 0.01, 0.01, 0.50])
    q = np.array([1, 2, 3, 4, 1])

    assert list(hotspots.classificar_quadrantes(p, q)) == ["HH", "LH", "LL", "HL", "ns"]


def test_classificar_quadrantes_respeita_o_limiar():
    assert hotspots.classificar_quadrantes([0.049], [1])[0] == "HH"
    assert hotspots.classificar_quadrantes([0.050], [1])[0] == "ns"


def test_classificar_quadrantes_rejeita_entradas_invalidas():
    with pytest.raises(ValueError):
        hotspots.classificar_quadrantes([0.01], [5])
    with pytest.raises(ValueError):
        hotspots.classificar_quadrantes([1.1], [1])
    with pytest.raises(ValueError):
        hotspots.classificar_quadrantes([0.01, 0.02], [1])


def test_bh_nunca_rejeita_mais_que_o_p_bruto():
    p = np.array([0.001, 0.010, 0.020, 0.040, 0.500, 0.900])
    p_bh = hotspots.corrigir_bh(p)

    assert np.all(p_bh >= p - 1e-12)
    assert np.all(p_bh <= 1)
    assert np.all((p_bh <= 0.05) <= (p <= 0.05))


def test_bh_exemplo_conhecido():
    # BH sobre [0,01..0,05] ajusta todos para 0,05.
    assert np.allclose(hotspots.corrigir_bh([0.01, 0.02, 0.03, 0.04, 0.05]), 0.05)


def test_bh_bate_com_statsmodels_quando_disponivel():
    sm = pytest.importorskip("statsmodels.stats.multitest")
    p = np.array([0.001, 0.004, 0.012, 0.03, 0.08, 0.21, 0.55, 0.90])

    esperado = sm.multipletests(p, method="fdr_bh")[1]
    assert np.allclose(hotspots.corrigir_bh(p), esperado)


@pytest.fixture
def grade_geo():
    """Grade 3x3 de polígonos contíguos, independente do GeoJSON real."""
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    geometrias = [box(x, y, x + 1, y + 1) for y in range(3) for x in range(3)]
    return gpd.GeoDataFrame(
        {
            "key": [f"B{i:02d}" for i in range(9)],
            "casos": [0, 0, 0, 0, 10, 20, 0, 30, 40],
        },
        geometry=geometrias,
        crs="EPSG:4326",
    )


def test_construir_pesos_queen_linha_padronizada(grade_geo):
    w, meta = hotspots.construir_pesos(grade_geo)

    assert w.n == 9
    assert meta["esquema_usado"] == "queen"
    assert meta["ilhas"] == []
    assert meta["fallback_por_ilhas"] is False
    somas = np.asarray(w.sparse.sum(axis=1)).ravel()
    assert np.allclose(somas, 1.0)


def test_construir_pesos_knn(grade_geo):
    w, meta = hotspots.construir_pesos(grade_geo, esquema="knn", k=2)

    assert w.n == 9
    assert meta["esquema_usado"] == "knn"
    assert set(w.cardinalities.values()) == {2}


def test_construir_pesos_rejeita_esquema_invalido(grade_geo):
    with pytest.raises(ValueError, match="esquema"):
        hotspots.construir_pesos(grade_geo, esquema="voronoi")
    with pytest.raises(ValueError, match="k="):
        hotspots.construir_pesos(grade_geo, esquema="knn", k=9)


def test_construir_pesos_cai_para_knn_quando_ha_ilhas():
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    geo = gpd.GeoDataFrame(
        {"key": ["A", "B"]},
        geometry=[box(0, 0, 1, 1), box(10, 10, 11, 11)],
        crs="EPSG:4326",
    )

    w, meta = hotspots.construir_pesos(geo, esquema="queen", k=1)

    assert meta["esquema_usado"] == "knn"
    assert meta["fallback_por_ilhas"] is True
    assert meta["ilhas"] == [0, 1]
    assert w.n == 2


def test_moran_e_lisa_deterministicos_com_seed(grade_geo):
    w, _ = hotspots.construir_pesos(grade_geo)

    moran_1 = hotspots.moran_global(grade_geo["casos"], w, permutacoes=99, seed=42)
    lisa_1 = hotspots.lisa_local(grade_geo["casos"], w, permutacoes=99, seed=42)
    moran_2 = hotspots.moran_global(grade_geo["casos"], w, permutacoes=99, seed=42)
    lisa_2 = hotspots.lisa_local(grade_geo["casos"], w, permutacoes=99, seed=42)

    assert moran_1["I"] == pytest.approx(moran_2["I"])
    assert lisa_1["p_sim"].tolist() == lisa_2["p_sim"].tolist()
    assert lisa_1["I_local"].tolist() == lisa_2["I_local"].tolist()
    assert set(lisa_1["q"]) <= {1, 2, 3, 4}
    assert 0 <= moran_1["p_perm"] <= 1


def test_calcular_temporada_retorna_contrato(grade_geo):
    resultado, resumo = hotspots.calcular_temporada(
        grade_geo,
        grade_geo[["key", "casos"]],
        permutacoes=99,
        seed=42,
    )

    assert len(resultado) == 9
    colunas = {
        "casos", "valor", "p_sim", "p_bh", "quadrante", "I_local",
        "cluster", "cluster_bh", "hotspot", "hotspot_bh",
    }
    assert colunas <= set(resultado.columns)
    assert resultado["cluster"].isin(["HH", "LH", "LL", "HL", "ns"]).all()
    assert resultado["cluster_bh"].isin(["HH", "LH", "LL", "HL", "ns"]).all()
    assert resultado["hotspot"].dtype == bool
    assert resultado["hotspot_bh"].dtype == bool
    assert (resultado["p_bh"] >= resultado["p_sim"] - 1e-12).all()
    assert (resultado["hotspot_bh"] <= resultado["hotspot"]).all()

    assert resumo["n_bairros"] == 9
    assert resumo["casos_total"] == 100
    assert resumo["moran"]["permutacoes"] == 99
    assert resumo["pesos"]["esquema_usado"] == "queen"
    assert sum(resumo["contagem"].values()) == 9
    assert sum(resumo["contagem_bh"].values()) == 9

    # A função não deve mutar a entrada.
    assert "cluster" not in grade_geo.columns


def test_calcular_temporada_nao_guarda_estado_entre_temporadas(grade_geo):
    casos_2024 = grade_geo[["key", "casos"]].copy()
    casos_2025 = casos_2024.copy()
    casos_2025.loc[8, "casos"] = 999

    out_2024_a, _ = hotspots.calcular_temporada(grade_geo, casos_2024, permutacoes=99, seed=42)
    out_2025, _ = hotspots.calcular_temporada(grade_geo, casos_2025, permutacoes=99, seed=42)
    out_2024_b, _ = hotspots.calcular_temporada(grade_geo, casos_2024, permutacoes=99, seed=42)

    assert out_2024_a["p_sim"].tolist() == out_2024_b["p_sim"].tolist()
    assert out_2024_a["cluster"].tolist() == out_2024_b["cluster"].tolist()
    assert out_2024_a["casos"].sum() != out_2025["casos"].sum()


def test_calcular_temporada_exige_todos_os_bairros(grade_geo):
    with pytest.raises(ValueError, match="faltam bairros"):
        hotspots.calcular_temporada(
            grade_geo,
            grade_geo[["key", "casos"]].iloc[:-1],
            permutacoes=99,
        )


def test_calcular_temporada_rejeita_contagem_nao_inteira(grade_geo):
    casos = grade_geo[["key", "casos"]].copy()
    casos["casos"] = casos["casos"].astype(float)
    casos.loc[0, "casos"] = 1.5

    with pytest.raises(ValueError, match="inteiras"):
        hotspots.calcular_temporada(grade_geo, casos, permutacoes=99)


def test_calcular_temporada_ignora_bairros_fora_da_geometria(grade_geo):
    casos = pd.concat([
        grade_geo[["key", "casos"]],
        pd.DataFrame({"key": ["EXTRA"], "casos": [99]}),
    ], ignore_index=True)

    resultado, resumo = hotspots.calcular_temporada(grade_geo, casos, permutacoes=99)

    assert resumo["bairros_extra_ignorados"] == ["EXTRA"]
    assert resultado["casos"].sum() == 100


def test_sensibilidade_pesos_bairro_bate_com_doc():
    """Artefato commitado precisa sustentar os números citados no doc da US20."""
    df = pd.read_csv(PESOS_BAIRRO)

    assert len(df) == 10 * 94 * 2
    assert set(df["esquema_solicitado"]) == {"queen", "knn"}
    assert (
        df.groupby(["temporada", "esquema_solicitado"])["key"]
        .nunique()
        .eq(94)
        .all()
    )

    knn = df[(df["esquema_solicitado"] == "knn") & df["hotspot"]]
    hh_knn = knn.groupby("key")["temporada"].nunique()
    assert hh_knn["JORDAO"] == 9
    assert hh_knn["BOA VIAGEM"] == 8
    assert hh_knn["IPSEP"] == 7
    assert hh_knn["IBURA"] == 6
    assert hh_knn["IMBIRIBEIRA"] == 1

    knn_bh = df[(df["esquema_solicitado"] == "knn") & df["hotspot_bh"]]
    hh_knn_bh = knn_bh.groupby("key")["temporada"].nunique()
    assert hh_knn_bh["JORDAO"] == 4
    assert hh_knn_bh["BOA VIAGEM"] == 4
    assert hh_knn_bh["IPSEP"] == 3
    assert hh_knn_bh["IBURA"] == 1
    assert hh_knn_bh.get("IMBIRIBEIRA", 0) == 0

    queen = df[(df["esquema_solicitado"] == "queen") & df["hotspot"]]
    hh_queen = queen.groupby("key")["temporada"].nunique()
    assert hh_queen["IBURA"] == 10
    assert hh_queen["IMBIRIBEIRA"] == 10
    assert hh_queen["JORDAO"] == 9
