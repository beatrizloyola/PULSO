"""Utilidades compartilhadas pelos spikes SP-2, SP-4 e SP-5.

Os notebooks leem o painel versionado (US14) em backend/app/data/painel/.
Nada aqui altera o pipeline de produção nem o modelo servido pela API.

Sobre população (opção A do time):
    carregar_populacao() devolve 1 habitante por bairro enquanto a US08
    (Censo 2022) não chega. O offset do GLM vira 0 e a "incidência" do LISA
    fica na escala de casos. Quando a tabela oficial existir, troque APENAS
    esta função: as fórmulas e os notebooks continuam iguais.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "app" / "data"
PAINEL_BAIRRO = DATA_DIR / "painel" / "painel_bairro_se.csv"
PAINEL_DS = DATA_DIR / "painel" / "painel_ds_se.csv"
BAIRROS_LOOKUP = DATA_DIR / "bairros_lookup.json"
BAIRROS_GEO = DATA_DIR / "bairros_esig.geojson"
DISTRITOS_GEO = DATA_DIR / "distritos_sanitarios_8d43533d.geojson"
SAIDAS_DIR = Path(__file__).resolve().parent / "saidas"

CORES_DS = {
    "1": "#4e79a7", "2": "#f28e2b", "3": "#e15759", "4": "#76b7b2",
    "5": "#59a14f", "6": "#edc948", "7": "#b07aa1", "8": "#9c755f",
}
CORES_LISA = {
    "HH": "#d73027", "LL": "#4575b4", "LH": "#fdae61",
    "HL": "#abd9e9", "ns": "#e6e6e6",
}
ROTULOS_LISA = {
    "HH": "Alto-Alto (hotspot)", "LL": "Baixo-Baixo (coldspot)",
    "LH": "Baixo-Alto (outlier)", "HL": "Alto-Baixo (outlier)",
    "ns": "Não significativo",
}


def normalizar(valor) -> str:
    """Chave de join tolerante a acento/caixa, igual à usada no painel."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(valor).strip().upper())
        if unicodedata.category(c) != "Mn"
    )


def carregar_painel(anos: list[int] | None = None) -> pd.DataFrame:
    """Painel bairro x SE (US14). Falha cedo se o comando não foi rodado."""
    if not PAINEL_BAIRRO.exists():
        raise FileNotFoundError(
            f"{PAINEL_BAIRRO} não existe. Rode antes:\n"
            "    cd backend && python scripts/gerar_painel.py"
        )
    df = pd.read_csv(PAINEL_BAIRRO)
    if anos:
        df = df[df["semana"].floordiv(100).isin(anos)].copy()
    return df


def carregar_lookup() -> pd.DataFrame:
    """Cadastro canônico dos 94 bairros (DS, RPA, scores e ZEIS)."""
    df = pd.DataFrame(json.loads(BAIRROS_LOOKUP.read_text(encoding="utf-8")))
    df = df.rename(columns={"nome": "bairro"})
    df["key"] = df["bairro"].map(normalizar)
    return df


def carregar_geo() -> "gpd.GeoDataFrame":  # noqa: F821 - import tardio
    """Polígonos dos 94 bairros + área em km² (SIRGAS 2000 / UTM 25S)."""
    import geopandas as gpd

    gdf = gpd.read_file(BAIRROS_GEO)
    gdf["key"] = gdf["EBAIRRNOME"].map(normalizar)
    gdf["area_km2"] = gdf.to_crs(31985).area / 1e6
    return gdf


def carregar_distritos() -> "gpd.GeoDataFrame":  # noqa: F821
    import geopandas as gpd

    ds = gpd.read_file(DISTRITOS_GEO)
    ds["ds"] = ds["cdistscodi"].astype(int).astype(str)
    return ds


def carregar_populacao() -> pd.DataFrame:
    """População por bairro — placeholder opção A (US08 pendente).

    Retorna uma linha por bairro com `populacao = 1.0` e `fonte` explícita.
    Substituir por:
        pop = pd.read_csv(CAMINHO_US08)  # bairro/populacao
        ...
    """
    lookup = carregar_lookup()[["key", "bairro"]].copy()
    lookup["populacao"] = 1.0
    lookup["fonte"] = "placeholder_opcao_A (US08 pendente)"
    return lookup


def salvar_figura(fig, nome: str, dpi: int = 150) -> Path:
    """Salva em backend/notebooks/saidas/ e devolve o caminho."""
    SAIDAS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = SAIDAS_DIR / nome
    fig.savefig(caminho, dpi=dpi, bbox_inches="tight")
    return caminho
