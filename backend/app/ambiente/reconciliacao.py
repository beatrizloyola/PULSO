"""Reconciliação APAC x CEMADEN (US06/US07): deduplicação, precedência e comparação.

Regra de precedência e de preenchimento de lacunas (por estação e dia):

1. Mesma estação = mesmo código. A APAC publica estações CEMADEN com o código
   do CEMADEN, então o código deduplica as duas fontes.
2. Havendo leitura APAC, ela vale (`origem = APAC`): é a série oficial já usada
   pelo modelo.
3. Sem leitura APAC, vale o total diário completo do download CEMADEN da mesma
   estação (`origem = CEMADEN`).
4. Sem nenhuma das duas, o dia fica ausente. Não há preenchimento a partir de
   outra estação nem de outra fonte nesta etapa; a espacialização por DS trata
   ausências com pesos de Thiessen e marca a falha.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.ambiente import espacializacao
from app.ingestao import cemaden

ORIGEM_APAC = "APAC"
ORIGEM_CEMADEN = cemaden.ORIGEM
TOLERANCIA_MM = 0.2  # resolução típica de pluviômetro de báscula
RAIO_PAR_KM = 3.0
MIN_DIAS_COMPARACAO = 30
CORRELACAO_REVISAR = 0.5
# Silêncio maior que isso encerra o período de operação da estação (ver periodos_operacao).
SILENCIO_MAX_DIAS = 365
# Sensor seco: zeros falsos (pluviômetro entupido ou travado) contra as vizinhas.
JANELA_SECO_DIAS = 30
MIN_DIAS_JANELA_SECO = 20
RAIO_SECO_KM = 5.0
MIN_VIZINHAS_SECO = 2  # Menos que isso na janela: compara com a mediana da cidade.
MIN_ESTACOES_CIDADE_SECO = 3
RAZAO_SECO = 0.1
MIN_MM_VIZINHAS_SECO = 30.0
# Dia D = 24 h que terminam N horas após 00h UTC de D (ver cemaden.FIM_DIA_UTC_H).
CONVENCOES_DIA = {
    "07h local de D (10h UTC)": 10,
    "08h local de D (11h UTC)": 11,
    "09h local de D (12h UTC)": 12,
    "dia civil de Recife (00h a 24h local)": 27,
}


def consolidar(apac: pd.DataFrame, cemaden_diario: pd.DataFrame) -> pd.DataFrame:
    """Uma leitura por estação/dia com flag `origem` (APAC ou CEMADEN)."""
    a = apac.dropna(subset=["chuva_mm"])[["codigo", "data", "chuva_mm"]].assign(origem=ORIGEM_APAC)
    c = cemaden_diario.dropna(subset=["chuva_mm"])[["codigo", "data", "chuva_mm"]].assign(origem=ORIGEM_CEMADEN)
    if a.duplicated(["codigo", "data"]).any() or c.duplicated(["codigo", "data"]).any():
        raise ValueError("Leituras duplicadas para estação/dia dentro de uma mesma fonte")
    ja_na_apac = c.set_index(["codigo", "data"]).index.isin(a.set_index(["codigo", "data"]).index)
    partes = [p for p in (a, c[~ja_na_apac]) if not p.empty]
    if not partes:
        return pd.DataFrame(columns=["codigo", "data", "chuva_mm", "origem"])
    df = pd.concat(partes, ignore_index=True)
    return df.sort_values(["codigo", "data"]).reset_index(drop=True)


def _trechos_continuos(datas: pd.Series, silencio_max_dias: int) -> list[tuple[str, str]]:
    dias = pd.to_datetime(pd.Series(sorted(datas.unique())))
    trecho = dias.diff().dt.days.gt(silencio_max_dias).cumsum()
    return [(g.iloc[0].strftime("%Y-%m-%d"), g.iloc[-1].strftime("%Y-%m-%d")) for _, g in dias.groupby(trecho)]


def periodos_operacao(apac: pd.DataFrame, cemaden_diario: pd.DataFrame,
                      janelas_cemaden: list[tuple[str, str]],
                      silencio_max_dias: int = SILENCIO_MAX_DIAS) -> pd.DataFrame:
    """Intervalos em que a ausência de leitura de cada estação conta como falha.

    APAC: da primeira à última leitura publicada da estação. CEMADEN: o mesmo, mas
    só dentro das janelas (meses) baixadas: mês não baixado não é falha da estação.
    Silêncio de mais de `silencio_max_dias` entre duas leituras encerra o período:
    a estação estava desativada, não falhando (ex.: um dia isolado publicado após
    dois anos mudo não torna os dois anos falha).
    """
    linhas = []
    for fonte, janelas in ((apac, None), (cemaden_diario, janelas_cemaden)):
        for codigo, datas in fonte.dropna(subset=["chuva_mm"]).groupby("codigo")["data"]:
            for primeira, ultima in _trechos_continuos(datas, silencio_max_dias):
                for inicio, fim in [(primeira, ultima)] if janelas is None else janelas:
                    if max(inicio, primeira) <= min(fim, ultima):
                        linhas.append((codigo, max(inicio, primeira), min(fim, ultima)))
    return pd.DataFrame(linhas, columns=["codigo", "inicio", "fim"])


def filtrar_sensor_seco(consolidado: pd.DataFrame, inventario: pd.DataFrame,
                        janela: int = JANELA_SECO_DIAS, min_dias: int = MIN_DIAS_JANELA_SECO,
                        raio_km: float = RAIO_SECO_KM, min_vizinhas: int = MIN_VIZINHAS_SECO,
                        min_cidade: int = MIN_ESTACOES_CIDADE_SECO,
                        razao: float = RAZAO_SECO, min_mm: float = MIN_MM_VIZINHAS_SECO,
                        ) -> tuple[pd.DataFrame, list[dict], list[str]]:
    """Remove leituras de estação com sensor seco (zeros falsos).

    Para cada janela de `janela` dias com ao menos `min_dias` leituras, compara a
    chuva média diária da estação com a mediana das vizinhas a até `raio_km` (ao
    menos `min_vizinhas` com janela válida; senão, a mediana das demais estações
    da cidade, ao menos `min_cidade`). Se a referência soma `min_mm` ou mais na
    janela e a estação fica abaixo de `razao` dela, todos os dias da janela saem:
    viram falha na espacialização, não chuva zero.

    Devolve as leituras mantidas, os trechos removidos por estação e as estações
    sem nenhuma vizinha no raio (checadas só contra a cidade).
    """
    diario = consolidado.pivot(index="data", columns="codigo", values="chuva_mm")
    datas = pd.date_range(diario.index.min(), diario.index.max()).strftime("%Y-%m-%d")
    diario = diario.reindex(datas)
    taxa = diario.rolling(janela, min_periods=min_dias).mean()
    coords = inventario.set_index("codigo").loc[diario.columns, ["latitude", "longitude"]].to_numpy()
    dist = espacializacao.distancia_km(coords[:, :1], coords[:, 1:], coords[:, 0], coords[:, 1])
    seco = pd.DataFrame(False, index=diario.index, columns=diario.columns)
    sem_vizinhas = []
    for j, codigo in enumerate(diario.columns):
        vizinhas = [k for k in range(len(diario.columns)) if k != j and dist[j, k] <= raio_km]
        if not vizinhas:
            sem_vizinhas.append(codigo)
        local = taxa.iloc[:, vizinhas]
        cidade = taxa.drop(columns=codigo)
        mediana = local.median(axis=1).where(
            local.notna().sum(axis=1) >= min_vizinhas,
            cidade.median(axis=1).where(cidade.notna().sum(axis=1) >= min_cidade))
        seco[codigo] = (mediana * janela >= min_mm) & (taxa[codigo] < razao * mediana)
    # Janela sinalizada termina em d e cobre d-janela+1..d: estende o sinal para trás.
    invalido = seco[::-1].astype(int).rolling(janela, min_periods=1).max()[::-1].astype(bool)

    removido = invalido.stack()
    removido = removido[removido].index
    chave = pd.MultiIndex.from_frame(consolidado[["data", "codigo"]])
    sai = chave.isin(removido)
    trechos = []
    for codigo in invalido.columns[invalido.any()]:
        s = invalido[codigo]
        for _, g in s[s].groupby((~s).cumsum()):
            leituras = diario.loc[g.index, codigo].dropna()
            if len(leituras):
                trechos.append({"codigo": codigo, "inicio": g.index[0], "fim": g.index[-1],
                                "dias_removidos": int(len(leituras)),
                                "chuva_removida_mm": _num(leituras.sum(), 1)})
    return consolidado[~sai].reset_index(drop=True), trechos, sorted(sem_vizinhas)


def _num(valor, casas=3):
    return None if valor is None or pd.isna(valor) else round(float(valor), casas)


def _correlacoes(x: pd.Series, y: pd.Series) -> dict:
    # Série constante (semana toda seca) não tem correlação definida: fica None.
    if x.nunique() < 2 or y.nunique() < 2:
        return {"pearson": None, "spearman": None}
    # Spearman = Pearson dos postos; evita depender do scipy.
    return {"pearson": _num(x.corr(y)), "spearman": _num(x.rank().corr(y.rank()))}


def comparar_duplicadas(apac: pd.DataFrame, cemaden_diario: pd.DataFrame,
                        tolerancia_mm: float = TOLERANCIA_MM) -> list[dict]:
    """Mesma estação nas duas fontes: concordância nos dias em comum."""
    comum = apac.dropna(subset=["chuva_mm"]).merge(
        cemaden_diario.dropna(subset=["chuva_mm"]), on=["codigo", "data"], suffixes=("_apac", "_cemaden"))
    saida = []
    for codigo, g in comum.groupby("codigo"):
        dif = g["chuva_mm_cemaden"] - g["chuva_mm_apac"]
        divergente = dif.abs() > np.maximum(1.0, 0.1 * g["chuva_mm_apac"])
        saida.append({
            "codigo": codigo, "dias_comuns": int(len(g)),
            **_correlacoes(g["chuva_mm_apac"], g["chuva_mm_cemaden"]),
            "vies_mm": _num(dif.mean()), "mae_mm": _num(dif.abs().mean()),
            "pct_concordancia": _num(100 * (dif.abs() <= tolerancia_mm).mean(), 1),
            "dias_divergentes": int(divergente.sum()),
        })
    return saida


def comparar_convencoes(apac: pd.DataFrame, leituras_cemaden: pd.DataFrame, inventario: pd.DataFrame,
                        raio_km: float = RAIO_PAR_KM, min_dias: int = MIN_DIAS_COMPARACAO,
                        convencoes: dict[str, int] = CONVENCOES_DIA) -> list[dict]:
    """Qual fim de dia faz o total CEMADEN acompanhar o diário da APAC.

    Compara cada estação CEMADEN com as estações APAC a até `raio_km`, incluindo a
    própria quando a APAC a publica. A convenção certa maximiza a correlação diária;
    sem duplicatas (antes de 2024), as vizinhas convencionais bastam.
    """
    coords = inventario.set_index("codigo")[["latitude", "longitude"]]
    apac_diario = apac.dropna(subset=["chuva_mm"]).pivot(index="data", columns="codigo", values="chuva_mm")
    saida = []
    for nome, fim_h in convencoes.items():
        diario = cemaden.agregar_diario(leituras_cemaden, fim_dia_utc_h=fim_h)
        cem_diario = diario.dropna(subset=["chuva_mm"]).pivot(index="data", columns="codigo", values="chuva_mm")
        correlacoes = []
        for c in cem_diario.columns:
            for a in apac_diario.columns:
                dist = espacializacao.distancia_km(*coords.loc[c], *coords.loc[a])
                if dist > raio_km:
                    continue
                par = pd.concat([apac_diario[a].rename("apac"), cem_diario[c].rename("cemaden")],
                                axis=1, join="inner").dropna()
                r = _correlacoes(par["apac"], par["cemaden"])["pearson"] if len(par) >= min_dias else None
                if r is not None:
                    correlacoes.append(r)
        duplicadas = comparar_duplicadas(apac, diario)
        dias = sum(p["dias_comuns"] for p in duplicadas)
        saida.append({
            "convencao": nome, "fim_dia_utc_h": fim_h,
            "pares_vizinhos": len(correlacoes), "pearson_medio_vizinhos": _num(np.mean(correlacoes))
            if correlacoes else None,
            "estacoes_duplicadas": len(duplicadas), "dias_duplicados": dias,
            "pct_concordancia_duplicadas": _num(
                sum(p["pct_concordancia"] * p["dias_comuns"] for p in duplicadas) / dias, 1) if dias else None,
        })
    return saida


def comparar_pares_proximos(consolidado: pd.DataFrame, inventario: pd.DataFrame,
                            raio_km: float = RAIO_PAR_KM, min_dias: int = MIN_DIAS_COMPARACAO) -> list[dict]:
    """Estações distintas a até `raio_km`: correlação diária e semanal nos dias em comum."""
    inv = inventario[inventario["codigo"].isin(consolidado["codigo"].unique())].reset_index(drop=True)
    diario = consolidado.pivot(index="data", columns="codigo", values="chuva_mm")
    semana = espacializacao.semana_de(pd.Series(diario.index, index=diario.index))
    saida = []
    for i in range(len(inv)):
        for j in range(i + 1, len(inv)):
            a, b = inv.iloc[i], inv.iloc[j]
            dist = float(espacializacao.distancia_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
            if dist > raio_km:
                continue
            par = diario[[a["codigo"], b["codigo"]]].dropna()
            if len(par) < min_dias:
                continue
            completas = par.groupby(semana.loc[par.index]).filter(lambda g: len(g) == 7)
            semanal = completas.groupby(semana.loc[completas.index]).sum()
            saida.append({
                "codigo_a": a["codigo"], "nome_a": a["nome"], "rede_a": a["rede"],
                "codigo_b": b["codigo"], "nome_b": b["nome"], "rede_b": b["rede"],
                "dist_km": _num(dist, 2), "dias_comuns": int(len(par)),
                "diaria": _correlacoes(par.iloc[:, 0], par.iloc[:, 1]),
                "semanas_comuns": int(len(semanal)),
                "semanal": _correlacoes(semanal.iloc[:, 0], semanal.iloc[:, 1]) if len(semanal) >= 3 else None,
            })
    return sorted(saida, key=lambda p: p["dist_km"])


def resumo_vizinhas(pares: list[dict], limite: float = CORRELACAO_REVISAR) -> list[dict]:
    """Mediana da correlação diária de cada estação com as vizinhas.

    Abaixo de `limite` a estação é marcada para revisão; não é excluída da série.
    """
    por_estacao: dict[str, list[float]] = {}
    for par in pares:
        if par["diaria"]["pearson"] is not None:
            for codigo in (par["codigo_a"], par["codigo_b"]):
                por_estacao.setdefault(codigo, []).append(par["diaria"]["pearson"])
    saida = []
    for codigo, valores in por_estacao.items():
        mediana = float(pd.Series(valores).median())
        saida.append({"codigo": codigo, "pares": len(valores), "pearson_diaria_mediana": _num(mediana),
                      "revisar": mediana < limite})
    return sorted(saida, key=lambda s: s["pearson_diaria_mediana"])


def resumo_origem(consolidado: pd.DataFrame) -> list[dict]:
    """Estações e estação-dias por ano e origem (quanto o CEMADEN acrescenta)."""
    df = consolidado.assign(ano=consolidado["data"].str[:4].astype(int))
    saida = []
    for ano, g in df.groupby("ano"):
        por_origem = g.groupby("origem").agg(estacoes=("codigo", "nunique"), estacao_dias=("data", "size"))
        saida.append({
            "ano": int(ano), "estacoes": int(g["codigo"].nunique()),
            **{f"estacoes_{o.lower()}": int(por_origem.at[o, "estacoes"]) if o in por_origem.index else 0
               for o in (ORIGEM_APAC, ORIGEM_CEMADEN)},
            **{f"estacao_dias_{o.lower()}": int(por_origem.at[o, "estacao_dias"]) if o in por_origem.index else 0
               for o in (ORIGEM_APAC, ORIGEM_CEMADEN)},
        })
    return saida
