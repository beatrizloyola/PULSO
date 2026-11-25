"""Inventário de estações pluviométricas de Recife e série semanal por estação (US05).

Rede de origem (dona da estação): `APAC` para as estações próprias da APAC
(convencionais e a da sede, mesmo quando a sede transmite pela plataforma do
CEMADEN); `CEMADEN` para as do cadastro ou só do download do CEMADEN. Quem
publicou cada medição fica na flag `origem` da série, não aqui.
O rótulo que a APAC usa no nome (`[APAC]`, `[CEMADEN]`, `[Convencional]`) é
mantido em `rotulo_apac`: ele não coincide sempre com o cadastro (ex.: Nova
Descoberta e Guabiraba aparecem como `[APAC]`, mas são estações CEMADEN).
"""
from __future__ import annotations

import re

import pandas as pd

from app.ambiente import espacializacao
from app.ingestao import cemaden

ORIGEM_APAC = "APAC"
ORIGEM_CEMADEN = cemaden.ORIGEM

_ATLAS_APAC = ("APAC, Atlas Climatológico de Pernambuco (normais 1991-2020), posto ")
# Estações só da APAC (fora do cadastro CEMADEN): coordenadas de publicações oficiais.
COORDENADAS_APAC = {
    "261160601V": (-8.050, -34.917, _ATLAS_APAC + "Recife (Várzea)"),
    "261160602V": (-8.044, -34.875, _ATLAS_APAC + "Recife (Santo Amaro)"),
    "261160604V": (-8.001, -34.935, _ATLAS_APAC + "Recife (Alto da Brasileira)"),
    "261160623A": (-8.04491, -34.87518, "ANA HidroInventário, estação 834020 (APAC-PE, Recife)"),
}
FONTE_CADASTRO_CEMADEN = "Cadastro CEMADEN (" + cemaden.CADASTRO_URL + ")"
FONTE_DOWNLOAD_CEMADEN = "Download CEMADEN (" + cemaden.DOWNLOAD_URL + ")"

_TIPOS = {"A": "automatica", "V": "convencional", "G": "geotecnica"}

COLUNAS_INVENTARIO = [
    "codigo", "nome", "latitude", "longitude", "fonte_coordenada", "rede", "tipo",
    "rotulo_apac", "publicada_apac", "publicada_cemaden", "inicio", "fim",
    "dias_com_leitura", "ds",
]


def rotulo_apac(nome: str) -> str:
    """'[CEMADEN 01] Várzea' -> 'CEMADEN'; 'Recife (Várzea) [Convencional]' -> 'Convencional'."""
    inicio = re.match(r"\s*\[([A-Za-z]+)", str(nome))
    if inicio:
        rotulo = inicio[1].upper()
        return ORIGEM_CEMADEN if rotulo.startswith("CEMADE") else rotulo
    return "Convencional" if "[convencional]" in str(nome).lower() else ""


def nome_limpo(nome: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", str(nome))).strip()


def tipo_estacao(codigo: str) -> str:
    return _TIPOS.get(str(codigo)[-1:].upper(), "outra")


def montar_inventario(apac: pd.DataFrame, consolidado: pd.DataFrame, cadastro: pd.DataFrame,
                      coords_cemaden: pd.DataFrame, poligonos, grade) -> pd.DataFrame:
    """Uma linha por estação: identificação, coordenadas e fonte, rede, período e DS.

    `apac`: leituras APAC (codigo, nome, ...); `consolidado`: leituras diárias já
    reconciliadas (codigo, data, chuva_mm, origem); `cadastro`: cadastro CEMADEN de
    Recife; `coords_cemaden`: coordenadas declaradas no download CEMADEN.
    Estação com leitura e sem coordenada interrompe a geração.
    """
    nomes_apac = apac.groupby("codigo")["nome"].last()
    cadastro = cadastro.set_index("codigo")
    coords_cemaden = coords_cemaden.set_index("codigo")
    periodo = consolidado.groupby("codigo").agg(
        inicio=("data", "min"), fim=("data", "max"), dias_com_leitura=("data", "nunique"))
    codigos = sorted(set(cadastro.index) | set(nomes_apac.index) | set(coords_cemaden.index) | set(periodo.index))

    linhas, sem_coordenada = [], []
    for codigo in codigos:
        if codigo in cadastro.index:
            lat, lon = cadastro.at[codigo, "latitude"], cadastro.at[codigo, "longitude"]
            fonte, nome = FONTE_CADASTRO_CEMADEN, cadastro.at[codigo, "nome"]
        elif codigo in COORDENADAS_APAC:
            lat, lon, fonte = COORDENADAS_APAC[codigo]
            nome = nome_limpo(nomes_apac.get(codigo, codigo))
        elif codigo in coords_cemaden.index:
            lat, lon = coords_cemaden.at[codigo, "latitude"], coords_cemaden.at[codigo, "longitude"]
            fonte, nome = FONTE_DOWNLOAD_CEMADEN, coords_cemaden.at[codigo, "nome"]
        else:
            sem_coordenada.append(codigo)
            continue
        no_cemaden = codigo in cadastro.index or codigo in coords_cemaden.index
        rede = ORIGEM_CEMADEN if no_cemaden and codigo not in COORDENADAS_APAC else ORIGEM_APAC
        linhas.append({
            "codigo": codigo, "nome": nome, "latitude": float(lat), "longitude": float(lon),
            "fonte_coordenada": fonte, "rede": rede, "tipo": tipo_estacao(codigo),
            "rotulo_apac": rotulo_apac(nomes_apac[codigo]) if codigo in nomes_apac.index else "",
            "publicada_apac": codigo in nomes_apac.index,
            "publicada_cemaden": codigo in coords_cemaden.index,
            "inicio": periodo["inicio"].get(codigo), "fim": periodo["fim"].get(codigo),
            "dias_com_leitura": int(periodo["dias_com_leitura"].get(codigo, 0)),
            "ds": espacializacao.ds_de_ponto(float(lat), float(lon), poligonos, grade),
        })
    if sem_coordenada:
        raise ValueError(f"Estações sem coordenadas conhecidas: {sem_coordenada}")
    return pd.DataFrame(linhas, columns=COLUNAS_INVENTARIO)


def serie_semanal(consolidado: pd.DataFrame) -> pd.DataFrame:
    """Diário reconciliado -> estação x SE. Semana sem os 7 dias fica sem total."""
    df = consolidado.dropna(subset=["chuva_mm"]).copy()
    df["semana"] = espacializacao.semana_de(df["data"])
    df["dia_cemaden"] = df["origem"] == ORIGEM_CEMADEN
    semanal = df.groupby(["codigo", "semana"], as_index=False).agg(
        chuva_soma=("chuva_mm", "sum"), dias=("data", "nunique"), dias_cemaden=("dia_cemaden", "sum"))
    semanal["chuva_mm"] = semanal["chuva_soma"].where(semanal["dias"] == 7)
    semanal["dias_cemaden"] = semanal["dias_cemaden"].astype(int)
    return semanal[["codigo", "semana", "chuva_mm", "dias", "dias_cemaden"]].sort_values(
        ["codigo", "semana"]).reset_index(drop=True)
