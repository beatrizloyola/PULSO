"""Gera os hotspots espaciais (Moran global + LISA) por temporada — US20.

Uso:
    cd backend
    python scripts/gerar_hotspots.py
    python scripts/gerar_hotspots.py --temporadas 2024,2025 --permutacoes 999
    python scripts/gerar_hotspots.py --fonte painel --temporadas 2024-2025

Fonte primária: série US04 2016–2025 (casos não descartados). O painel US14
entra como ``--fonte painel`` para a sensibilidade de fonte.

Saídas (em ``backend/notebooks/saidas`` por padrão):
    us20_lisa_<temporada>.geojson
    us20_lisa_bairro_temporada.csv
    us20_moran_global.csv
    us20_contagem_lisa.csv
    us20_hh_por_ds.csv
    us20_meta.json
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "notebooks"))

import _comum  # noqa: E402
import hotspots  # noqa: E402

SAIDA_PADRAO = _comum.SAIDAS_DIR
COLUNAS_SAIDA = [
    "temporada", "bairro_id", "key", "bairro", "ds", "casos", "valor",
    "p_sim", "p_bh", "quadrante", "I_local", "cluster", "cluster_bh",
    "hotspot", "hotspot_bh",
]
CATEGORIAS_LISA = ["HH", "LH", "LL", "HL", "ns"]


def _versao(pacote: str) -> str | None:
    try:
        return version(pacote)
    except PackageNotFoundError:
        return None


def _git_sha() -> str | None:
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return resultado.stdout.strip() or None


def _parse_temporadas(texto: str) -> list[int]:
    """Aceita ``2024``, ``2024,2025`` ou ``2016-2025``."""
    temporadas: list[int] = []
    for parte in str(texto).split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            inicio, fim = parte.split("-", 1)
            try:
                inicio_int, fim_int = int(inicio), int(fim)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(
                    f"temporada inválida: {parte!r}"
                ) from exc
            if fim_int < inicio_int:
                raise argparse.ArgumentTypeError(
                    f"intervalo de temporadas invertido: {parte!r}"
                )
            temporadas.extend(range(inicio_int, fim_int + 1))
        else:
            try:
                temporadas.append(int(parte))
            except ValueError as exc:
                raise argparse.ArgumentTypeError(
                    f"temporada inválida: {parte!r}"
                ) from exc
    if not temporadas:
        raise argparse.ArgumentTypeError("informe ao menos uma temporada")
    return sorted(set(temporadas))


def _carregar_geo():
    geo = _comum.carregar_geo().copy()
    lookup = _comum.carregar_lookup()[["key", "id", "bairro", "ds", "rpa"]]
    lookup = lookup.rename(columns={"id": "bairro_id"})
    geo = geo.merge(lookup, on="key", how="left")

    if geo["bairro_id"].isna().any():
        faltantes = sorted(geo.loc[geo["bairro_id"].isna(), "key"].tolist())
        raise ValueError(f"bairros sem lookup canônico: {faltantes}")
    if len(geo) != 94:
        raise ValueError(f"esperados 94 bairros; encontrados {len(geo)}")
    if geo.crs is None:
        geo = geo.set_crs(4326)
    return geo


def _carregar_casos(fonte: str):
    if fonte == "historico":
        casos = hotspots.carregar_casos_historicos()
        arquivo = _comum.DATA_DIR / "sinan_bairro_se_2016_2025.csv"
    elif fonte == "painel":
        casos = hotspots.carregar_casos_painel()
        arquivo = _comum.PAINEL_BAIRRO
    else:
        raise ValueError(f"fonte inválida: {fonte!r}")

    attrs = dict(casos.attrs)
    completos = hotspots.completar_temporadas(casos)
    return completos, attrs, arquivo


def _preparar_saida(resultado, temporada: int) -> pd.DataFrame:
    resultado = resultado.copy()
    resultado["temporada"] = int(temporada)

    faltando = [c for c in COLUNAS_SAIDA if c not in resultado.columns]
    if faltando:
        raise ValueError(f"resultado do LISA sem colunas: {faltando}")

    saida = resultado[COLUNAS_SAIDA + ["geometry"]].copy()
    saida["bairro"] = saida["bairro"].astype(str).str.title()

    for coluna in ["bairro_id", "key", "bairro", "ds"]:
        if saida[coluna].isna().any():
            raise ValueError(f"saída tem {coluna} nulo")
    if saida["key"].duplicated().any():
        raise ValueError("saída tem bairro duplicado")
    if not saida["cluster"].isin(CATEGORIAS_LISA).all():
        raise ValueError("saída tem cluster inválido")
    if not saida["cluster_bh"].isin(CATEGORIAS_LISA).all():
        raise ValueError("saída tem cluster_bh inválido")

    return saida.sort_values("key").reset_index(drop=True)


def _exportar_geojson(saida: pd.DataFrame, caminho: Path, simplificar_m: float) -> None:
    exportar = saida.to_crs(31985)
    if simplificar_m > 0:
        # GeoDataFrame.simplify devolve GeoSeries; atribuir à coluna preserva
        # as propriedades do bairro no GeoJSON.
        exportar["geometry"] = exportar.geometry.simplify(
            simplificar_m, preserve_topology=True
        )
    exportar = exportar.to_crs(4326)

    if exportar.geometry.is_empty.any():
        raise ValueError(f"simplificação gerou geometria vazia em {caminho.name}")
    if caminho.exists():
        caminho.unlink()
    exportar.to_file(caminho, driver="GeoJSON")


def _linha_moran(resumo: dict, temporada: int, fonte: str) -> dict:
    moran = resumo["moran"]
    pesos = resumo["pesos"]
    return {
        "temporada": int(temporada),
        "fonte": fonte,
        "esquema": pesos["esquema_usado"],
        "k": pesos["k"],
        "n_bairros": resumo["n_bairros"],
        "casos_total": resumo["casos_total"],
        "bairros_com_casos": resumo["bairros_com_casos"],
        "I": moran["I"],
        "EI": moran["EI"],
        "z_perm": moran["z_perm"],
        "p_perm": moran["p_perm"],
        "z_normal": moran["z_normal"],
        "p_normal": moran["p_normal"],
        "permutacoes": moran["permutacoes"],
        "seed": moran["seed"],
        "fallback_por_ilhas": pesos["fallback_por_ilhas"],
    }


def _linhas_contagem(resumo: dict, temporada: int) -> list[dict]:
    return [
        {
            "temporada": int(temporada),
            "categoria": categoria,
            "sem_bh": resumo["contagem"][categoria],
            "com_bh": resumo["contagem_bh"][categoria],
        }
        for categoria in CATEGORIAS_LISA
    ]


def _linhas_hh_por_ds(saida: pd.DataFrame, temporada: int) -> list[dict]:
    hh = saida.loc[saida["cluster"] == "HH", "ds"].value_counts()
    hh_bh = saida.loc[saida["cluster_bh"] == "HH", "ds"].value_counts()
    return [
        {
            "temporada": int(temporada),
            "ds": ds,
            "hh_sem_bh": int(hh.get(ds, 0)),
            "hh_com_bh": int(hh_bh.get(ds, 0)),
        }
        for ds in [str(i) for i in range(1, 9)]
    ]


def _linha_pesos(resumo: dict, temporada: int, esquema_solicitado: str) -> dict:
    pesos = resumo["pesos"]
    return {
        "temporada": int(temporada),
        "esquema_solicitado": esquema_solicitado,
        "esquema_usado": pesos["esquema_usado"],
        "k": pesos["k"] if pesos["k"] is not None else "-",
        "I": resumo["moran"]["I"],
        "p_perm": resumo["moran"]["p_perm"],
        "HH": resumo["contagem"]["HH"],
        "HH_bh": resumo["contagem_bh"]["HH"],
        "LL": resumo["contagem"]["LL"],
        "LL_bh": resumo["contagem_bh"]["LL"],
        "casos_total": resumo["casos_total"],
        "fallback_por_ilhas": pesos["fallback_por_ilhas"],
    }


def _sensibilidade_pesos(
    geo,
    casos: pd.DataFrame,
    temporadas: list[int],
    resumos: dict[int, dict],
    args: argparse.Namespace,
) -> pd.DataFrame:
    """Compara o esquema principal com o outro (Queen ↔ KNN k=4)."""
    esquema_alternativo = "knn" if args.esquema == "queen" else "queen"
    k_alternativo = 4 if esquema_alternativo == "knn" else args.k

    linhas = [_linha_pesos(resumos[t], t, args.esquema) for t in temporadas]
    for temporada in temporadas:
        casos_t = casos.loc[casos["temporada"] == temporada, ["key", "casos"]]
        _, resumo = hotspots.calcular_temporada(
            geo,
            casos_t,
            esquema=esquema_alternativo,
            k=k_alternativo,
            permutacoes=args.permutacoes,
            seed=args.seed,
            alpha=args.alpha,
        )
        linhas.append(_linha_pesos(resumo, temporada, esquema_alternativo))

    return pd.DataFrame(linhas).sort_values(
        ["temporada", "esquema_solicitado"]
    ).reset_index(drop=True)


def _sensibilidade_fonte(
    geo,
    casos_atual: pd.DataFrame,
    fonte_atual: str,
    casos_outra: pd.DataFrame,
    fonte_outra: str,
    temporadas: list[int],
    args: argparse.Namespace,
) -> pd.DataFrame:
    """Compara as fontes (US04 × painel) nas temporadas em que ambas existem."""
    sobrepostas = sorted(
        set(temporadas) & set(int(t) for t in casos_outra["temporada"].unique())
    )
    if not sobrepostas:
        return pd.DataFrame()

    linhas = []
    for temporada in sobrepostas:
        for fonte, casos in [(fonte_atual, casos_atual), (fonte_outra, casos_outra)]:
            casos_t = casos.loc[casos["temporada"] == temporada, ["key", "casos"]]
            _, resumo = hotspots.calcular_temporada(
                geo,
                casos_t,
                esquema=args.esquema,
                k=args.k,
                permutacoes=args.permutacoes,
                seed=args.seed,
                alpha=args.alpha,
            )
            linhas.append({
                "temporada": int(temporada),
                "fonte": fonte,
                "esquema": resumo["pesos"]["esquema_usado"],
                "casos_total": resumo["casos_total"],
                "I": resumo["moran"]["I"],
                "p_perm": resumo["moran"]["p_perm"],
                "HH": resumo["contagem"]["HH"],
                "HH_bh": resumo["contagem_bh"]["HH"],
                "LL": resumo["contagem"]["LL"],
                "LL_bh": resumo["contagem_bh"]["LL"],
            })
    return pd.DataFrame(linhas).sort_values(["temporada", "fonte"]).reset_index(drop=True)


def _tabela_persistencia(lisa_df: pd.DataFrame) -> pd.DataFrame:
    """Conta em quantas temporadas cada bairro foi HH (sem e com BH)."""
    persistencia = (
        lisa_df.groupby(["bairro_id", "key", "bairro", "ds"], as_index=False)
        .agg(
            n_temporadas=("temporada", "nunique"),
            n_temporadas_hh=("hotspot", "sum"),
            n_temporadas_hh_bh=("hotspot_bh", "sum"),
            casos_total=("casos", "sum"),
        )
    )
    persistencia["n_temporadas_hh"] = persistencia["n_temporadas_hh"].astype(int)
    persistencia["n_temporadas_hh_bh"] = persistencia["n_temporadas_hh_bh"].astype(int)

    def _anos_em_que(df: pd.DataFrame, coluna: str, nome: str) -> pd.Series:
        return (
            df.loc[df[coluna], ["key", "temporada"]]
            .drop_duplicates()
            .sort_values(["key", "temporada"])
            .groupby("key")["temporada"]
            .apply(lambda s: " ".join(str(int(t)) for t in s))
            .rename(nome)
        )

    hh = _anos_em_que(lisa_df, "hotspot", "temporadas_hh")
    hh_bh = _anos_em_que(lisa_df, "hotspot_bh", "temporadas_hh_bh")
    persistencia = persistencia.merge(hh, on="key", how="left")
    persistencia = persistencia.merge(hh_bh, on="key", how="left")
    persistencia["temporadas_hh"] = persistencia["temporadas_hh"].fillna("-")
    persistencia["temporadas_hh_bh"] = persistencia["temporadas_hh_bh"].fillna("-")

    colunas = [
        "bairro_id", "key", "bairro", "ds", "n_temporadas",
        "n_temporadas_hh", "temporadas_hh",
        "n_temporadas_hh_bh", "temporadas_hh_bh", "casos_total",
    ]
    return (
        persistencia[colunas]
        .sort_values(
            ["n_temporadas_hh", "n_temporadas_hh_bh", "bairro"],
            ascending=[False, False, True],
        )
        .reset_index(drop=True)
    )


def _plot_moran_por_temporada(
    moran_df: pd.DataFrame,
    contagem_df: pd.DataFrame,
    caminho: Path,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    temporadas = moran_df["temporada"].astype(int).tolist()
    hh = (
        contagem_df.loc[contagem_df["categoria"] == "HH"]
        .set_index("temporada")
        .reindex(temporadas)
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax1.plot(temporadas, moran_df["I"], marker="o", color="#c0392b")
    ax1.axhline(0, color="gray", linewidth=0.8)
    ax1.axhline(
        float(moran_df["EI"].iloc[0]), color="black", linestyle="--",
        linewidth=1, label="Esperado (EI)",
    )
    for temporada, valor, p in zip(temporadas, moran_df["I"], moran_df["p_perm"]):
        ax1.annotate(
            f"p={p:.3f}", (temporada, valor), textcoords="offset points",
            xytext=(0, 8), ha="center", fontsize=7,
        )
    ax1.set_ylabel("Moran's I")
    ax1.set_title("US20 · Moran global por temporada")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.2)

    ax2.bar(
        [t - 0.2 for t in temporadas], hh["sem_bh"],
        width=0.4, label="HH (p_sim < alpha)", color="#d73027",
    )
    ax2.bar(
        [t + 0.2 for t in temporadas], hh["com_bh"],
        width=0.4, label="HH (BH 5%)", color="#f46d43",
    )
    ax2.set_ylabel("Nº de bairros HH")
    ax2.set_xlabel("Temporada")
    ax2.set_xticks(temporadas)
    ax2.legend(fontsize=8)
    ax2.grid(axis="y", alpha=0.2)

    fig.tight_layout()
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_mapas_temporadas(
    saidas_geo: dict[int, pd.DataFrame],
    resumos: dict[int, dict],
    caminho: Path,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    temporadas = sorted(saidas_geo)
    n = len(temporadas)
    ncols = min(5, n)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 4 * nrows), squeeze=False)
    distritos = _comum.carregar_distritos().to_crs(4326)

    for ax, temporada in zip(axes.ravel(), temporadas):
        geo = saidas_geo[temporada]
        for categoria in ["ns", "HL", "LH", "LL", "HH"]:
            parte = geo[geo["cluster"] == categoria]
            if not parte.empty:
                parte.plot(
                    ax=ax, color=_comum.CORES_LISA[categoria],
                    edgecolor="white", linewidth=0.2,
                )
        distritos.boundary.plot(ax=ax, color="black", linewidth=0.6)
        resumo = resumos[temporada]
        ax.set_title(
            f"{temporada} · I={resumo['moran']['I']:.3f} · "
            f"p={resumo['moran']['p_perm']:.3f} · HH={resumo['contagem']['HH']}",
            fontsize=9,
        )
        ax.axis("off")

    for ax in axes.ravel()[n:]:
        ax.axis("off")

    handles = [
        Patch(facecolor=_comum.CORES_LISA[c], label=_comum.ROTULOS_LISA[c])
        for c in ["HH", "LL", "LH", "HL", "ns"]
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=8, frameon=False)
    fig.suptitle(
        "US20 · LISA por temporada (classificação primária, p_sim < alpha)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_persistencia(geo, persistencia: pd.DataFrame, caminho: Path) -> None:
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mapa = geo.copy()
    mapa = mapa.merge(
        persistencia[["key", "n_temporadas_hh", "n_temporadas_hh_bh"]],
        on="key",
        how="left",
    )
    for coluna in ["n_temporadas_hh", "n_temporadas_hh_bh"]:
        mapa[coluna] = mapa[coluna].fillna(0).astype(int)
    mapa = gpd.GeoDataFrame(mapa, geometry="geometry", crs=geo.crs)
    distritos = _comum.carregar_distritos().to_crs(4326)
    vmax = max(1, int(mapa["n_temporadas_hh"].max()), int(mapa["n_temporadas_hh_bh"].max()))

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    paineis = [
        ("n_temporadas_hh", "HH (p_sim < alpha)"),
        ("n_temporadas_hh_bh", "HH (BH 5%)"),
    ]
    for ax, (coluna, titulo) in zip(axes, paineis):
        mapa.plot(
            column=coluna,
            ax=ax,
            cmap="Reds",
            vmin=0,
            vmax=vmax,
            edgecolor="white",
            linewidth=0.2,
            legend=True,
            legend_kwds={"label": "nº de temporadas", "shrink": 0.6},
            missing_kwds={"color": "#eeeeee"},
        )
        distritos.boundary.plot(ax=ax, color="black", linewidth=0.6)
        ax.set_title(titulo)
        ax.axis("off")

    fig.suptitle("US20 · Persistência de hotspots", fontsize=12)
    fig.tight_layout()
    fig.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _caminho_fonte(caminho: Path) -> str:
    try:
        return str(caminho.relative_to(BACKEND_DIR))
    except ValueError:
        return str(caminho)


def _montar_meta(
    *,
    fonte: str,
    arquivo_fonte: Path,
    attrs: dict,
    temporadas: list[int],
    n_bairros: int,
    cobertura: dict,
    pesos: dict,
    args: argparse.Namespace,
) -> dict:
    limitacoes = [
        "Contagem de casos, não incidência: a população (US08) ainda é placeholder.",
        "Temporada = ano civil da SE; a fronteira epidêmica do SP-3 fica pendente.",
        "A série US04 usa a semana de notificação; a decisão US01 (DT_SIN_PRI × DT_NOTIFIC) está pendente.",
        "cluster usa p_sim < alpha; cluster_bh é a sensibilidade BH-FDR.",
        "Resultado ecológico por bairro; não vale para indivíduos (MAUP).",
    ]
    if fonte == "painel":
        limitacoes.append(
            "O painel US14 inclui notificações descartadas; use como sensibilidade, não como fonte primária."
        )

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "fonte": fonte,
        "fonte_descricao": (
            hotspots.FONTE_HISTORICA if fonte == "historico" else hotspots.FONTE_PAINEL
        ),
        "arquivo_fonte": _caminho_fonte(arquivo_fonte),
        "fonte_bruta": attrs,
        "temporadas": temporadas,
        "n_bairros": int(n_bairros),
        "variavel": "casos notificados por bairro (contagem; US08 pendente)",
        "populacao": "placeholder 1 habitante/bairro (US08 pendente)",
        "pesos": pesos,
        "permutacoes": int(args.permutacoes),
        "seed": int(args.seed),
        "alpha": float(args.alpha),
        "classificacao": "cluster: p_sim < alpha; cluster_bh: BH-FDR alpha",
        "geometria": {
            "fonte": "bairros_esig.geojson",
            "crs_saida": "EPSG:4326",
            "simplificacao_m": float(args.simplificar),
        },
        "cobertura": cobertura,
        "bibliotecas": {
            pacote: _versao(pacote)
            for pacote in ["pandas", "numpy", "geopandas", "libpysal", "esda"]
        },
        "limitacoes": limitacoes,
        "saidas": sorted(
            p.name for p in Path(args.saida).glob("us20_*") if p.name != "us20_meta.json"
        ) + ["us20_meta.json"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera Moran global e LISA por temporada (US20)."
    )
    parser.add_argument(
        "--fonte",
        choices=["historico", "painel"],
        default="historico",
        help="Fonte dos casos (default: historico/US04).",
    )
    parser.add_argument(
        "--temporadas",
        type=_parse_temporadas,
        default=None,
        help="Ex.: 2024, 2024,2025 ou 2016-2025 (default: todas da fonte).",
    )
    parser.add_argument(
        "--esquema",
        choices=["queen", "knn"],
        default="queen",
        help="Matriz de pesos espaciais (default: queen).",
    )
    parser.add_argument("--k", type=int, default=4, help="Vizinhos do KNN (default: 4).")
    parser.add_argument(
        "--permutacoes",
        type=int,
        default=999,
        help="Permutações de Moran/LISA (default: 999).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed do numpy (default: 42).")
    parser.add_argument(
        "--alpha", type=float, default=0.05, help="Nível de significância (default: 0.05)."
    )
    parser.add_argument(
        "--simplificar",
        type=float,
        default=10.0,
        help="Tolerância de simplificação em metros no GeoJSON (0 desliga; default: 10).",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=SAIDA_PADRAO,
        help=f"Diretório de saída (default: {SAIDA_PADRAO}).",
    )
    args = parser.parse_args(argv)

    if args.permutacoes < 1:
        parser.error("--permutacoes deve ser >= 1")
    if args.k < 1:
        parser.error("--k deve ser >= 1")
    if not 0 < args.alpha < 1:
        parser.error("--alpha deve estar entre 0 e 1")
    if args.simplificar < 0:
        parser.error("--simplificar deve ser >= 0")

    casos, attrs, arquivo = _carregar_casos(args.fonte)
    disponiveis = sorted(int(t) for t in casos["temporada"].unique())
    temporadas = args.temporadas or disponiveis
    faltando = sorted(set(temporadas) - set(disponiveis))
    if faltando:
        parser.error(
            f"temporadas sem dados na fonte {args.fonte!r}: {faltando} "
            f"(disponíveis: {disponiveis})"
        )
    casos = casos[casos["temporada"].isin(temporadas)].copy()

    geo = _carregar_geo()
    saida_dir = Path(args.saida)
    saida_dir.mkdir(parents=True, exist_ok=True)

    lisa_rows: list[pd.DataFrame] = []
    moran_rows: list[dict] = []
    contagem_rows: list[dict] = []
    ds_rows: list[dict] = []
    resumos: dict[int, dict] = {}
    saidas_geo: dict[int, pd.DataFrame] = {}
    pesos_usados: dict | None = None

    for temporada in temporadas:
        casos_t = casos.loc[casos["temporada"] == temporada, ["key", "casos"]]
        resultado, resumo = hotspots.calcular_temporada(
            geo,
            casos_t,
            esquema=args.esquema,
            k=args.k,
            permutacoes=args.permutacoes,
            seed=args.seed,
            alpha=args.alpha,
        )
        saida = _preparar_saida(resultado, temporada)
        _exportar_geojson(saida, saida_dir / f"us20_lisa_{temporada}.geojson", args.simplificar)

        lisa_rows.append(saida.drop(columns="geometry"))
        moran_rows.append(_linha_moran(resumo, temporada, args.fonte))
        contagem_rows.extend(_linhas_contagem(resumo, temporada))
        ds_rows.extend(_linhas_hh_por_ds(saida, temporada))
        resumos[temporada] = resumo
        saidas_geo[temporada] = saida
        pesos_usados = pesos_usados or resumo["pesos"]

        print(
            f"[{temporada}] I={resumo['moran']['I']:.4f} "
            f"p={resumo['moran']['p_perm']:.4f} "
            f"HH={resumo['contagem']['HH']} (BH={resumo['contagem_bh']['HH']}) "
            f"-> us20_lisa_{temporada}.geojson"
        )

    lisa_df = pd.concat(lisa_rows, ignore_index=True)
    moran_df = pd.DataFrame(moran_rows)
    contagem_df = pd.DataFrame(contagem_rows)
    ds_df = pd.DataFrame(ds_rows)

    lisa_df.to_csv(saida_dir / "us20_lisa_bairro_temporada.csv", index=False)
    moran_df.to_csv(saida_dir / "us20_moran_global.csv", index=False)
    contagem_df.to_csv(saida_dir / "us20_contagem_lisa.csv", index=False)
    ds_df.to_csv(saida_dir / "us20_hh_por_ds.csv", index=False)

    persistencia = _tabela_persistencia(lisa_df)
    persistencia.to_csv(saida_dir / "us20_hotspots_persistentes.csv", index=False)

    pesos_df = _sensibilidade_pesos(geo, casos, temporadas, resumos, args)
    pesos_df.to_csv(saida_dir / "us20_sensibilidade_pesos.csv", index=False)

    outra_fonte = "painel" if args.fonte == "historico" else "historico"
    try:
        casos_outra, _, _ = _carregar_casos(outra_fonte)
    except FileNotFoundError as exc:
        print(f"[aviso] sensibilidade de fonte pulada: {exc}")
        casos_outra = None

    if casos_outra is not None:
        fonte_df = _sensibilidade_fonte(
            geo,
            casos,
            args.fonte,
            casos_outra,
            outra_fonte,
            temporadas,
            args,
        )
        if not fonte_df.empty:
            fonte_df.to_csv(saida_dir / "us20_sensibilidade_fonte.csv", index=False)
        else:
            print("[aviso] sem temporadas sobrepostas para sensibilidade de fonte")

    _plot_moran_por_temporada(
        moran_df, contagem_df, saida_dir / "us20_moran_por_temporada.png"
    )
    _plot_mapas_temporadas(
        saidas_geo, resumos, saida_dir / "us20_mapa_lisa_temporadas.png"
    )
    _plot_persistencia(
        geo, persistencia, saida_dir / "us20_mapa_persistencia.png"
    )

    meta = _montar_meta(
        fonte=args.fonte,
        arquivo_fonte=arquivo,
        attrs=attrs,
        temporadas=temporadas,
        n_bairros=len(geo),
        cobertura=hotspots.resumo_cobertura(casos),
        pesos=pesos_usados or {},
        args=args,
    )
    (saida_dir / "us20_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    print(
        f"[gerar_hotspots] fonte={args.fonte} temporadas={temporadas} "
        f"bairros={len(geo)} permutacoes={args.permutacoes} seed={args.seed}"
    )
    print(f"[gerar_hotspots] saídas em {saida_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
