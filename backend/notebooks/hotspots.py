"""Camada de dados da US20 — hotspots espaciais (LISA) por temporada.

Este módulo concentra o carregamento e a preparação dos casos usados pelo
Moran global e pelo LISA. Ele não importa ``geopandas``/``libpysal``/``esda``
no topo de propósito: o CI de ML instala apenas ``requirements.txt`` e não
deve pagar o custo do stack geoespacial. As funções espaciais entram nas
próximas etapas, com imports tardios.

Fontes:

- **US04** (primária): ``sinan_bairro_se_2016_2025.csv``, casos notificados
  não descartados, 2016–2025, chave por nome de bairro.
- **US14** (sensibilidade): ``painel_bairro_se.csv``, todas as notificações,
  2024–2025, chave por bairro normalizado. O painel inclui descartados; por
  isso não é a fonte primária de hotspots.

Temporada: ano civil da semana epidemiológica (``YYYY // 100``). A fronteira
de temporada epidêmica do SP-3 fica para uma decisão posterior.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import _comum

FONTE_HISTORICA = "US04 SINAN 2016-2025 (casos não descartados)"
FONTE_PAINEL = "US14 painel bairro x SE 2024-2025 (todas as notificações)"

COLUNAS_CASOS = [
    "temporada", "key", "bairro_id", "bairro", "ds", "rpa", "casos", "fonte",
]
COLUNAS_BAIRRO = ["key", "bairro_id", "bairro", "ds", "rpa"]


def _bairros_lookup() -> pd.DataFrame:
    """Cadastro canônico dos 94 bairros, só com as colunas usadas na análise."""
    lookup = _comum.carregar_lookup()
    faltando = [c for c in ["key", "id", "bairro", "ds", "rpa"] if c not in lookup.columns]
    if faltando:
        raise ValueError(f"bairros_lookup.json sem colunas obrigatórias: {faltando}")

    bairros = (
        lookup[["key", "id", "bairro", "ds", "rpa"]]
        .rename(columns={"id": "bairro_id"})
        .copy()
    )
    bairros["bairro_id"] = bairros["bairro_id"].astype(str)
    bairros["ds"] = bairros["ds"].astype(str)
    bairros["rpa"] = bairros["rpa"].astype(str)

    if bairros["key"].duplicated().any():
        raise ValueError("bairros_lookup.json tem chave de bairro duplicada")
    if len(bairros) != 94:
        raise ValueError(f"bairros_lookup.json deve ter 94 bairros; tem {len(bairros)}")

    return bairros.sort_values("key").reset_index(drop=True)


def temporada_da_semana(semana) -> int:
    """Converte uma SE ``YYYYWW`` (ou ``YYYY-Www``) no ano civil da temporada.

    Exemplos: ``202401 -> 2024``, ``"2024-W20" -> 2024``.
    """
    texto = str(semana).strip().replace("-W", "")
    if len(texto) != 6 or not texto.isdigit():
        raise ValueError(f"Semana epidemiológica inválida: {semana!r} (esperado YYYYWW)")
    codigo = int(texto)
    semana_do_ano = codigo % 100
    if not 1 <= semana_do_ano <= 53:
        raise ValueError(f"Semana epidemiológica inválida: {semana!r} (semana fora de 1-53)")
    return codigo // 100


def _normalizar_casos(bruto: pd.DataFrame, fonte: str) -> pd.DataFrame:
    """Valida a tabela bruta e devolve bairro/temporada/casos prontos para uso.

    A normalização de nome é a mesma do painel (``_comum.normalizar``). Linhas
    cujo bairro não existe no cadastro canônico são descartadas; o total é
    exposto em ``attrs`` para o relatório de cobertura.
    """
    faltando = [c for c in ["bairro", "semana", "casos"] if c not in bruto.columns]
    if faltando:
        raise ValueError(f"fonte {fonte!r} sem colunas obrigatórias: {faltando}")

    df = bruto.copy()
    df["semana"] = pd.to_numeric(df["semana"], errors="coerce")
    df["casos"] = pd.to_numeric(df["casos"], errors="coerce")
    if df["semana"].isna().any():
        raise ValueError(f"fonte {fonte!r} tem semana ausente ou não numérica")
    if df["casos"].isna().any():
        raise ValueError(f"fonte {fonte!r} tem casos ausente ou não numérico")
    if (df["casos"] < 0).any():
        raise ValueError(f"fonte {fonte!r} tem casos negativos")

    df["temporada"] = [temporada_da_semana(s) for s in df["semana"].astype(int)]
    if "ano" in df.columns:
        ano = pd.to_numeric(df["ano"], errors="coerce")
        if ano.isna().any() or (ano.astype(int) != df["temporada"]).any():
            raise ValueError(f"coluna 'ano' de {fonte!r} não confere com a semana")

    df["key"] = df["bairro"].map(_comum.normalizar)
    bairros = _bairros_lookup()
    # O nome canônico vem do lookup; o nome de origem fica só para o relatório.
    mapeado = df.merge(bairros, on="key", how="inner", suffixes=("_origem", ""))
    descartado = df[~df["key"].isin(bairros["key"])]

    casos = (
        mapeado.groupby(["temporada", "key", "bairro_id", "bairro", "ds", "rpa"],
                        as_index=False)["casos"]
        .sum()
    )
    casos["casos"] = casos["casos"].astype(int)
    casos["fonte"] = fonte

    resultado = casos[COLUNAS_CASOS].sort_values(["temporada", "key"]).reset_index(drop=True)
    resultado.attrs["registros_brutos"] = int(len(df))
    resultado.attrs["casos_brutos"] = int(df["casos"].sum())
    resultado.attrs["registros_fora_lookup"] = int(len(descartado))
    resultado.attrs["casos_fora_lookup"] = int(descartado["casos"].sum())
    resultado.attrs["bairros_fora_lookup"] = sorted(descartado["bairro"].unique().tolist())
    return resultado


def carregar_casos_historicos(caminho: Path | str | None = None) -> pd.DataFrame:
    """Casos por bairro e temporada da série US04 (2016–2025).

    Retorna uma linha por ``(temporada, bairro)`` **apenas onde há casos**.
    Use :func:`completar_temporadas` para materializar os 94 bairros em todas
    as temporadas, com zero onde não houve notificação.
    """
    caminho = Path(caminho) if caminho is not None else (
        _comum.DATA_DIR / "sinan_bairro_se_2016_2025.csv"
    )
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho} não existe. Rode antes:\n"
            "    cd backend && python scripts/build_sinan_historico.py"
        )

    bruto = pd.read_csv(caminho)
    return _normalizar_casos(bruto, FONTE_HISTORICA)


def carregar_casos_painel(anos: list[int] | None = None) -> pd.DataFrame:
    """Casos por bairro e temporada do painel US14 (2024–2025).

    É a fonte de **sensibilidade**: o painel conta todas as notificações,
    inclusive descartadas, e por isso não é comparável à US04. Use apenas para
    quantificar a diferença em relação ao SP-4.
    """
    caminho = _comum.PAINEL_BAIRRO
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho} não existe. Rode antes:\n"
            "    cd backend && python scripts/gerar_painel.py"
        )

    bruto = pd.read_csv(caminho)
    faltando = [c for c in ["bairro_norm", "semana", "casos"] if c not in bruto.columns]
    if faltando:
        raise ValueError(f"painel bairro x SE sem colunas obrigatórias: {faltando}")

    bruto = bruto.copy()
    bruto["temporada"] = [temporada_da_semana(s) for s in bruto["semana"]]
    if anos is not None:
        bruto = bruto[bruto["temporada"].isin(anos)]
    if bruto.empty:
        raise ValueError(f"painel não tem dados para as temporadas {anos}")

    casos = (
        bruto.groupby(["temporada", "bairro_norm"], as_index=False)["casos"]
        .sum(min_count=1)
        .rename(columns={"bairro_norm": "key"})
    )
    if casos["casos"].isna().any():
        faltantes = casos.loc[casos["casos"].isna(), ["temporada", "key"]]
        raise ValueError(
            "painel sem cobertura de casos para: "
            + ", ".join(f"{r.temporada}/{r.key}" for r in faltantes.itertuples())
        )

    casos["casos"] = casos["casos"].astype(int)
    casos = casos.merge(_bairros_lookup(), on="key", how="left")
    if casos["bairro_id"].isna().any():
        faltantes = sorted(casos.loc[casos["bairro_id"].isna(), "key"].tolist())
        raise ValueError(f"painel tem bairros fora do lookup: {faltantes}")

    casos["fonte"] = FONTE_PAINEL
    resultado = casos[COLUNAS_CASOS].sort_values(["temporada", "key"]).reset_index(drop=True)
    resultado.attrs["registros_brutos"] = int(len(bruto))
    resultado.attrs["casos_brutos"] = int(bruto["casos"].sum())
    return resultado


def completar_temporadas(
    casos: pd.DataFrame,
    bairros: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Materializa a grade temporada × 94 bairros, com zero onde não há casos.

    Sem isso, um bairro sem notificação em uma temporada simplesmente some da
    tabela e o LISA perde a unidade espacial. Zero é um valor observado (não
    houve caso), não um dado faltante.
    """
    if casos.empty:
        raise ValueError("não há casos para completar")
    faltando = [c for c in ["temporada", "key", "casos", "fonte"] if c not in casos.columns]
    if faltando:
        raise ValueError(f"tabela de casos sem colunas obrigatórias: {faltando}")
    if casos.duplicated(["temporada", "key"]).any():
        raise ValueError("tabela de casos tem (temporada, bairro) duplicado")

    bairros_df = _bairros_lookup() if bairros is None else bairros
    faltando = [c for c in COLUNAS_BAIRRO if c not in bairros_df.columns]
    if faltando:
        raise ValueError(f"cadastro de bairros sem colunas obrigatórias: {faltando}")

    fontes = casos.groupby("temporada")["fonte"].nunique()
    if (fontes > 1).any():
        raise ValueError("cada temporada deve vir de uma única fonte")
    fonte_por_temporada = casos.groupby("temporada")["fonte"].first().to_dict()

    temporadas = sorted(int(t) for t in casos["temporada"].unique())
    grade = (
        bairros_df[COLUNAS_BAIRRO]
        .assign(_k=1)
        .merge(pd.DataFrame({"temporada": temporadas, "_k": 1}), on="_k")
        .drop(columns="_k")
    )
    completos = grade.merge(
        casos[["temporada", "key", "casos"]],
        on=["temporada", "key"],
        how="left",
    )
    completos["casos"] = completos["casos"].fillna(0).astype(int)
    completos["fonte"] = completos["temporada"].map(fonte_por_temporada)
    completos = completos[COLUNAS_CASOS].sort_values(["temporada", "key"])

    if completos.duplicated(["temporada", "key"]).any():
        raise ValueError("grade completada tem (temporada, bairro) duplicado")
    if completos["fonte"].isna().any():
        raise ValueError("grade completada tem temporada sem fonte")

    return completos.reset_index(drop=True)


def resumo_cobertura(casos: pd.DataFrame) -> dict:
    """Resumo serializável em JSON para o ``us20_meta.json`` e para o log do script."""
    if casos.empty:
        raise ValueError("não há casos para resumir")

    por_temporada = casos.groupby("temporada").agg(
        casos=("casos", "sum"),
        bairros_com_casos=("casos", lambda s: int((s > 0).sum())),
    )
    return {
        "temporadas": [int(t) for t in por_temporada.index],
        "n_bairros": int(casos["key"].nunique()),
        "n_linhas": int(len(casos)),
        "casos_por_temporada": {
            str(int(t)): int(row["casos"]) for t, row in por_temporada.iterrows()
        },
        "bairros_com_casos_por_temporada": {
            str(int(t)): int(row["bairros_com_casos"])
            for t, row in por_temporada.iterrows()
        },
    }
