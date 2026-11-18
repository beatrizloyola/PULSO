#!/usr/bin/env python3
"""
Atlas Brasil (PNUD/Ipea/FJP): IDHM 2010 por Unidade de Desenvolvimento Humano
(UDH) agregado para os 94 bairros do Recife.

O Atlas publica o IDHM no nível de UDH, não de bairro. Este script:
  1. lista as UDHs da Região Metropolitana do Recife (id 11 no Atlas) e mantém
     apenas as do município do Recife;
  2. baixa o IDHM 2010 (indicador 196) e a população total (indicador 166),
     ambos do Censo 2010, para cada UDH;
  3. mapeia cada UDH para os bairros citados no nome oficial da UDH
     ("Afogados / Estância / Jiquiá : ..." -> AFOGADOS, ESTANCIA, JIQUIA);
  4. agrega por bairro com média ponderada pela população. Quando uma UDH
     abrange mais de um bairro, a população é dividida igualmente entre eles.

Gera app/data/idh_atlas_2010.json. Uso (a partir de backend/):

    python -m scripts.build_idh_atlas

Fonte: https://www.atlasbrasil.org.br/consulta/planilha
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config

ATLAS_BASE = "https://www.atlasbrasil.org.br"
ATLAS_CONSULTA_URL = f"{ATLAS_BASE}/consulta/planilha"
RM_RECIFE_ID = 11          # Região Metropolitana do Recife na base do Atlas
TIPO_UDH = 6               # código de territorialidade "UDH"
TIPO_GRID_UDH = 5          # valor de "e" (entidade) que a API de grade espera para UDH
INDICADOR_IDHM = 196       # IDHM (Censo)
INDICADOR_POPULACAO = 166  # População total (Censo)
ANO_2010_ID = 3            # id do período 2010 no indicador IDHM
MUNICIPIO_RECIFE = "Recife"

OUTPUT_FILE = config.DATA_DIR / "idh_atlas_2010.json"


def _normalize(s: str) -> str:
    """Remove acentos e pontuação, igual à normalização dos nomes do lookup."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r"[^A-Z0-9 ]", " ", s.upper()).strip()


def _parse_numero(valor: str) -> float:
    """'0,952' -> 0.952 ; '9.635' -> 9635.0"""
    return float(valor.replace(".", "").replace(",", "."))


def _parse_populacao(valor: str) -> int:
    return int(round(_parse_numero(valor)))


def _sessao() -> Tuple[requests.Session, str]:
    """Abre sessão e captura o token CSRF exigido pela API de consulta."""
    session = requests.Session()
    session.headers.update({"User-Agent": "PULSO/1.0 (coleta IDH Atlas Brasil)"})
    resp = session.get(ATLAS_CONSULTA_URL, timeout=60)
    resp.raise_for_status()
    match = re.search(r"_token\s*:\s*'([^']+)'", resp.text)
    if not match:
        raise RuntimeError("token CSRF não encontrado na página de consulta do Atlas")
    return session, match.group(1)


