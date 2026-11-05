"""Semana epidemiológica (padrão CDC, via `epiweeks`) como tipo de domínio.

Consolida no shared kernel a conversão data -> código SE (AAAASS) hoje
duplicada em data_sync.py, forecast_serving.py e forecast_features.py, para
que US14/US34 (painel e CI) tenham uma única definição a validar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from epiweeks import Week

SISTEMA = "cdc"


@dataclass(frozen=True, order=True)
class SemanaEpidemiologica:
    """Código SE no formato ano*100+semana (ex: 202520), com aritmética de semanas."""

    codigo: int

    @property
    def ano(self) -> int:
        return self.codigo // 100

    @property
    def semana(self) -> int:
        return self.codigo % 100

    @classmethod
    def de_data(cls, dt: date) -> "SemanaEpidemiologica":
        w = Week.fromdate(dt, system=SISTEMA)
        return cls(w.year * 100 + w.week)

    @classmethod
    def de_codigo(cls, codigo: int) -> "SemanaEpidemiologica":
        return cls(codigo)

    @classmethod
    def de_ano_semana(cls, ano: int, semana: int) -> "SemanaEpidemiologica":
        return cls(ano * 100 + semana)

    def _week(self) -> Week:
        return Week(self.ano, self.semana, system=SISTEMA)

    def __add__(self, horizonte: int) -> "SemanaEpidemiologica":
        w = self._week() + horizonte
        return SemanaEpidemiologica(w.year * 100 + w.week)

    def __sub__(self, horizonte: int) -> "SemanaEpidemiologica":
        return self.__add__(-horizonte)

    def inicio(self) -> date:
        return self._week().startdate()
