from datetime import date

import pandas as pd
import pytest

from app import config
from app.shared.semana_epidemiologica import SemanaEpidemiologica
from app.shared.territorio import (
    BairroDesconhecidoError,
    normalizar_nome_bairro,
    territorio_de,
    todos_territorios,
    validar_cobertura_total,
)


def test_94_bairros_mapeados_para_8_ds():
    territorios = todos_territorios()
    assert len(territorios) == 94
    assert {t.ds for t in territorios} == {str(i) for i in range(1, 9)}


def test_ds_bate_com_csv_oficial():
    caminho = next(config.DATA_DIR.glob("distritos_sanitarios_*.csv"))
    df = pd.read_csv(caminho, sep=";", encoding="utf-8")
    for _, linha in df.iterrows():
        t = territorio_de(linha["bairro"])
        assert t.ds == str(linha["distrito_sanitario"]).strip()


def test_rpa_derivada_do_ds():
    assert territorio_de("Boa Vista").rpa == "RPA 1"  # DS 1
    assert territorio_de("Ibura").rpa == "RPA 6"  # DS 8


@pytest.mark.parametrize("variante", ["agua fria", "ÁGUA FRIA", "  Agua Fria  ", "AGUA FRIA"])
def test_normalizacao_ignora_acento_caixa_espacos(variante):
    assert normalizar_nome_bairro(variante) == normalizar_nome_bairro("Água Fria")
    assert territorio_de(variante).ds == territorio_de("Água Fria").ds


def test_bairro_desconhecido_levanta_erro_claro():
    with pytest.raises(BairroDesconhecidoError):
        territorio_de("Bairro Que Nao Existe")


def test_validar_cobertura_total_aceita_nomes_do_sinan():
    # "BAIRRO IGNORADO" é sentinela do SINAN para casos sem bairro atribuído,
    # não é um bairro real — não deve (nem pode) mapear para DS.
    bairros_csv = next(config.DATA_DIR.glob("dengue_tabela_de_bairros.csv"))
    nomes_sinan = pd.read_csv(bairros_csv, sep=";", encoding="utf-8")["Nome Localidade"].tolist()
    nomes_sinan = [n for n in nomes_sinan if normalizar_nome_bairro(n) != "BAIRRO IGNORADO"]
    validar_cobertura_total(nomes_sinan)


def test_validar_cobertura_total_falha_com_bairro_sem_ds():
    with pytest.raises(BairroDesconhecidoError, match="1 bairro"):
        validar_cobertura_total(["Boa Vista", "Bairro Inventado"])


def test_semana_epidemiologica_de_data():
    se = SemanaEpidemiologica.de_data(date(2025, 1, 1))
    assert se.ano == se.codigo // 100
    assert 1 <= se.semana <= 53


def test_semana_epidemiologica_soma_horizonte():
    base = SemanaEpidemiologica.de_ano_semana(2025, 20)
    assert base + 1 == SemanaEpidemiologica.de_ano_semana(2025, 21)
    assert base + 4 - 4 == base


def test_semana_epidemiologica_rejeita_semana_inexistente_no_ano():
    # 2026 tem 52 semanas CDC, não 53 — construir já deve falhar, não só na aritmética.
    with pytest.raises(ValueError):
        SemanaEpidemiologica.de_ano_semana(2026, 53)


def test_semana_epidemiologica_ordenavel():
    a = SemanaEpidemiologica.de_ano_semana(2024, 52)
    b = SemanaEpidemiologica.de_ano_semana(2025, 1)
    assert a < b
