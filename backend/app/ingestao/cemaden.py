"""ACL do CEMADEN: download oficial do Mapa Interativo -> leituras internas (US06).

Fonte: https://mapainterativo.cemaden.gov.br/ -> "Download - Dados Pluviométricos"
(`/download/download_form.php`). O formulário exige captcha, então o arquivo
é baixado manualmente: um CSV mensal por UF ou município, separado por `;`.
Cada linha é o acumulado de um intervalo (10 min com chuva, 1 h sem chuva)
que termina em `datahora`, registrada em UTC.

Fora deste módulo só existem `codigo`, `data_hora_utc`, `data` e `chuva_mm`,
com a flag de origem `CEMADEN`.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

import pandas as pd

ORIGEM = "CEMADEN"
DOWNLOAD_URL = "https://mapainterativo.cemaden.gov.br/download/download_form.php"
CADASTRO_URL = "https://resources.cemaden.gov.br/dados/311_24.json"
RECIFE_IBGE = 2611606
# Código CEMADEN = IBGE de 6 dígitos + número + tipo (A pluviométrica, G geotécnica...).
PREFIXO_RECIFE = "261160"

# Duas variantes de cabeçalho publicadas pelo Mapa Interativo.
_COLUNAS = {
    "municipio": "municipio", "MUNICIPIO": "municipio",
    "codEstacao": "codigo", "COD_ESTACAO": "codigo",
    "uf": "uf", "UF": "uf",
    "nomeEstacao": "nome", "NOME_ESTACAO": "nome",
    "latitude": "latitude", "LATITUDE": "latitude",
    "longitude": "longitude", "LONGITUDE": "longitude",
    "datahora": "data_hora_utc", "DATA_HORA": "data_hora_utc",
    "valorMedida": "chuva_mm", "MEDIDA": "chuva_mm",
}
_OBRIGATORIAS = ["codigo", "nome", "latitude", "longitude", "data_hora_utc", "chuva_mm"]
_AUSENTE = {"", "-", "NAN", "NULL", "NONE"}

# Dia pluviométrico D = 24 h que terminam FIM_DIA_UTC_H horas após 00h UTC de D.
# 10 = 07h de Recife em D, a leitura padrão de pluviômetro (ANA). Contra os postos
# convencionais da APAC em 2016–2019, a correlação diária com as automáticas a até 3 km
# tem pico entre 07h e 08h; 27 seria o dia civil de Recife (00h local de D+1).
FIM_DIA_UTC_H = 10
# Sem chuva a estação transmite de hora em hora; menos que isso é falha de dado.
HORAS_MIN_DIA = 22
# Uma leitura cobre no máximo 1 h (10 min com chuva). Acima disto não é chuva do
# intervalo: é acumulado despejado após falha de transmissão (ex.: 194 mm às 03:10 UTC
# de 14/06/2019 em 601A, depois de 3 semanas sem dado). O dia inteiro fica ausente.
MAX_MM_LEITURA = 50.0


def _texto(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str.strip().str.strip('"')


def _numero(serie: pd.Series, campo: str) -> pd.Series:
    texto = _texto(serie)
    ausente = texto.str.upper().isin(_AUSENTE)
    valores = pd.to_numeric(texto.str.replace(",", ".", regex=False).where(~ausente), errors="coerce")
    if (valores.isna() & ~ausente).any():
        raise ValueError(f"CEMADEN: {campo} não numérico")
    return valores


def _data_hora(serie: pd.Series) -> pd.Series:
    texto = _texto(serie)
    valores = pd.to_datetime(texto, format="ISO8601", errors="coerce")
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        faltando = valores.isna()
        if not faltando.any():
            break
        valores[faltando] = pd.to_datetime(texto[faltando], format=formato, errors="coerce")
    if valores.isna().any():
        raise ValueError("CEMADEN: data/hora em formato desconhecido")
    return valores.dt.tz_localize(None) if valores.dt.tz is not None else valores


def parse_download(texto: str, prefixo: str = PREFIXO_RECIFE) -> pd.DataFrame:
    """CSV oficial -> leituras sub-diárias únicas de Recife, em UTC.

    Valor ausente é descartado (nunca vira zero); valor negativo ou conflitante
    para a mesma estação/horário interrompe a leitura.
    """
    linhas = texto.lstrip("\ufeff").splitlines()
    if not linhas:
        raise ValueError("CEMADEN: arquivo vazio")
    cabecalho = [c.strip().strip('"') for c in linhas[0].split(";")]
    nomes = [_COLUNAS.get(c, c) for c in cabecalho]
    if not set(_OBRIGATORIAS).issubset(nomes):
        raise ValueError("CEMADEN: cabeçalho ausente ou formato alterado")
    bruto = pd.DataFrame([linha.split(";") for linha in linhas[1:] if linha.strip()])
    if bruto.empty:
        raise ValueError("CEMADEN: arquivo sem leituras")
    if bruto.shape[1] != len(nomes):
        raise ValueError("CEMADEN: linha com número inesperado de colunas")
    bruto.columns = nomes
    bruto["codigo"] = _texto(bruto["codigo"])
    bruto = bruto[bruto["codigo"].str.startswith(prefixo)]
    if bruto.empty:
        raise ValueError("CEMADEN: nenhuma leitura de Recife no arquivo")

    df = pd.DataFrame({
        "codigo": bruto["codigo"],
        "nome": _texto(bruto["nome"]),
        "latitude": _numero(bruto["latitude"], "latitude"),
        "longitude": _numero(bruto["longitude"], "longitude"),
        "data_hora_utc": _data_hora(bruto["data_hora_utc"]),
        "chuva_mm": _numero(bruto["chuva_mm"], "precipitação"),
    })
    df = df.dropna(subset=["chuva_mm"])
    if not df["chuva_mm"].map(math.isfinite).all() or (df["chuva_mm"] < 0).any():
        raise ValueError("CEMADEN: precipitação inválida")
    if (df.groupby(["codigo", "data_hora_utc"])["chuva_mm"].nunique() > 1).any():
        raise ValueError("CEMADEN: leituras conflitantes para estação/horário")
    df = df.drop_duplicates(["codigo", "data_hora_utc"])
    return df.sort_values(["codigo", "data_hora_utc"]).reset_index(drop=True)


def ler_texto(caminho: Path) -> str:
    """Download oficial (`.csv`) ou extrato comprimido (`.csv.gz`)."""
    bruto = caminho.read_bytes()
    if caminho.suffix == ".gz":
        bruto = gzip.decompress(bruto)
    try:
        return bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        return bruto.decode("latin-1")


def ler_download(caminho: Path, prefixo: str = PREFIXO_RECIFE) -> pd.DataFrame:
    return parse_download(ler_texto(caminho), prefixo)


def extrair_recife(texto: str, prefixo: str = PREFIXO_RECIFE) -> str:
    """Cabeçalho + linhas de Recife, sem alteração: o extrato segue no formato oficial.

    Serve para versionar só Recife a partir de um download de UF inteira.
    """
    linhas = texto.lstrip("\ufeff").splitlines()
    nomes = [_COLUNAS.get(c.strip().strip('"'), c) for c in linhas[0].split(";")] if linhas else []
    if "codigo" not in nomes:
        raise ValueError("CEMADEN: cabeçalho ausente ou formato alterado")
    coluna = nomes.index("codigo")
    recife = [linha for linha in linhas[1:]
              if linha.count(";") >= coluna and linha.split(";")[coluna].strip().strip('"').startswith(prefixo)]
    if not recife:
        raise ValueError("CEMADEN: nenhuma leitura de Recife no arquivo")
    return "\n".join([linhas[0], *recife]) + "\n"


def juntar_leituras(partes: list[pd.DataFrame]) -> pd.DataFrame:
    """Vários meses/arquivos; sobreposição idêntica é deduplicada, conflito falha."""
    if not partes:
        return pd.DataFrame(columns=["codigo", "nome", "latitude", "longitude", "data_hora_utc", "chuva_mm"])
    df = pd.concat(partes, ignore_index=True)
    if (df.groupby(["codigo", "data_hora_utc"])["chuva_mm"].nunique() > 1).any():
        raise ValueError("CEMADEN: arquivos com leituras conflitantes para estação/horário")
    return df.drop_duplicates(["codigo", "data_hora_utc"]).sort_values(
        ["codigo", "data_hora_utc"]).reset_index(drop=True)


def agregar_diario(leituras: pd.DataFrame, fim_dia_utc_h: int = FIM_DIA_UTC_H,
                   horas_min: int = HORAS_MIN_DIA, max_mm_leitura: float = MAX_MM_LEITURA) -> pd.DataFrame:
    """Leituras sub-diárias -> total diário por estação.

    A leitura marca o fim do intervalo: com o padrão (10), a de 10:00 UTC de D
    fecha o dia D e a de 10:10 UTC já é do dia D+1. Dia com menos de
    `horas_min` horas com transmissão, ou com leitura acima de `max_mm_leitura`,
    fica com `chuva_mm` ausente, não com a soma parcial.
    """
    colunas = ["codigo", "data", "chuva_mm", "horas_com_dado", "leitura_suspeita"]
    if leituras.empty:
        return pd.DataFrame(columns=colunas)
    deslocado = leituras["data_hora_utc"] + pd.Timedelta(hours=24 - fim_dia_utc_h) - pd.Timedelta(seconds=1)
    df = pd.DataFrame({"codigo": leituras["codigo"].to_numpy(),
                       "data": deslocado.dt.strftime("%Y-%m-%d").to_numpy(),
                       "hora": deslocado.dt.hour.to_numpy(),
                       "chuva_mm": leituras["chuva_mm"].to_numpy()})
    diario = df.groupby(["codigo", "data"], as_index=False).agg(
        chuva_mm=("chuva_mm", "sum"), horas_com_dado=("hora", "nunique"), maior=("chuva_mm", "max"))
    diario["leitura_suspeita"] = diario["maior"] > max_mm_leitura
    invalido = (diario["horas_com_dado"] < horas_min) | diario["leitura_suspeita"]
    diario.loc[invalido, "chuva_mm"] = float("nan")
    return diario[colunas]


def coordenadas_download(leituras: pd.DataFrame) -> pd.DataFrame:
    """Coordenadas declaradas no próprio download, uma por estação."""
    colunas = ["codigo", "nome", "latitude", "longitude"]
    if leituras.empty:
        return pd.DataFrame(columns=colunas)
    return leituras.groupby("codigo", as_index=False).agg(
        nome=("nome", "last"), latitude=("latitude", "median"), longitude=("longitude", "median"))[colunas]


def parse_cadastro(texto: str, codibge: int = RECIFE_IBGE) -> pd.DataFrame:
    """Cadastro público de estações (JSONP de resources.cemaden.gov.br) -> Recife."""
    try:
        dados = json.loads(texto[texto.index("(") + 1:texto.rindex(")")])
        estacoes = [e for bloco in dados for e in bloco["estacao"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("CEMADEN: cadastro de estações em formato alterado") from exc
    linhas = [{"codigo": e["codestacao"], "nome": e["nomeestacao"],
               "latitude": float(e["latitude"]), "longitude": float(e["longitude"]),
               "rede": e.get("sigla") or ORIGEM, "tipo": e.get("tipoestacao")}
              for e in estacoes if e.get("codibge") == codibge]
    if not linhas:
        raise ValueError("CEMADEN: cadastro sem estações de Recife")
    return pd.DataFrame(linhas).drop_duplicates("codigo").sort_values("codigo").reset_index(drop=True)
