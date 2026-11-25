#!/usr/bin/env python3
"""
Temperatura do ar semanal de Recife, anos epidemiológicos 2016-2025 (US10).

Fonte: Open-Meteo Historical Weather API (reanálise ERA5/ERA5-Land), o mesmo
endpoint e ponto (RECIFE_LAT/RECIFE_LON) usados pela coleta do servidor.
Diário em America/Recife -> semana epidemiológica CDC.

Saídas (backend/app/data/):
  temperatura_se_2016_2025.csv   semana, temp_media, temp_max, temp_max_abs, dias
  temperatura_se_report.json     fonte, parâmetros, ponto da grade, hash, cobertura
Cache (não versionado): resposta bruta em cache/openmeteo_temperatura_<inicio>_<fim>.json

Uso:
  python scripts/build_temperatura_historica.py [--refresh]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from epiweeks import Week, Year

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.ambiente import temperatura
from app.services import data_sync

ANOS = range(2016, 2026)
INICIO = Week(ANOS[0], 1, system="cdc").startdate()
FIM = Year(ANOS[-1], system="cdc").enddate()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="baixa de novo a resposta do Open-Meteo")
    args = parser.parse_args()
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache = config.CACHE_DIR / f"openmeteo_temperatura_{INICIO}_{FIM}.json"
    if args.refresh or not cache.exists():
        print(f"[Open-Meteo] baixando {INICIO} a {FIM}...")
        with requests.Session() as session:
            session.headers["User-Agent"] = "PULSO/1.0 (pesquisa; dados publicos Recife)"
            _, payload = data_sync.download_temperatures(session, INICIO, FIM)
        cache.write_text(json.dumps(payload), encoding="utf-8")
    bruto = cache.read_bytes()
    payload = json.loads(bruto)
    diario = data_sync.parse_temperatures(payload, INICIO, FIM)
    semanal = temperatura.agregar_semanal(diario)

    saida = config.DATA_DIR / "temperatura_se_2016_2025.csv"
    semanal.round(2).to_csv(saida, index=False)
    report = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "fonte": {
            "nome": "Open-Meteo Historical Weather API (reanálise ERA5/ERA5-Land)",
            "url": config.OPENMETEO_ARCHIVE_URL,
            "parametros": {"latitude": config.RECIFE_LAT, "longitude": config.RECIFE_LON,
                           "daily": "temperature_2m_mean,temperature_2m_max",
                           "timezone": "America/Recife", "start_date": str(INICIO), "end_date": str(FIM)},
            "ponto_grade": {k: payload.get(k) for k in ("latitude", "longitude", "elevation")},
            "unidades": payload.get("daily_units"),
            "arquivo_cache": cache.name, "sha256": hashlib.sha256(bruto).hexdigest(),
            "baixado_em": datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc).isoformat(),
            "atribuicao": "Weather data by Open-Meteo.com (CC BY 4.0)",
        },
        "cobertura": {
            "semana_min": int(semanal["semana"].min()), "semana_max": int(semanal["semana"].max()),
            "semanas": int(len(semanal)), "semanas_incompletas": int((semanal["dias"] != 7).sum()),
            "dias_sem_valor": int(diario[["temp_media", "temp_max"]].isna().any(axis=1).sum()),
        },
        "definicoes": {
            "temp_media": "média das temperaturas médias diárias (°C)",
            "temp_max": "média das máximas diárias (°C), mesma definição do modelo",
            "temp_max_abs": "maior máxima diária da semana (°C)",
        },
    }
    caminho = config.DATA_DIR / "temperatura_se_report.json"
    caminho.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("salvo:", saida, "|", len(semanal), "semanas")
    print("salvo:", caminho)


if __name__ == "__main__":
    main()
