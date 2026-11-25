import numpy as np
import pandas as pd
import pytest

from app.ambiente import espacializacao as esp, estacoes
from app.shared.territorio import territorio_de

# Dois DS quadrados lado a lado; a fronteira de Thiessen entre as estações
# A e B (nos centros) coincide com a divisa dos DS.
DS1 = np.array([[-34.95, -8.06], [-34.93, -8.06], [-34.93, -8.04], [-34.95, -8.04], [-34.95, -8.06]])
DS2 = DS1 + [0.02, 0]
POLIGONOS = {"1": [DS1], "2": [DS2]}
GRADE = esp.grade_ds(POLIGONOS, passo=0.001)
ESTACOES = pd.DataFrame({"codigo": ["A", "B"], "latitude": [-8.05, -8.05], "longitude": [-34.94, -34.92]})
SEMANA = pd.date_range("2025-01-05", "2025-01-11").strftime("%Y-%m-%d").tolist()  # 2025-W02


def diario(valores):
    return pd.DataFrame([{"codigo": c, "data": d, "chuva_mm": v}
                         for c, serie in valores.items() for d, v in zip(SEMANA, serie) if v is not None])


def semanal(valores):
    df = esp.chuva_ds_semanal(esp.chuva_ds_diaria(diario(valores), ESTACOES, GRADE, SEMANA))
    return df.set_index("ds")


def test_cada_ds_recebe_a_chuva_da_propria_estacao():
    df = semanal({"A": [1] * 7, "B": [10] * 7})
    assert df.loc["1", "chuva_mm"] == pytest.approx(7)
    assert df.loc["2", "chuva_mm"] == pytest.approx(70)
    assert df["completa"].all()
    assert (df["falha"] == 0).all()


def test_falha_abaixo_do_limite_usa_estacao_vizinha_e_registra_a_falha():
    df = semanal({"A": [1] * 7, "B": [10, 10, None, 10, 10, 10, 10]})
    assert df.loc["2", "completa"]
    assert df.loc["2", "falha"] == pytest.approx(1 / 7)
    assert df.loc["2", "chuva_mm"] == pytest.approx(1 + 60)  # Dia sem B recebe a chuva de A.
    assert df.loc["1", "falha"] == 0


def test_semana_com_falha_acima_do_limite_fica_incompleta_e_sem_chuva():
    df = semanal({"A": [1] * 7, "B": [10, None, None, 10, 10, 10, 10]})
    assert df.loc["2", "falha"] == pytest.approx(2 / 7)
    assert not df.loc["2", "completa"]
    assert pd.isna(df.loc["2", "chuva_mm"])
    assert df.loc["1", "completa"]


def test_dia_sem_nenhuma_estacao_nao_vira_zero():
    df = semanal({"A": [1, 1, None, 1, 1, 1, 1], "B": [10, 10, None, 10, 10, 10, 10]})
    assert (df["dias_com_estimativa"] == 6).all()
    assert df["chuva_mm"].isna().all()


def test_estacao_antes_da_primeira_leitura_nao_conta_como_falha():
    df = semanal({"A": [1] * 7, "B": [None, None, None] + [10] * 4})
    # B ainda não operava: DS2 usa A sem falha (mas a distância média cresce).
    assert df.loc["2", "falha"] == 0
    assert df.loc["2", "chuva_mm"] == pytest.approx(3 + 40)


def test_lacuna_fora_dos_periodos_informados_nao_e_falha():
    valores = {"A": [1] * 7, "B": [10, None, None, None, None, None, 10]}
    sem_periodos = esp.chuva_ds_semanal(esp.chuva_ds_diaria(diario(valores), ESTACOES, GRADE, SEMANA))
    assert sem_periodos.set_index("ds").loc["2", "falha"] == pytest.approx(5 / 7)
    # Ex.: meses não baixados do CEMADEN; B só deveria ter medido no 1º e no 7º dia.
    periodos = pd.DataFrame({"codigo": ["A", "B", "B"], "inicio": [SEMANA[0], SEMANA[0], SEMANA[6]],
                             "fim": [SEMANA[6], SEMANA[0], SEMANA[6]]})
    df = esp.chuva_ds_semanal(esp.chuva_ds_diaria(diario(valores), ESTACOES, GRADE, SEMANA, periodos))
    assert df.set_index("ds").loc["2", "falha"] == 0


