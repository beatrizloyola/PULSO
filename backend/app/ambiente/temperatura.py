"""Temperatura do ar semanal (US10): diário -> semana epidemiológica CDC.

Definições (as mesmas do modelo atual para `temp_media` e `temp_max`):
- `temp_media`: média das temperaturas médias diárias da semana;
- `temp_max`: média das máximas diárias da semana;
- `temp_max_abs`: maior máxima diária da semana.
Semana sem os 7 dias fica sem valor.
"""
from __future__ import annotations

import pandas as pd

from app.ambiente.espacializacao import semana_de


def agregar_semanal(diario: pd.DataFrame) -> pd.DataFrame:
    """`diario`: data (AAAA-MM-DD), temp_media, temp_max."""
    df = diario.copy()
    df["semana"] = semana_de(df["data"])
    df["dia_valido"] = df[["temp_media", "temp_max"]].notna().all(axis=1)
    semanal = df.groupby("semana", as_index=False).agg(
        temp_media=("temp_media", "mean"), temp_max=("temp_max", "mean"),
        temp_max_abs=("temp_max", "max"), dias=("dia_valido", "sum"))
    semanal["dias"] = semanal["dias"].astype(int)
    semanal.loc[semanal["dias"] != 7, ["temp_media", "temp_max", "temp_max_abs"]] = float("nan")
    return semanal[["semana", "temp_media", "temp_max", "temp_max_abs", "dias"]]
