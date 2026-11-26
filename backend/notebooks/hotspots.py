"""Camada de dados da US20 — hotspots espaciais (LISA) por temporada.

Este módulo concentra o carregamento, a preparação e a estatística espacial
usados pela US20. Ele não importa ``geopandas``/``libpysal``/``esda`` no topo
de propósito: o CI de ML instala apenas ``requirements.txt`` e não deve pagar
o custo do stack geoespacial. As funções espaciais fazem imports tardios.

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

import numpy as np
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

def construir_pesos(geo, esquema: str = "queen", k: int = 4) -> tuple[object, dict]:
    """Monta a matriz de pesos espaciais e devolve ``(w, metadados)``.

    ``queen`` é o esquema primário; se houver ilhas (bairro sem vizinho por
    contiguidade), cai para ``knn`` com ``k`` vizinhos e registra o fallback.
    A matriz é sempre linha-padronizada.
    """
    import libpysal
    from libpysal.weights import KNN, Queen

    esquema = str(esquema).strip().lower()
    if esquema not in {"queen", "knn"}:
        raise ValueError(f"esquema de pesos inválido: {esquema!r} (use 'queen' ou 'knn')")
    if not isinstance(k, int) or k < 1:
        raise ValueError("k deve ser um inteiro >= 1")
    if len(geo) < 2:
        raise ValueError("são necessários pelo menos 2 polígonos para montar os pesos")

    ilhas_queen = []
    fallback = False
    if esquema == "queen":
        w = Queen.from_dataframe(geo, use_index=False)
        ilhas_queen = [int(i) for i in w.islands]
        if ilhas_queen:
            fallback = True
            if k >= len(geo):
                raise ValueError(f"k={k} não pode ser >= n={len(geo)} no fallback KNN")
            w = KNN.from_dataframe(geo, k=k)
    else:
        if k >= len(geo):
            raise ValueError(f"k={k} não pode ser >= n={len(geo)}")
        w = KNN.from_dataframe(geo, k=k)

    w.transform = "r"
    cardinalidades = list(w.cardinalities.values())
    meta = {
        "esquema_solicitado": esquema,
        "esquema_usado": "knn" if (esquema == "knn" or fallback) else "queen",
        "n": int(w.n),
        "k": int(k) if (esquema == "knn" or fallback) else None,
        "vizinhos_medios": round(float(np.mean(cardinalidades)), 3),
        "ilhas": ilhas_queen if esquema == "queen" else [],
        "fallback_por_ilhas": bool(fallback),
        "libpysal": libpysal.__version__,
    }
    return w, meta


def _validar_valores(valores, w) -> np.ndarray:
    """Valida o vetor de valores antes de Moran/LISA."""
    arr = np.asarray(valores, dtype=float)
    if arr.ndim != 1:
        raise ValueError("valores deve ser um vetor 1D")
    if len(arr) != w.n:
        raise ValueError(f"valores tem {len(arr)} elementos; a matriz de pesos tem {w.n}")
    if not np.isfinite(arr).all():
        raise ValueError("valores tem NaN ou infinito")
    return arr


def moran_global(valores, w, permutacoes: int = 999, seed: int = 42) -> dict:
    """Moran's I global com inferência permutacional.

    A seed é resetada antes da chamada porque ``esda`` usa o RNG global do
    numpy; sem isso, rodar o Moran antes do LISA muda os p-valores do LISA.
    """
    import esda

    arr = _validar_valores(valores, w)
    if not isinstance(permutacoes, int) or permutacoes < 1:
        raise ValueError("permutacoes deve ser um inteiro >= 1")
    if not isinstance(seed, int):
        raise ValueError("seed deve ser um inteiro")

    np.random.seed(seed)
    moran = esda.Moran(arr, w, permutations=permutacoes)
    return {
        "n": int(len(arr)),
        "I": float(moran.I),
        "EI": float(moran.EI),
        "z_perm": float(moran.z_sim),
        "p_perm": float(moran.p_sim),
        "z_normal": float(moran.z_norm),
        "p_normal": float(moran.p_norm),
        "permutacoes": int(permutacoes),
        "seed": int(seed),
        "esda": esda.__version__,
    }


def lisa_local(valores, w, permutacoes: int = 999, seed: int = 42) -> dict:
    """LISA local com 999 permutações (por padrão) e seed resetada."""
    import esda

    arr = _validar_valores(valores, w)
    if not isinstance(permutacoes, int) or permutacoes < 1:
        raise ValueError("permutacoes deve ser um inteiro >= 1")
    if not isinstance(seed, int):
        raise ValueError("seed deve ser um inteiro")

    np.random.seed(seed)
    lisa = esda.Moran_Local(arr, w, permutations=permutacoes)
    return {
        "n": int(len(arr)),
        "p_sim": np.asarray(lisa.p_sim, dtype=float),
        "q": np.asarray(lisa.q, dtype=int),
        "I_local": np.asarray(lisa.Is, dtype=float),
        "permutacoes": int(permutacoes),
        "seed": int(seed),
        "esda": esda.__version__,
    }


def classificar_quadrantes(p_sim, q, alpha: float = 0.05) -> np.ndarray:
    """Converte p-valor + quadrante LISA em ``HH/LH/LL/HL/ns``.

    Quadrantes do ``esda``: 1 = HH, 2 = LH, 3 = LL, 4 = HL.
    """
    p = np.asarray(p_sim, dtype=float)
    quadrantes = np.asarray(q, dtype=int)
    if p.ndim != 1 or quadrantes.ndim != 1:
        raise ValueError("p_sim e q devem ser vetores 1D")
    if p.shape != quadrantes.shape:
        raise ValueError("p_sim e q devem ter o mesmo tamanho")
    if not np.isfinite(p).all() or not ((0 <= p) & (p <= 1)).all():
        raise ValueError("p_sim deve estar entre 0 e 1")
    if not np.isin(quadrantes, [1, 2, 3, 4]).all():
        raise ValueError("q deve conter apenas quadrantes 1-4")
    if not (0 < alpha < 1):
        raise ValueError("alpha deve estar entre 0 e 1")

    classes = np.full(p.shape, "ns", dtype=object)
    for quadrante, categoria in [(1, "HH"), (2, "LH"), (3, "LL"), (4, "HL")]:
        classes[(p < alpha) & (quadrantes == quadrante)] = categoria
    return classes


def corrigir_bh(p_sim, alpha: float = 0.05) -> np.ndarray:
    """p-valores ajustados por Benjamini-Hochberg (FDR 5% por padrão).

    Implementação em numpy para não depender de ``statsmodels`` no CI; a
    fórmula é a mesma de ``multipletests(method='fdr_bh')``.
    """
    p = np.asarray(p_sim, dtype=float)
    if p.ndim != 1:
        raise ValueError("p_sim deve ser um vetor 1D")
    if not np.isfinite(p).all() or not ((0 <= p) & (p <= 1)).all():
        raise ValueError("p_sim deve estar entre 0 e 1")
    if not (0 < alpha < 1):
        raise ValueError("alpha deve estar entre 0 e 1")
    if len(p) == 0:
        return np.array([], dtype=float)

    n = len(p)
    ordem = np.argsort(p, kind="mergesort")
    ajustados = p[ordem] * n / np.arange(1, n + 1)
    # BH exige monotonicidade: o ajustado não pode cair ao subir o p bruto.
    ajustados = np.minimum.accumulate(ajustados[::-1])[::-1]
    ajustados = np.clip(ajustados, 0, 1)

    p_bh = np.empty_like(ajustados)
    p_bh[ordem] = ajustados
    return p_bh


def calcular_temporada(
    geo,
    casos: pd.DataFrame,
    esquema: str = "queen",
    k: int = 4,
    permutacoes: int = 999,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[pd.DataFrame, dict]:
    """Roda Moran + LISA para uma temporada e devolve ``(geodataframe, resumo)``.

    ``casos`` precisa ter uma linha por bairro de ``geo`` (use
    :func:`completar_temporadas`). O retorno preserva a geometria e adiciona as
    colunas de classificação e os p-valores.
    """
    if not isinstance(casos, pd.DataFrame):
        raise TypeError("casos deve ser um DataFrame")
    if "key" not in geo.columns:
        raise ValueError("geo sem coluna 'key'")
    if geo["key"].duplicated().any():
        raise ValueError("geo tem chave de bairro duplicada")
    faltando = [c for c in ["key", "casos"] if c not in casos.columns]
    if faltando:
        raise ValueError(f"casos sem colunas obrigatórias: {faltando}")
    if casos.duplicated("key").any():
        raise ValueError("casos tem bairro duplicado")

    casos = casos[["key", "casos"]].copy()
    casos["casos"] = pd.to_numeric(casos["casos"], errors="coerce")
    if casos["casos"].isna().any():
        raise ValueError("casos tem valor ausente ou não numérico")
    if (casos["casos"] < 0).any():
        raise ValueError("casos tem valor negativo")

    chaves_geo = set(geo["key"])
    chaves_casos = set(casos["key"])
    faltam = sorted(chaves_geo - chaves_casos)
    if faltam:
        raise ValueError(f"faltam bairros no vetor de casos: {faltam}")
    ignorados = sorted(chaves_casos - chaves_geo)

    valores = geo["key"].map(casos.set_index("key")["casos"])
    if valores.isna().any():
        raise ValueError("nem todo bairro de geo tem valor de casos")
    valores = valores.astype(float)
    if not np.allclose(valores, np.round(valores)):
        raise ValueError("casos devem ser contagens inteiras")

    w, meta_pesos = construir_pesos(geo, esquema=esquema, k=k)
    moran = moran_global(valores.to_numpy(), w, permutacoes=permutacoes, seed=seed)
    lisa = lisa_local(valores.to_numpy(), w, permutacoes=permutacoes, seed=seed)

    cluster = classificar_quadrantes(lisa["p_sim"], lisa["q"], alpha=alpha)
    p_bh = corrigir_bh(lisa["p_sim"], alpha=alpha)
    cluster_bh = classificar_quadrantes(p_bh, lisa["q"], alpha=alpha)

    resultado = geo.copy()
    resultado["casos"] = valores.astype(int)
    resultado["valor"] = valores
    resultado["p_sim"] = lisa["p_sim"]
    resultado["p_bh"] = p_bh
    resultado["quadrante"] = lisa["q"]
    resultado["I_local"] = lisa["I_local"]
    resultado["cluster"] = cluster.astype(str)
    resultado["cluster_bh"] = cluster_bh.astype(str)
    resultado["hotspot"] = (cluster == "HH").astype(bool)
    resultado["hotspot_bh"] = (cluster_bh == "HH").astype(bool)

    categorias = ["HH", "LH", "LL", "HL", "ns"]
    resumo = {
        "n_bairros": int(len(resultado)),
        "casos_total": int(resultado["casos"].sum()),
        "bairros_com_casos": int((resultado["casos"] > 0).sum()),
        "bairros_extra_ignorados": ignorados,
        "moran": moran,
        "pesos": meta_pesos,
        "permutacoes": int(permutacoes),
        "seed": int(seed),
        "alpha": float(alpha),
        "contagem": {
            categoria: int((resultado["cluster"] == categoria).sum())
            for categoria in categorias
        },
        "contagem_bh": {
            categoria: int((resultado["cluster_bh"] == categoria).sum())
            for categoria in categorias
        },
    }
    resultado.attrs["resumo"] = resumo
    return resultado, resumo
