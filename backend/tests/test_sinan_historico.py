"""Testes do build do histórico SINAN por bairro x semana (US04)."""
import json

import pandas as pd
import pytest

from app import config
from scripts import build_sinan_historico as build
from scripts.build_sinan_historico import (
    _col,
    _filtrar_descartados,
    _filtrar_municipio,
    _norm,
    _reagregar,
)

MUNICIPIO_RESIDENCIA = ["id_mn_resi", "co_municipio_residencia",
                        "id_municip", "co_municipio_notificacao"]


@pytest.fixture
def amostra_sinan():
    """Amostra mínima com bairro, semana, município e classificação final."""
    return pd.DataFrame({
        "id_mn_resi": ["261160", "260005", "261160", "261160", "999999"],
        "classi_fin": ["10", "10", "5", "3", None],
        "semana": [201602, 201602, 201602, 201603, 201603],
        "bairro": ["A", "B", "A", "A", "B"],
    })


def test_col_prioriza_municipio_de_residencia():
    df = pd.DataFrame(columns=["co_municipio_notificacao", "co_municipio_residencia"])
    assert _col(df, MUNICIPIO_RESIDENCIA) == "co_municipio_residencia"


def test_norm_remove_acentos_e_trata_sentinelas():
    assert _norm("  São José  ") == "SAO JOSE"
    assert _norm("Não Informado") is None
    assert _norm("") is None
    assert _norm(None) is None


def test_filtro_municipio_mantem_apenas_recife(amostra_sinan):
    out = _filtrar_municipio(amostra_sinan, "id_mn_resi")
    assert out["id_mn_resi"].tolist() == ["261160", "261160", "261160"]


def test_filtro_descarta_classificacao_5(amostra_sinan):
    out = _filtrar_descartados(amostra_sinan, "classi_fin")
    assert out["classi_fin"].tolist() == ["10", "10", "3", None]


def test_filtro_descarta_classificacao_5_em_coluna_float():
    # Coluna com vazios é lida pelo pandas como float: o descartado chega como 5.0.
    df = pd.DataFrame({"classi_fin": [10.0, 5.0, None, 3.0]})
    out = _filtrar_descartados(df, "classi_fin")
    assert out.index.tolist() == [0, 2, 3]


def test_reagregar_grao_unico_e_ano_da_semana():
    out = pd.DataFrame({
        "bairro": ["A", "A", "A", "B"],
        "semana": [201602, 201602, 201603, 201601],
        "casos": [1, 2, 4, 7],
        "ano": [2016, 2016, 2016, 2016],
    })
    agg = _reagregar(out)
    assert list(agg.columns) == ["bairro", "semana", "casos", "ano"]
    assert not agg.duplicated(subset=["bairro", "semana"]).any()
    linha = agg[(agg["bairro"] == "A") & (agg["semana"] == 201602)].iloc[0]
    assert linha["casos"] == 3
    assert linha["ano"] == 2016


CABECALHO = "id_mn_resi;classi_fin;nm_bairro;id_bairro;sem_not;dt_notific"


def _escrever_cache(cache_dir, year, linhas):
    path = cache_dir / f"dengue_{year}.csv"
    path.write_text("\n".join([CABECALHO, *linhas]) + "\n", encoding="utf-8")


def test_fluxo_completo_com_cache_local(tmp_path, monkeypatch):
    """Mini-CSVs em cache para todos os anos: sem rede (conftest bloqueia requests)."""
    cache_dir, data_dir = tmp_path / "cache", tmp_path / "data"
    cache_dir.mkdir()
    data_dir.mkdir()
    (data_dir / "bairros_lookup.json").write_text(
        json.dumps([{"nome": "Boa Viagem"}, {"nome": "Várzea"}]), encoding="utf-8")
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)

    _escrever_cache(cache_dir, 2016, [
        "261160;1;BOA VIAGEM;1;201601;2016-01-05",
        # classificação vazia: a coluna vira float e o descartado chega como 5.0
        "261160;;BOA VIAGEM;1;201601;2016-01-06",
        "261160;5;BOA VIAGEM;1;201601;2016-01-07",
        "260005;1;BOA VIAGEM;1;201601;2016-01-08",
        # notificação no arquivo de 2016 com semana de 2017
        "261160;1;VARZEA;2;201701;2017-01-02",
    ])
    _escrever_cache(cache_dir, 2017, ["261160;1;VARZEA;2;201701;2017-01-03"])
    # 2018-2022 com 1 caso e 2023-2025 com 2: o p75 da série fica em 2.
    for year in build.ANOS[2:]:
        casos = 2 if year >= 2023 else 1
        _escrever_cache(cache_dir, year, [f"261160;1;BOA VIAGEM;1;{year}10;{year}-03-01"] * casos)

    build.main()

    csv = pd.read_csv(data_dir / "sinan_bairro_se_2016_2025.csv")
    report = json.loads((data_dir / "sinan_bairro_se_report.json").read_text(encoding="utf-8"))

    assert not csv.duplicated(subset=["bairro", "semana"]).any()
    linhas = {(r.bairro, r.semana): (r.casos, r.ano) for r in csv.itertuples()}
    assert linhas[("Boa Viagem", 201601)] == (2, 2016)
    assert linhas[("Várzea", 201701)] == (2, 2017)

    # Por arquivo, 2016 tem 3 casos e 2017 tem 1; o report usa o CSV reagregado
    # (2 e 2), o que põe 2017 entre os anos epidêmicos.
    assert report["anos"]["2016"]["casos_agregados"] == 3
    assert report["anos"]["2017"]["casos_agregados"] == 1
    esperado = {str(y): (2 if y >= 2023 else 1) for y in build.ANOS} | {"2016": 2, "2017": 2}
    assert report["totais_por_ano"] == esperado
    assert report["threshold_casos"] == 2.0
    assert report["epidemic_years"] == [2016, 2017, 2023, 2024, 2025]
