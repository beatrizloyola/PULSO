import pandas as pd
import pytest

from app import config
from app.services import forecast_features as ff
from app.shared.painel_schema import (
    SchemaInvalidoError,
    validar_painel_bairro,
    validar_painel_ds,
)


@pytest.fixture(scope="module")
def panel_cru():
    return ff.build_panel(config.FORECAST_ANOS)


@pytest.fixture(scope="module")
def painel_bairro(panel_cru):
    return ff.add_features(panel_cru)


@pytest.fixture(scope="module")
def painel_ds(panel_cru):
    return ff.add_features_ds(ff.build_panel_ds(panel_cru))


def test_painel_bairro_valido(painel_bairro):
    validar_painel_bairro(painel_bairro)  # não levanta


def test_painel_ds_valido(painel_ds):
    validar_painel_ds(painel_ds)  # não levanta
    assert set(painel_ds["ds"].unique()) == {str(i) for i in range(1, 9)}


def test_painel_ds_soma_casos_dos_bairros(painel_bairro, painel_ds):
    # Semana com cobertura garantida (nem a primeira nem a última do histórico).
    semanas_cobertas = sorted(painel_bairro.dropna(subset=["casos"])["semana"].unique())
    semana = semanas_cobertas[len(semanas_cobertas) // 2]
    for ds in painel_ds["ds"].unique():
        esperado = painel_bairro[(painel_bairro["ds"] == ds) & (painel_bairro["semana"] == semana)]["casos"].sum(min_count=1)
        obtido = painel_ds[(painel_ds["ds"] == ds) & (painel_ds["semana"] == semana)]["casos"].iloc[0]
        assert obtido == pytest.approx(esperado)


def test_validacao_falha_com_chave_duplicada():
    df = pd.DataFrame({
        "bairro_id": ["b1", "b1"], "bairro": ["X", "X"], "ds": ["1", "1"], "rpa": ["RPA 1", "RPA 1"],
        "semana": [202501, 202501], "casos": [1, 2], "chuva_mm": [0, 0], "temp_media": [25, 25],
    })
    with pytest.raises(SchemaInvalidoError, match="não é única"):
        validar_painel_bairro(df)


def test_validacao_falha_com_valor_fora_da_faixa():
    df = pd.DataFrame({
        "bairro_id": ["b1"], "bairro": ["X"], "ds": ["1"], "rpa": ["RPA 1"],
        "semana": [202501], "casos": [-5], "chuva_mm": [0], "temp_media": [25],
    })
    with pytest.raises(SchemaInvalidoError, match="casos"):
        validar_painel_bairro(df)


def test_validacao_falha_com_coluna_faltando():
    df = pd.DataFrame({"bairro_id": ["b1"], "semana": [202501]})
    with pytest.raises(SchemaInvalidoError, match="colunas obrigatórias ausentes"):
        validar_painel_bairro(df)


def test_features_bairro_nao_usam_dado_futuro():
    """Nenhuma feature na semana t pode mudar se dados de semanas > t mudarem."""
    panel = ff.build_panel(config.FORECAST_ANOS)
    semanas = sorted(panel["semana"].unique())
    corte = semanas[len(semanas) // 2]

    completo = ff.add_features(panel)
    truncado = ff.add_features(panel[panel["semana"] <= corte].copy())

    a = (completo[completo["semana"] <= corte]
         .sort_values(["bairro", "semana"]).reset_index(drop=True)[ff.FEATURES])
    b = truncado.sort_values(["bairro", "semana"]).reset_index(drop=True)[ff.FEATURES]
    pd.testing.assert_frame_equal(a, b)


def test_features_ds_nao_usam_dado_futuro():
    panel = ff.build_panel(config.FORECAST_ANOS)
    semanas = sorted(panel["semana"].unique())
    corte = semanas[len(semanas) // 2]

    completo = ff.add_features_ds(ff.build_panel_ds(panel))
    truncado = ff.add_features_ds(ff.build_panel_ds(panel[panel["semana"] <= corte].copy()))

    cols = [c for c in completo.columns if c not in ("ds", "semana")]
    a = (completo[completo["semana"] <= corte]
         .sort_values(["ds", "semana"]).reset_index(drop=True)[cols])
    b = truncado.sort_values(["ds", "semana"]).reset_index(drop=True)[cols]
    pd.testing.assert_frame_equal(a, b)
