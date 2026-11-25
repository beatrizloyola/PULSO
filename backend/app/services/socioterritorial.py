"""Referências socioterritoriais por bairro.

O IDH vem do Atlas do Desenvolvimento Humano no Brasil (PNUD/Ipea/FJP), que
publica o IDHM no nível de Unidade de Desenvolvimento Humano (UDH). O arquivo
`idh_atlas_2010.json` traz a agregação para os 94 bairros do Recife, gerada por
`scripts/build_idh_atlas.py`. O dado é do Censo 2010 e serve como contexto
socioeconômico — não é variável do modelo de previsão.
"""
import json
import logging
import unicodedata

from app import config

log = logging.getLogger(__name__)

IDH_FILE = config.DATA_DIR / "idh_atlas_2010.json"

_cache = {"assinatura": None, "dados": None}
_avisou_ausencia = False


def _norm(valor) -> str:
    """Remove acentos e normaliza para maiúsculas (mesmo padrão do lookup)."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).upper().strip()


def _carregar() -> dict:
    global _avisou_ausencia
    if not IDH_FILE.exists():
        if not _avisou_ausencia:
            log.warning("%s não encontrado — idh virá null em todas as respostas. "
                        "Gere com: python -m scripts.build_idh_atlas", IDH_FILE)
            _avisou_ausencia = True
        return {}
    assinatura = IDH_FILE.stat().st_mtime_ns
    if _cache["dados"] is None or _cache["assinatura"] != assinatura:
        with open(IDH_FILE, encoding="utf-8") as f:
            _cache["dados"] = json.load(f)
        _cache["assinatura"] = assinatura
    return _cache["dados"]


def disponivel() -> bool:
    """Para o /health: o arquivo de IDH existe e tem bairros carregados."""
    return bool(_carregar().get("bairros"))


def referencia() -> dict:
    """Metadados da fonte para o cabeçalho das respostas da API."""
    dados = _carregar()
    if not dados:
        return {}
    return {
        "ano": dados.get("ano_referencia"),
        "fonte": dados.get("fonte"),
        "url": dados.get("url"),
        "indicador": dados.get("indicador"),
        "agregacao": dados.get("agregacao"),
        "cobertura": dados.get("cobertura"),
    }


def por_bairro(nome: str):
    """Retorna {'idh': float, 'udhs': int} para o bairro, ou None."""
    bairros = _carregar().get("bairros", {})
    if not bairros:
        return None
    chave = _norm(nome)
    if chave in bairros:
        return bairros[chave]
    for nome_bairro, valores in bairros.items():
        if _norm(nome_bairro) == chave:
            return valores
    return None
