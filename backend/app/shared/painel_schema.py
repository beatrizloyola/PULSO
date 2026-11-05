"""Contrato de schema do painel analitico (US14): colunas, chave unica, faixas.

Qualquer regressao de normalizacao, agregacao ou unidade quebra aqui antes de
alimentar treino (US34) ou a API — nunca silenciosamente num painel invalido.
"""
from __future__ import annotations

import pandas as pd

CHAVE_BAIRRO = ["bairro_id", "semana"]
CHAVE_DS = ["ds", "semana"]

COLUNAS_OBRIGATORIAS_BAIRRO = [
    "bairro_id", "bairro", "ds", "rpa", "semana", "casos", "chuva_mm", "temp_media",
]
COLUNAS_OBRIGATORIAS_DS = ["ds", "semana", "casos", "chuva_mm", "temp_media"]

# coluna -> (minimo, maximo) inclusive; None = sem limite. NaN é ignorado:
# ausencia de dado é um estado legítimo (semana sem cobertura), não um erro.
FAIXAS_VALIDAS = {
    "casos": (0, None),
    "chuva_mm": (0, None),
    "temp_media": (-10, 45),
    "temp_max": (-10, 50),
    "vuln": (0, 100),
    "hist": (0, 100),
}


class SchemaInvalidoError(ValueError):
    """Painel não respeita o contrato de schema — não deve seguir para treino/API."""


def _validar_semanas(df: pd.DataFrame) -> list[str]:
    if "semana" not in df.columns:
        return []
    semanas = df["semana"].dropna()
    semana_do_ano = semanas.astype(int) % 100
    if ((semana_do_ano < 1) | (semana_do_ano > 53)).any():
        return ["semana: código fora do formato AAAASS (semana 1-53)"]
    return []


def _validar_faixas(df: pd.DataFrame) -> list[str]:
    problemas = []
    for coluna, (minimo, maximo) in FAIXAS_VALIDAS.items():
        if coluna not in df.columns:
            continue
        valores = df[coluna].dropna()
        if minimo is not None and (valores < minimo).any():
            problemas.append(f"{coluna}: valor(es) abaixo do mínimo ({minimo})")
        if maximo is not None and (valores > maximo).any():
            problemas.append(f"{coluna}: valor(es) acima do máximo ({maximo})")
    return problemas


def _validar(df: pd.DataFrame, colunas_obrigatorias: list[str], chave: list[str]) -> list[str]:
    problemas = []

    faltando = [c for c in colunas_obrigatorias if c not in df.columns]
    if faltando:
        problemas.append(f"colunas obrigatórias ausentes: {faltando}")

    if not faltando:
        if df[chave].isna().any().any():
            problemas.append(f"chave {chave} tem valor nulo")
        duplicadas = df.duplicated(chave)
        if duplicadas.any():
            problemas.append(f"chave {chave} não é única: {int(duplicadas.sum())} linha(s) duplicada(s)")

    problemas += _validar_semanas(df)
    problemas += _validar_faixas(df)
    return problemas


def validar_painel_bairro(df: pd.DataFrame) -> None:
    """Valida painel bairro x SE: colunas, chave bairro+semana única, faixas válidas."""
    problemas = _validar(df, COLUNAS_OBRIGATORIAS_BAIRRO, CHAVE_BAIRRO)
    if problemas:
        raise SchemaInvalidoError("painel bairro x SE inválido: " + "; ".join(problemas))


def validar_painel_ds(df: pd.DataFrame) -> None:
    """Valida painel DS x SE: colunas, chave ds+semana única, faixas válidas."""
    problemas = _validar(df, COLUNAS_OBRIGATORIAS_DS, CHAVE_DS)
    if problemas:
        raise SchemaInvalidoError("painel DS x SE inválido: " + "; ".join(problemas))