def test_pesos_thiessen_somam_um_por_ds():
    pesos = esp.pesos_thiessen(ESTACOES, GRADE)
    assert pesos.groupby("ds")["peso"].sum().tolist() == pytest.approx([1, 1])
    assert pesos.set_index("ds").loc["1", "codigo"] == "A"


def test_ds_de_ponto_dentro_e_fora_dos_poligonos():
    assert esp.ds_de_ponto(-8.05, -34.945, POLIGONOS, GRADE) == "1"
    assert esp.ds_de_ponto(-8.05, -34.85, POLIGONOS, GRADE) == "2"  # Fora: DS mais próximo.


def test_ds_reais_seguem_a_tabela_canonica_e_nao_o_codigo_do_gis():
    poligonos = esp.carregar_poligonos_ds()
    grade = esp.grade_ds(poligonos)
    assert sorted(set(grade.ds)) == [str(i) for i in range(1, 9)]
    # O GIS troca DS VII e VIII; o painel usa a tabela da Secretaria (territorio.py).
    assert esp.ds_de_ponto(-7.994, -34.936, poligonos, grade) == territorio_de("Guabiraba").ds == "8"
    assert esp.ds_de_ponto(-8.122, -34.955, poligonos, grade) == territorio_de("Ibura").ds == "7"


def test_rotulo_da_apac_nao_define_a_rede():
    assert estacoes.rotulo_apac("[CEMADEN 01] Várzea") == "CEMADEN"
    assert estacoes.rotulo_apac("[APAC] Guabiraba") == "APAC"
    assert estacoes.rotulo_apac("Recife (Várzea) [Convencional]") == "Convencional"
    apac = pd.DataFrame({"codigo": ["261160612A", "261160604V"],
                         "nome": ["[APAC] Guabiraba", "Alto da Brasileira [Convencional]"]})
    consolidado = pd.DataFrame({"codigo": ["261160612A", "261160604V"], "data": ["2024-01-01"] * 2,
                                "chuva_mm": [0.0, 0.0], "origem": ["APAC"] * 2})
    cadastro = pd.DataFrame({"codigo": ["261160612A"], "nome": ["Guabiraba"],
                             "latitude": [-7.994], "longitude": [-34.936]})
    # A sede da APAC (623A) também aparece no download do CEMADEN: continua sendo rede APAC.
    download = pd.DataFrame({"codigo": ["261160623A"], "nome": ["RECIFE - APAC"],
                             "latitude": [-8.04491], "longitude": [-34.87518]})
    inv = estacoes.montar_inventario(apac, consolidado, cadastro, download, POLIGONOS, GRADE).set_index("codigo")
    assert inv.loc["261160612A", ["rede", "rotulo_apac"]].tolist() == ["CEMADEN", "APAC"]
    assert inv.loc["261160604V", ["rede", "tipo"]].tolist() == ["APAC", "convencional"]
    assert inv.loc["261160604V", "fonte_coordenada"].startswith("APAC, Atlas")
    assert inv.loc["261160623A", ["rede", "publicada_cemaden"]].tolist() == ["APAC", True]


def test_estacao_com_leitura_e_sem_coordenada_interrompe_inventario():
    apac = pd.DataFrame({"codigo": ["261160699A"], "nome": ["Nova"]})
    consolidado = pd.DataFrame({"codigo": ["261160699A"], "data": ["2024-01-01"],
                                "chuva_mm": [0.0], "origem": ["APAC"]})
    vazio = pd.DataFrame(columns=["codigo", "nome", "latitude", "longitude"])
    with pytest.raises(ValueError, match="sem coordenadas"):
        estacoes.montar_inventario(apac, consolidado, vazio, vazio, POLIGONOS, GRADE)


def test_serie_por_estacao_exige_sete_dias_e_conta_dias_cemaden():
    consolidado = diario({"A": [1] * 7, "B": [None] + [2] * 6}).assign(origem="APAC")
    consolidado.loc[consolidado.index[0], "origem"] = "CEMADEN"
    df = estacoes.serie_semanal(consolidado).set_index("codigo")
    assert df.loc["A", ["chuva_mm", "dias", "dias_cemaden"]].tolist() == [7, 7, 1]
    assert pd.isna(df.loc["B", "chuva_mm"]) and df.loc["B", "dias"] == 6