def _post(session: requests.Session, token: str, path: str, **kwargs):
    """POST com uma nova tentativa em caso de falha transitória."""
    url = f"{ATLAS_BASE}{path}"
    for tentativa in range(1, 4):
        try:
            resp = session.post(url, headers={"X-CSRF-Token": token}, timeout=90, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if tentativa == 3:
                raise RuntimeError(f"falha ao consultar {path}: {exc}") from exc
            time.sleep(2)
    raise AssertionError("inalcançável")


def listar_udhs(session: requests.Session, token: str) -> List[dict]:
    """Percorre as páginas de UDHs da RM Recife."""
    udhs: List[dict] = []
    pagina = 1
    while True:
        data = _post(
            session, token, "/api/selecionarTerritorialidade",
            data={"dadosPesq": RM_RECIFE_ID, "variavel": TIPO_UDH,
                  "page": pagina, "_token": token},
        )
        udhs.extend({"id": d["id"], "nome": d["n"]} for d in data["data"])
        if pagina >= data["last_page"]:
            return udhs
        pagina += 1


def baixar_idhm(session: requests.Session, token: str, ids: List[int]) -> dict:
    """IDHM 2010 e população total das UDHs informadas."""
    payload = {
        "territorialidades": {
            "entidades": [{
                "e": TIPO_GRID_UDH, "mun": [], "rm": [], "est": [], "udh": [], "l": ids,
            }],
        },
        "indicadores": {
            "cod_indicadores": [
                {"id_indicador": INDICADOR_IDHM, "id_ano": ANO_2010_ID},
                {"id_indicador": INDICADOR_POPULACAO, "id_ano": ANO_2010_ID},
            ],
            "data_desagregacoes": [],
        },
        "pagination": {"current_page": 1, "last_page": 0, "per_page": 1000,
                       "total": 0, "from": 0, "to": 0},
        "ordenation": {"default": "asc"},
    }
    return _post(session, token, "/api/dadosgrid", json=payload)


def mapear_bairros(nome_udh: str, nomes_bairro: List[str],
                   indice: Dict[str, str]) -> List[str]:
    """Extrai os bairros citados no nome oficial da UDH."""
    base = nome_udh.split(" (Recife,")[0]
    base = base.split(" : ")[0]
    base = re.sub(r"\s*\([^)]*\)\s*$", "", base)
    bairros = []
    for parte in (p.strip() for p in base.split("/")):
        if not parte:
            continue
        chave = _normalize(parte)
        if chave in indice:
            bairros.append(indice[chave])
            continue
        candidatos = [b for b in nomes_bairro if _normalize(b) in chave]
        if not candidatos:
            raise ValueError(f"UDH sem bairro correspondente: {nome_udh!r} ({parte!r})")
        bairros.append(max(candidatos, key=len))
    return bairros


def agregar(udhs: List[dict], nomes_bairro: List[str]) -> Tuple[Dict[str, dict], List[dict]]:
    indice = {_normalize(n): n for n in nomes_bairro}
    soma = {b: 0.0 for b in nomes_bairro}
    peso = {b: 0.0 for b in nomes_bairro}
    contagem = {b: 0 for b in nomes_bairro}

    registros = []
    for udh in udhs:
        bairros = mapear_bairros(udh["nome"], nomes_bairro, indice)
        registros.append({
            "id": udh["id"],
            "nome": udh["nome"],
            "bairros": bairros,
            "idhm": udh["idhm"],
            "populacao": udh["populacao"],
        })
        cota = udh["populacao"] / len(bairros)
        for bairro in bairros:
            soma[bairro] += udh["idhm"] * cota
            peso[bairro] += cota
            contagem[bairro] += 1

    faltando = [b for b in nomes_bairro if peso[b] == 0]
    if faltando:
        raise ValueError(f"bairros sem UDH associada: {faltando}")

    bairros = {
        b: {"idh": round(soma[b] / peso[b], 4), "udhs": contagem[b]}
        for b in sorted(nomes_bairro)
    }
    return bairros, registros


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()

    with open(config.BAIRROS_LOOKUP_FILE, encoding="utf-8") as f:
        nomes_bairro = [b["nome"] for b in json.load(f)]

    print("[build_idh_atlas] Consultando o Atlas Brasil...")
    session, token = _sessao()

    udhs_rm = listar_udhs(session, token)
    print(f"  UDHs na RM Recife: {len(udhs_rm)}")

    grid = baixar_idhm(session, token, [u["id"] for u in udhs_rm])
    linhas = grid["data"][1:]  # primeira linha é o Brasil
    colunas = {c["id"]: i for i, c in enumerate(grid["columns"])}
    col_idhm = colunas[f"{INDICADOR_IDHM}_{ANO_2010_ID}"]
    col_pop = colunas[f"{INDICADOR_POPULACAO}_{ANO_2010_ID}"]

    udhs = []
    for linha in linhas:
        nome = linha[0]
        if f"({MUNICIPIO_RECIFE}," not in nome:
            continue
        udhs.append({
            "id": None,
            "nome": nome.split(f" ({MUNICIPIO_RECIFE},")[0],
            "idhm": _parse_numero(linha[col_idhm]),
            "populacao": _parse_populacao(linha[col_pop]),
        })

    # Recupera o id de cada UDH do Recife a partir do nome completo retornado.
    por_nome = {u["nome"].split(f" ({MUNICIPIO_RECIFE},")[0]: u["id"] for u in udhs_rm}
    for udh in udhs:
        udh["id"] = por_nome.get(udh["nome"])
    if any(u["id"] is None for u in udhs):
        raise RuntimeError("não foi possível casar ids das UDHs do Recife")

    bairros, registros = agregar(udhs, nomes_bairro)

    resultado = {
        "fonte": "Atlas do Desenvolvimento Humano no Brasil (PNUD, Ipea e FJP)",
        "url": ATLAS_CONSULTA_URL,
        "indicador": "IDHM — Índice de Desenvolvimento Humano Municipal (Censo 2010)",
        "ano_referencia": 2010,
        "agregacao": (
            "IDHM 2010 das UDHs do Recife agregado por bairro com média ponderada "
            "pela população; quando a UDH abrange mais de um bairro, sua população "
            "é dividida igualmente entre eles."
        ),
        "cobertura": {
            "udhs": len(registros),
            "bairros": len(bairros),
            "populacao_udhs": sum(r["populacao"] for r in registros),
        },
        "bairros": bairros,
        "udhs": sorted(registros, key=lambda r: r["id"]),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  UDHs do Recife: {len(registros)}")
    print(f"  Bairros cobertos: {len(bairros)}/{len(nomes_bairro)}")
    print(f"  IDHM: {min(b['idh'] for b in bairros.values()):.3f} a "
          f"{max(b['idh'] for b in bairros.values()):.3f}")
    print(f"  Salvo em: {args.output}")


if __name__ == "__main__":
    main()
