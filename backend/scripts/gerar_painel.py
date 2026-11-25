"""
Regenera os painéis bairro x SE e DS x SE a partir das fontes (SINAN cache +
APAC/clima), valida o schema (app/shared/painel_schema.py) e grava um data
card (fonte, cobertura, versão). É o "um comando" pedido pela US14 — roda
independente de treino (scripts/train_forecast.py cuida disso).

Uso:
    python scripts/gerar_painel.py
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.services import forecast_features as ff
from app.shared import painel_schema

SAIDA_DIR = config.DATA_DIR / "painel"
FONTE_CLIMA = "APAC (chuva) + Open-Meteo (temperatura)"


def _hash_df(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:12]


def main():
    anos = config.FORECAST_ANOS
    print(f"[gerar_painel] Construindo painel bairro x SE para {anos}...")
    panel = ff.build_panel(anos)
    bairro_df = ff.add_features(panel)
    ds_df = ff.add_features_ds(ff.build_panel_ds(panel))

    painel_schema.validar_painel_bairro(bairro_df)
    painel_schema.validar_painel_ds(ds_df)
    print(f"   bairro x SE: {bairro_df['bairro'].nunique()} bairros x {bairro_df['semana'].nunique()} semanas")
    print(f"   DS x SE: {ds_df['ds'].nunique()} DS x {ds_df['semana'].nunique()} semanas")

    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    versao = f"{_hash_df(bairro_df)}-{_hash_df(ds_df)}"
    bairro_path = SAIDA_DIR / "painel_bairro_se.csv"
    ds_path = SAIDA_DIR / "painel_ds_se.csv"
    bairro_df.to_csv(bairro_path, index=False)
    ds_df.to_csv(ds_path, index=False)

    data_card = {
        "versao": versao,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "fontes": {
            "casos": "SINAN (cache local, backend/app/data/cache/dengue_*.csv)",
            "clima": FONTE_CLIMA,
            "territorio": "distritos_sanitarios_*.csv + bairros_lookup.json (app/shared/territorio.py)",
        },
        "cobertura": {
            "anos": anos,
            "semana_min": int(bairro_df["semana"].min()),
            "semana_max": int(bairro_df["semana"].max()),
            "n_bairros": int(bairro_df["bairro"].nunique()),
            "n_ds": int(ds_df["ds"].nunique()),
        },
        "dados_coleta": panel.attrs.get("snapshot_meta", {}),
        "arquivos": {
            "painel_bairro_se": bairro_path.name,
            "painel_ds_se": ds_path.name,
        },
    }
    (SAIDA_DIR / "data_card.json").write_text(
        json.dumps(data_card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[gerar_painel] versão {versao} salva em {SAIDA_DIR}")


if __name__ == "__main__":
    main()
