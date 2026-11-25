"""Chuva por DS: polígonos de Thiessen (Voronoi) discretizados sobre os DS (US05).

Cada DS é amostrado por uma grade regular de pontos. A cada dia, cada ponto
recebe a chuva da estação mais próxima **entre as que mediram naquele dia**;
a chuva do DS é a média dos pontos (= média das estações ponderada pela área
de Thiessen dentro do DS). A rede muda ao longo do tempo, então os pesos são
recalculados por dia.

Falha: fração da área do DS cuja estação mais próxima **em operação** (entre a
primeira e a última leitura dela) não mediu no dia. É o quanto da área ficou
coberta por uma estação mais distante. Semana com falha média acima de
`LIMITE_FALHA` ou com dia sem nenhuma estação fica incompleta: `chuva_mm`
ausente, nunca preenchida em silêncio.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app import config
from app.shared.semana_epidemiologica import SemanaEpidemiologica
from app.shared.territorio import territorio_de

PASSO_GRAUS = 0.0025  # ~275 m em Recife
LIMITE_FALHA = 0.2
_KM_POR_GRAU_LAT = 110.574
_KM_POR_GRAU_LON = 111.320 * math.cos(math.radians(-8.05))


@dataclass(frozen=True)
class GradeDS:
    """Pontos da grade dentro dos DS, com o DS de cada ponto."""

    lat: np.ndarray
    lon: np.ndarray
    ds: np.ndarray


# Bairros do ESIG com grafia diferente da tabela canônica de DS.
_NOMES_ESIG = {"Cohab - Ibura de Cima": "Cohab", "Sítio dos Pintos - São Brás": "Sitio dos Pintos"}


def carregar_poligonos_ds(caminho: Path | None = None) -> dict[str, list[np.ndarray]]:
    """Polígonos dos 94 bairros (ESIG) agrupados pelo DS canônico -> anéis (lon, lat).

    O DS vem de `territorio_de` (tabela da Secretaria de Saúde), não do código de DS
    dos arquivos GIS: eles trocam DS VII e VIII em 14 bairros, e o painel usa a tabela.
    """
    caminho = caminho or config.DATA_DIR / "bairros_esig.geojson"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    poligonos: dict[str, list[np.ndarray]] = {}
    for feature in dados["features"]:
        nome = feature["properties"]["EBAIRRNOMEOF"]
        ds = territorio_de(_NOMES_ESIG.get(nome, nome)).ds
        geometria = feature["geometry"]
        partes = geometria["coordinates"] if geometria["type"] == "MultiPolygon" else [geometria["coordinates"]]
        poligonos.setdefault(ds, []).extend(np.asarray(anel, dtype=float)[:, :2] for parte in partes for anel in parte)
    return poligonos


def _dentro(lon: np.ndarray, lat: np.ndarray, aneis: list[np.ndarray], bloco: int = 2048) -> np.ndarray:
    """Ray casting par-ímpar sobre todos os anéis (buracos saem automaticamente)."""
    todos = np.vstack(aneis)
    candidatos = np.flatnonzero((lon >= todos[:, 0].min()) & (lon <= todos[:, 0].max())
                                & (lat >= todos[:, 1].min()) & (lat <= todos[:, 1].max()))
    dentro = np.zeros(lon.shape, dtype=bool)
    if not len(candidatos):
        return dentro
    x, y = lon[candidatos, None], lat[candidatos, None]
    arestas = np.vstack([np.hstack([anel, np.roll(anel, -1, axis=0)]) for anel in aneis])
    cruzamentos = np.zeros(len(candidatos), dtype=int)
    for inicio in range(0, len(arestas), bloco):
        ax, ay, bx, by = arestas[inicio:inicio + bloco].T
        cruza = (ay > y) != (by > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_corte = ax + (y - ay) * (bx - ax) / (by - ay)
        cruzamentos += (cruza & (x < x_corte)).sum(axis=1)
    dentro[candidatos] = cruzamentos % 2 == 1
    return dentro


def grade_ds(poligonos: dict[str, list[np.ndarray]], passo: float = PASSO_GRAUS) -> GradeDS:
    todos = np.vstack([anel for aneis in poligonos.values() for anel in aneis])
    lon_min, lat_min = todos.min(axis=0)
    lon_max, lat_max = todos.max(axis=0)
    lon, lat = np.meshgrid(np.arange(lon_min + passo / 2, lon_max, passo),
                           np.arange(lat_min + passo / 2, lat_max, passo))
    lon, lat = lon.ravel(), lat.ravel()
    ds = np.full(lon.shape, "", dtype=object)
    for codigo, aneis in sorted(poligonos.items()):
        ds[_dentro(lon, lat, aneis) & (ds == "")] = codigo
    manter = ds != ""
    return GradeDS(lat=lat[manter], lon=lon[manter], ds=ds[manter].astype(str))


def distancia_km(lat1, lon1, lat2, lon2):
    """Equiretangular: erro desprezível na escala de um município."""
    return np.hypot((np.asarray(lat1) - lat2) * _KM_POR_GRAU_LAT,
                    (np.asarray(lon1) - lon2) * _KM_POR_GRAU_LON)


def ds_de_ponto(lat: float, lon: float, poligonos: dict[str, list[np.ndarray]], grade: GradeDS) -> str:
    """DS que contém o ponto; fora de todos (margem/costa), o DS da grade mais próxima."""
    for codigo, aneis in sorted(poligonos.items()):
        if _dentro(np.array([lon]), np.array([lat]), aneis)[0]:
            return codigo
    return str(grade.ds[np.argmin(distancia_km(grade.lat, grade.lon, lat, lon))])


def pesos_thiessen(estacoes: pd.DataFrame, grade: GradeDS) -> pd.DataFrame:
    """Peso de cada estação em cada DS com a rede completa informada (documentação)."""
    dist = distancia_km(grade.lat[:, None], grade.lon[:, None],
                        estacoes["latitude"].to_numpy()[None, :], estacoes["longitude"].to_numpy()[None, :])
    mais_proxima = estacoes["codigo"].to_numpy()[dist.argmin(axis=1)]
    pesos = pd.crosstab(grade.ds, mais_proxima, normalize="index").stack()
    pesos = pesos[pesos > 0].rename("peso").reset_index()
    pesos.columns = ["ds", "codigo", "peso"]
    return pesos.sort_values(["ds", "peso"], ascending=[True, False]).reset_index(drop=True)


def chuva_ds_diaria(diario: pd.DataFrame, estacoes: pd.DataFrame, grade: GradeDS,
                    datas: list[str] | None = None, periodos: pd.DataFrame | None = None) -> pd.DataFrame:
    """Leituras diárias por estação -> chuva diária por DS com falha e distância média.

    `diario`: codigo, data (AAAA-MM-DD), chuva_mm (sem linhas ausentes).
    `estacoes`: codigo, latitude, longitude (todas as estações de `diario`).
    `periodos`: codigo, inicio, fim — intervalos (vários por estação) em que a ausência
    de leitura é falha. Padrão: da primeira à última leitura de cada estação.
    """
    diario = diario.dropna(subset=["chuva_mm"])
    codigos = sorted(diario["codigo"].unique())
    faltando = set(codigos) - set(estacoes["codigo"])
    if faltando:
        raise ValueError(f"Estações sem coordenadas: {sorted(faltando)}")
    coords = estacoes.set_index("codigo").loc[codigos]
    if datas is None:
        datas = pd.date_range(diario["data"].min(), diario["data"].max()).strftime("%Y-%m-%d").tolist()
    chuva = diario.pivot(index="data", columns="codigo", values="chuva_mm").reindex(index=datas, columns=codigos)
    valores = chuva.to_numpy(dtype=float)
    if periodos is None:
        periodos = diario.groupby("codigo", as_index=False)["data"].agg(inicio="min", fim="max")
    dias = np.array(datas, dtype=object)
    em_operacao = np.zeros((len(datas), len(codigos)), dtype=bool)
    coluna = {codigo: j for j, codigo in enumerate(codigos)}
    for codigo, inicio, fim in periodos[["codigo", "inicio", "fim"]].itertuples(index=False):
        if codigo in coluna:
            em_operacao[:, coluna[codigo]] |= (dias >= inicio) & (dias <= fim)

    dist = distancia_km(grade.lat[:, None], grade.lon[:, None],
                        coords["latitude"].to_numpy()[None, :], coords["longitude"].to_numpy()[None, :])
    lista_ds = sorted(set(grade.ds))
    indice_ds = np.searchsorted(lista_ds, grade.ds)
    pontos_ds = np.bincount(indice_ds, minlength=len(lista_ds))
    cache: dict[tuple[bytes, bytes], tuple] = {}

    def configuracao(mediu: np.ndarray, operando: np.ndarray):
        chave = (mediu.tobytes(), operando.tobytes())
        if chave not in cache:
            n_est = len(codigos)
            if not mediu.any():
                cache[chave] = None
            else:
                idx_mediu = np.flatnonzero(mediu)
                proxima = idx_mediu[dist[:, idx_mediu].argmin(axis=1)]
                idx_oper = np.flatnonzero(operando)
                proxima_oper = idx_oper[dist[:, idx_oper].argmin(axis=1)]
                falhou = ~mediu[proxima_oper]
                pesos = np.zeros((len(lista_ds), n_est))
                np.add.at(pesos, (indice_ds, proxima), 1.0)
                pesos /= pontos_ds[:, None]
                cache[chave] = (
                    pesos,
                    np.bincount(indice_ds, weights=falhou, minlength=len(lista_ds)) / pontos_ds,
                    np.bincount(indice_ds, weights=dist[np.arange(len(proxima)), proxima],
                                minlength=len(lista_ds)) / pontos_ds,
                    (pesos > 0).sum(axis=1),
                )
        return cache[chave]

    linhas = []
    for i, data in enumerate(datas):
        mediu = ~np.isnan(valores[i])
        conf = configuracao(mediu, em_operacao[i] | mediu)
        if conf is None:
            for ds in lista_ds:
                linhas.append((ds, data, np.nan, 1.0, 0, np.nan))
            continue
        pesos, falha, dist_media, n_est = conf
        chuva_ds = pesos @ np.nan_to_num(valores[i])
        for j, ds in enumerate(lista_ds):
            linhas.append((ds, data, chuva_ds[j], falha[j], int(n_est[j]), dist_media[j]))
    return pd.DataFrame(linhas, columns=["ds", "data", "chuva_mm", "falha", "n_estacoes", "dist_media_km"])


def semana_de(datas: pd.Series) -> pd.Series:
    unicas = {d: SemanaEpidemiologica.de_data(pd.Timestamp(d).date()).codigo for d in datas.unique()}
    return datas.map(unicas).astype(int)


def chuva_ds_semanal(diario_ds: pd.DataFrame, limite_falha: float = LIMITE_FALHA) -> pd.DataFrame:
    """Diário por DS -> SE. Dia sem linha conta como falha total."""
    df = diario_ds.copy()
    df["semana"] = semana_de(df["data"])
    semanal = df.groupby(["ds", "semana"], as_index=False).agg(
        chuva_soma=("chuva_mm", "sum"), dias_com_estimativa=("chuva_mm", "count"),
        dias=("data", "count"), falha_soma=("falha", "sum"),
        n_estacoes=("n_estacoes", "max"), dist_media_km=("dist_media_km", "mean"))
    semanal["falha"] = (semanal["falha_soma"] + (7 - semanal["dias"])) / 7
    semanal["completa"] = (semanal["dias_com_estimativa"] == 7) & (semanal["falha"] <= limite_falha)
    semanal["chuva_mm"] = semanal["chuva_soma"].where(semanal["completa"])
    colunas = ["ds", "semana", "chuva_mm", "completa", "falha", "dias_com_estimativa",
               "n_estacoes", "dist_media_km"]
    return semanal[colunas].sort_values(["ds", "semana"]).reset_index(drop=True)
