#!/usr/bin/env python3
"""
Chuva por estação e por Distrito Sanitário, APAC + CEMADEN, 2016-2025 (US05/US06/US07).

Fontes:
  APAC   Histórico Pluviométrico diário de Recife (mesmo formulário de
         app/services/apac_client.py), uma consulta por ano civil.
  CEMADEN  CSVs mensais do Mapa Interativo ("Download - Dados Pluviométricos"),
         baixados manualmente (captcha) em backend/app/data/cache/cemaden/ (UF ou
         município). O script extrai só as linhas de Recife, no formato oficial, para
         backend/app/data/cemaden_recife/cemaden_recife_AAAA_MM.csv.gz (versionado) e lê
         a série desses extratos. Cadastro de estações baixado de resources.cemaden.gov.br.

Período: anos epidemiológicos CDC 2016-2025 (2016-01-03 a 2026-01-03).

Saídas (backend/app/data/):
  estacoes_chuva_recife.csv       inventário: código, nome, lat/lon, rede, período, DS
  chuva_estacao_se_2016_2025.csv  estação x SE: chuva_mm, dias, dias_cemaden
  chuva_ds_se_2016_2025.csv       DS x SE: chuva_mm (Thiessen), completa, falha, ...
  chuva_estacoes_report.json      proveniência, método, cobertura e reconciliação
Cache (não versionado): HTMLs da APAC, cadastro CEMADEN e o diário consolidado
  (cache/chuva_estacao_dia.csv, com a flag de origem por medição).

Uso:
  python scripts/build_chuva_estacoes.py [--refresh] [--cemaden-dir DIR]
"""
import argparse
import gzip
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from epiweeks import Week, Year

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.ambiente import espacializacao, estacoes, reconciliacao
from app.ingestao import cemaden
from app.services import apac_client

ANOS = range(2016, 2026)
INICIO = Week(ANOS[0], 1, system="cdc").startdate()
FIM = Year(ANOS[-1], system="cdc").enddate()
USER_AGENT = "PULSO/1.0 (pesquisa; dados publicos Recife)"
EXTRATOS_CEMADEN = config.DATA_DIR / "cemaden_recife"


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _consultas_apac():
    for ano in range(INICIO.year, FIM.year + 1):
        yield max(INICIO, date(ano, 1, 1)), min(FIM, date(ano, 12, 31))


def carregar_apac(session, refresh):
    leituras, consultas = [], []
    for inicio, fim in _consultas_apac():
        cache = config.CACHE_DIR / f"apac_diario_{inicio}_{fim}.html"
        if refresh or not cache.exists():
            print(f"[APAC] baixando {inicio} a {fim}...")
            _, html = apac_client.download_diario(session, inicio, fim)
            cache.write_text(html, encoding="utf-8")
        html = cache.read_text(encoding="utf-8")
        df = apac_client.parse_diario(html, inicio, fim)
        leituras.append(df)
        consultas.append({"inicio": str(inicio), "fim": str(fim), "arquivo": cache.name,
                          "sha256": _sha256(html.encode("utf-8")), "estacoes": int(df["estacao"].nunique())})
    df = pd.concat(leituras, ignore_index=True).rename(columns={"estacao": "codigo"})
    return df[["codigo", "nome", "data", "chuva_mm"]], consultas


def carregar_cadastro(session, refresh):
    cache = config.CACHE_DIR / "cemaden_cadastro_estacoes.jsonp"
    if refresh or not cache.exists():
        print("[CEMADEN] baixando cadastro de estações...")
        response = session.get(cemaden.CADASTRO_URL, timeout=(10, 60))
        response.raise_for_status()
        cache.write_bytes(response.content)
    bruto = cache.read_bytes()
    return cemaden.parse_cadastro(bruto.decode("utf-8")), {
        "url": cemaden.CADASTRO_URL, "arquivo": cache.name, "sha256": _sha256(bruto),
        "baixado_em": datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc).isoformat()}


def extrair_downloads(pasta: Path):
    """Downloads brutos (UF ou município) -> um extrato mensal versionado, só Recife."""
    EXTRATOS_CEMADEN.mkdir(exist_ok=True)
    for arquivo in sorted(pasta.glob("*.csv")) if pasta.exists() else []:
        texto = cemaden.extrair_recife(cemaden.ler_texto(arquivo))
        horarios = cemaden.parse_download(texto)["data_hora_utc"]
        destino = EXTRATOS_CEMADEN / f"cemaden_recife_{horarios.median():%Y_%m}.csv.gz"
        conteudo = gzip.compress(texto.encode("utf-8"), mtime=0)  # mtime fixo: bytes reprodutíveis
        if not destino.exists() or destino.read_bytes() != conteudo:
            destino.write_bytes(conteudo)
            print(f"[CEMADEN] extrato {destino.name} <- {arquivo.name}")


