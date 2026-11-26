"""Testes da camada de dados da US20 (hotspots por temporada).

Só dependem de pandas: o CI de ML não instala geopandas/libpysal/esda. Os
testes espaciais ficam no arquivo do pipeline, com ``pytest.importorskip``.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))

import hotspots


HISTORICO = Path(__file__).resolve().parents[1] / "app" / "data" / "sinan_bairro_se_2016_2025.csv"
PAINEL = Path(__file__).resolve().parents[1] / "app" / "data" / "painel" / "painel_bairro_se.csv"


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
