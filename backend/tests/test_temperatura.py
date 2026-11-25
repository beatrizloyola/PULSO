from datetime import date

import pandas as pd
import pytest

from app.ambiente import temperatura
from app.services import data_sync


def diario(inicio="2024-12-29", fim="2025-01-04"):
    dias = pd.date_range(inicio, fim).strftime("%Y-%m-%d")
    return pd.DataFrame({"data": dias, "temp_media": [26, 27, 28, 27, 26, 27, 28],
                         "temp_max": [29, 30, 33, 30, 29, 30, 31]})


def test_semana_cdc_media_e_maximas():
    [semana] = temperatura.agregar_semanal(diario()).to_dict("records")
    assert semana["semana"] == 202501  # Atravessa a virada do ano.
    assert semana["temp_media"] == pytest.approx(27)
    assert semana["temp_max"] == pytest.approx(212 / 7)  # Média das máximas (definição do modelo).
    assert semana["temp_max_abs"] == 33
    assert semana["dias"] == 7


def test_semana_sem_os_sete_dias_fica_sem_valor():
    df = diario()
    df.loc[2, "temp_max"] = None
    [semana] = temperatura.agregar_semanal(df).to_dict("records")
    assert semana["dias"] == 6
    assert pd.isna(semana["temp_media"]) and pd.isna(semana["temp_max_abs"])


def test_resposta_open_meteo_com_lacuna_de_datas_e_rejeitada():
    payload = {"daily": {"time": ["2025-01-01", "2025-01-03"],
                         "temperature_2m_mean": [27, 27], "temperature_2m_max": [30, 30]}}
    with pytest.raises(ValueError, match="período retornado"):
        data_sync.parse_temperatures(payload, date(2025, 1, 1), date(2025, 1, 3))