def carregar_cemaden():
    """Leituras dos extratos versionados e o intervalo de datas de cada um."""
    arquivos = sorted(EXTRATOS_CEMADEN.glob("*.csv.gz"))
    partes, janelas, proveniencia = [], [], []
    for arquivo in arquivos:
        leituras = cemaden.ler_download(arquivo)
        datas = leituras["data_hora_utc"].dt.strftime("%Y-%m-%d")
        partes.append(leituras)
        janelas.append((datas.min(), datas.max()))
        proveniencia.append({"arquivo": arquivo.name, "sha256": _sha256(arquivo.read_bytes()),
                             "de": datas.min(), "ate": datas.max(),
                             "estacoes_recife": int(leituras["codigo"].nunique())})
    return cemaden.juntar_leituras(partes), janelas, proveniencia


def _cobertura_ds(ds_semanal):
    df = ds_semanal.assign(ano=ds_semanal["semana"] // 100)
    return [{"ano": int(ano), "pct_semanas_completas": round(100 * g["completa"].mean(), 1),
             "falha_media": round(g["falha"].mean(), 3),
             "dist_media_km": round(g["dist_media_km"].mean(), 2) if g["dist_media_km"].notna().any() else None}
            for ano, g in df.groupby("ano")]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="baixa de novo APAC e cadastro CEMADEN")
    parser.add_argument("--cemaden-dir", type=Path, default=config.CACHE_DIR / "cemaden",
                        help="pasta com os downloads brutos do CEMADEN a extrair (UF ou município)")
    args = parser.parse_args()
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        apac, consultas_apac = carregar_apac(session, args.refresh)
        cadastro, prov_cadastro = carregar_cadastro(session, args.refresh)
    extrair_downloads(args.cemaden_dir)
    leituras_cemaden, janelas_cemaden, arquivos_cemaden = carregar_cemaden()
    cemaden_diario = cemaden.agregar_diario(leituras_cemaden)
    periodo = (cemaden_diario["data"] >= str(INICIO)) & (cemaden_diario["data"] <= str(FIM))
    cemaden_diario = cemaden_diario[periodo]
    print(f"[APAC] {len(apac)} leituras, {apac['codigo'].nunique()} estações")
    print(f"[CEMADEN] {len(arquivos_cemaden)} arquivo(s), {len(leituras_cemaden)} leituras, "
          f"{cemaden_diario['chuva_mm'].notna().sum()} estação-dias completos")

    consolidado_bruto = reconciliacao.consolidar(apac, cemaden_diario)
    poligonos = espacializacao.carregar_poligonos_ds()
    grade = espacializacao.grade_ds(poligonos)
    coords_download = cemaden.coordenadas_download(leituras_cemaden)
    inventario = estacoes.montar_inventario(apac, consolidado_bruto, cadastro, coords_download, poligonos, grade)
    consolidado, sensor_seco, sem_vizinhas = reconciliacao.filtrar_sensor_seco(consolidado_bruto, inventario)
    print(f"[QC] sensor seco: {len(sensor_seco)} trecho(s), "
          f"{sum(t['dias_removidos'] for t in sensor_seco)} estação-dias removidos")
    # Inventário refeito para que período e dias_com_leitura não contem os dias removidos.
    inventario = estacoes.montar_inventario(apac, consolidado, cadastro, coords_download, poligonos, grade)

    datas = pd.date_range(INICIO, FIM).strftime("%Y-%m-%d").tolist()
    periodos = reconciliacao.periodos_operacao(apac, cemaden_diario, janelas_cemaden)
    ds_diario = espacializacao.chuva_ds_diaria(consolidado, inventario, grade, datas, periodos)
    ds_semanal = espacializacao.chuva_ds_semanal(ds_diario)
    estacao_semanal = estacoes.serie_semanal(consolidado)
    com_leitura = inventario[inventario["dias_com_leitura"] > 0]
    pares = reconciliacao.comparar_pares_proximos(consolidado, inventario)

    report = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "periodo": {"inicio": str(INICIO), "fim": str(FIM), "anos_epidemiologicos": [ANOS[0], ANOS[-1]]},
        "fontes": {
            "apac": {"portal": config.APAC_PORTAL_URL, "consulta": config.APAC_HISTORICO_DIARIO_URL,
                     "consultas": consultas_apac},
            "cemaden": {"download": cemaden.DOWNLOAD_URL, "arquivos": arquivos_cemaden,
                        "cadastro": prov_cadastro},
            "ds": "bairros_esig.geojson agrupados pelo DS de territorio_de (tabela da Secretaria de Saúde)",
        },
        "metodo": {
            "precedencia": "APAC; CEMADEN só preenche estação-dia ausente na APAC (mesmo código)",
            "dia_cemaden": f"dia D termina {cemaden.FIM_DIA_UTC_H}h UTC após 00h UTC de D (07h local, "
                           f"como a APAC); mínimo de {cemaden.HORAS_MIN_DIA} horas com transmissão; "
                           f"dia com leitura > {cemaden.MAX_MM_LEITURA:g} mm fica ausente",
            "dias_leitura_suspeita": cemaden_diario.loc[cemaden_diario["leitura_suspeita"].astype(bool),
                                                        ["codigo", "data"]].to_dict("records"),
            "espacializacao": "Thiessen discretizado por DS, recalculado por dia com as estações que mediram",
            "passo_grade_graus": espacializacao.PASSO_GRAUS, "pontos_grade": int(len(grade.ds)),
            "limite_falha": espacializacao.LIMITE_FALHA,
            "silencio_encerra_operacao_dias": reconciliacao.SILENCIO_MAX_DIAS,
            "sensor_seco": {
                "regra": f"janela de {reconciliacao.JANELA_SECO_DIAS} dias (>= {reconciliacao.MIN_DIAS_JANELA_SECO} "
                         f"leituras) com chuva < {reconciliacao.RAZAO_SECO:g} x mediana das vizinhas a até "
                         f"{reconciliacao.RAIO_SECO_KM:g} km (>= {reconciliacao.MIN_VIZINHAS_SECO}; senão, mediana "
                         f"da cidade), quando a referência soma >= {reconciliacao.MIN_MM_VIZINHAS_SECO:g} mm: "
                         f"dias da janela removidos",
                "trechos_removidos": sensor_seco,
                "estacoes_sem_vizinha_no_raio": sem_vizinhas,
            },
        },
        "estacoes": {"inventario": int(len(inventario)), "com_leitura": int(len(com_leitura)),
                     "por_rede": com_leitura["rede"].value_counts().to_dict()},
        "pesos_thiessen_rede_completa": espacializacao.pesos_thiessen(com_leitura, grade).round(4).to_dict("records"),
        "cobertura_por_ano": reconciliacao.resumo_origem(consolidado),
        "cobertura_ds_por_ano": _cobertura_ds(ds_semanal),
        "reconciliacao": {
            "estacoes_duplicadas": reconciliacao.comparar_duplicadas(apac, cemaden_diario),
            "convencoes_dia": reconciliacao.comparar_convencoes(apac, leituras_cemaden, inventario)
            if not leituras_cemaden.empty else [],
            "raio_pares_km": reconciliacao.RAIO_PAR_KM,
            "pares_proximos": pares,
            "correlacao_revisar_abaixo_de": reconciliacao.CORRELACAO_REVISAR,
            "estacoes_vs_vizinhas": reconciliacao.resumo_vizinhas(pares),
        },
    }

    saidas = {
        "estacoes_chuva_recife.csv": inventario,
        "chuva_estacao_se_2016_2025.csv": estacao_semanal,
        "chuva_ds_se_2016_2025.csv": ds_semanal.round({"chuva_mm": 2, "falha": 4, "dist_media_km": 3}),
    }
    for nome, df in saidas.items():
        df.to_csv(config.DATA_DIR / nome, index=False)
        print("salvo:", config.DATA_DIR / nome, "|", len(df), "linhas")
    consolidado.to_csv(config.CACHE_DIR / "chuva_estacao_dia.csv", index=False)
    caminho = config.DATA_DIR / "chuva_estacoes_report.json"
    caminho.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("salvo:", caminho)
    for linha in report["cobertura_ds_por_ano"]:
        print(f"  {linha['ano']}: {linha['pct_semanas_completas']}% DS-semanas completas, "
              f"falha média {linha['falha_media']}")


if __name__ == "__main__":
    main()
