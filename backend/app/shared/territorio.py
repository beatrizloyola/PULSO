"""Linguagem ubíqua de território: bairro -> DS -> RPA -> setor censitário.

Fonte de verdade para DS é `distritos_sanitarios_*.csv` (Secretaria de Saúde).
RPA é derivada do DS (mapeamento administrativo fixo de Recife). Setor
censitário fica como campo opcional até a ingestão do Censo 2022 (US08).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from app import config

# DS -> RPA é um mapeamento administrativo fixo (Lei Municipal de Regiões
# Político-Administrativas do Recife), não varia por fonte de dados.
_DS_PARA_RPA = {
    "1": "RPA 1", "2": "RPA 1",
    "3": "RPA 2",
    "4": "RPA 3",
    "5": "RPA 4",
    "6": "RPA 5",
    "7": "RPA 6", "8": "RPA 6",
}


def normalizar_nome_bairro(nome: str) -> str:
    """Remove acentos, colapsa espaços e uppercase. Chave estável para join entre fontes.

    Mesmo padrão usado em data_sync.norm()/forecast_features._norm(); não
    importamos de lá de propósito — shared kernel não deve depender de
    app.services (a direção certa é o contrário). Consolidar as 3 cópias
    nesse módulo é follow-up, não escopo desta issue.
    """
    sem_acento = unicodedata.normalize("NFD", str(nome).strip().upper())
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.split())


@dataclass(frozen=True)
class TerritorioId:
    """Identidade territorial estável de um bairro de Recife."""

    bairro: str
    bairro_normalizado: str
    distrito_sanitario: str
    rpa: str
    setor_censitario: str | None = None

    @property
    def ds(self) -> str:
        return self.distrito_sanitario


class BairroDesconhecidoError(KeyError):
    """Bairro sem DS mapeado — indica inconsistência entre fontes (SINAN, APAC, GIS)."""


@lru_cache(maxsize=1)
def _mapa_distritos() -> dict[str, TerritorioId]:
    """Carrega distritos_sanitarios_*.csv e monta o mapa canônico por nome normalizado."""
    caminho = next(config.DATA_DIR.glob("distritos_sanitarios_*.csv"))
    df = pd.read_csv(caminho, sep=";", encoding="utf-8")

    mapa: dict[str, TerritorioId] = {}
    for _, linha in df.iterrows():
        bairro = str(linha["bairro"]).strip()
        ds = str(linha["distrito_sanitario"]).strip()
        chave = normalizar_nome_bairro(bairro)
        mapa[chave] = TerritorioId(
            bairro=bairro,
            bairro_normalizado=chave,
            distrito_sanitario=ds,
            rpa=_DS_PARA_RPA.get(ds, "RPA N/A"),
        )
    return mapa


def territorio_de(nome_bairro: str) -> TerritorioId:
    """Resolve um nome de bairro (de qualquer fonte) para o TerritorioId canônico.

    Levanta BairroDesconhecidoError se o nome não normalizar para nenhum bairro
    dos 94 mapeados em distritos_sanitarios_*.csv — nunca retorna DS ambíguo.
    """
    chave = normalizar_nome_bairro(nome_bairro)
    mapa = _mapa_distritos()
    if chave not in mapa:
        raise BairroDesconhecidoError(
            f"Bairro '{nome_bairro}' (normalizado: '{chave}') não tem DS mapeado "
            f"em distritos_sanitarios_*.csv"
        )
    return mapa[chave]


def todos_territorios() -> list[TerritorioId]:
    """Os 94 territórios canônicos, para validação e exportação."""
    return list(_mapa_distritos().values())


def validar_cobertura_total(nomes_bairros: list[str]) -> None:
    """Falha se algum nome da lista (ex: bairros do SINAN) não mapear para DS.

    Usado por testes e pelo pipeline do painel (US14) para travar regressões
    de normalização antes que cheguem à agregação por DS.
    """
    sem_ds = sorted({
        nome for nome in nomes_bairros
        if normalizar_nome_bairro(nome) not in _mapa_distritos()
    })
    if sem_ds:
        raise BairroDesconhecidoError(
            f"{len(sem_ds)} bairro(s) sem DS mapeado: {sem_ds}"
        )
