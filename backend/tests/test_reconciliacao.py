import pandas as pd
import pytest

from app.ambiente import reconciliacao as rec

DIAS = pd.date_range("2024-03-01", "2024-03-10").strftime("%Y-%m-%d").tolist()


def leituras(codigo, valores, dias=DIAS):
    return pd.DataFrame({"codigo": codigo, "data": dias[:len(valores)], "chuva_mm": valores})


def test_apac_tem_precedencia_e_cemaden_so_preenche_lacuna_da_mesma_estacao():
    apac = leituras("X", [1.0, None, 3.0])
    cemaden = pd.concat([leituras("X", [9.0, 2.0, 9.0, None]), leituras("Y", [5.0])])
    df = rec.consolidar(apac, cemaden).set_index(["codigo", "data"])
    assert df.loc[("X", DIAS[0]), ["chuva_mm", "origem"]].tolist() == [1.0, "APAC"]
    assert df.loc[("X", DIAS[1]), ["chuva_mm", "origem"]].tolist() == [2.0, "CEMADEN"]
    assert df.loc[("X", DIAS[2]), "origem"] == "APAC"
    assert ("X", DIAS[3]) not in df.index  # Dia incompleto no CEMADEN não vira leitura.
    assert df.loc[("Y", DIAS[0]), "origem"] == "CEMADEN"
    assert not df.index.duplicated().any()


def test_periodo_cemaden_fica_restrito_aos_meses_baixados():
    apac = leituras("X", [1.0, 1.0], dias=["2024-02-01", "2024-02-02"])
    cemaden = pd.concat([leituras("X", [1.0, 1.0], dias=["2016-01-05", "2016-03-20"]),
                         leituras("Y", [1.0], dias=["2016-03-10"])])
    janelas = [("2016-01-01", "2016-01-31"), ("2016-03-01", "2016-03-31")]  # Fevereiro não baixado.
    periodos = rec.periodos_operacao(apac, cemaden, janelas)
    assert sorted(map(tuple, periodos.values.tolist())) == [
        ("X", "2016-01-05", "2016-01-31"), ("X", "2016-03-01", "2016-03-20"),
        ("X", "2024-02-01", "2024-02-02"), ("Y", "2016-03-10", "2016-03-10")]


def test_silencio_longo_encerra_periodo_de_operacao():
    apac = leituras("X", [1.0, 1.0, 0.0], dias=["2020-01-01", "2020-01-02", "2022-06-01"])
    periodos = rec.periodos_operacao(apac, leituras("Y", []), [])
    assert sorted(map(tuple, periodos.values.tolist())) == [
        ("X", "2020-01-01", "2020-01-02"), ("X", "2022-06-01", "2022-06-01")]


def test_sensor_seco_e_removido_e_vizinhas_mantidas():
    dias = pd.date_range("2023-01-01", periods=60).strftime("%Y-%m-%d").tolist()
    chuva = [0.0] * 30 + [2.0] * 30  # Mês seco, depois mês chuvoso.
    consolidado = pd.concat([leituras("A", chuva, dias), leituras("B", chuva, dias),
                             leituras("C", [0.0] * 60, dias), leituras("D", [0.0] * 60, dias)])
    inventario = pd.DataFrame({"codigo": ["A", "B", "C", "D"], "latitude": [-8.0, -8.001, -8.002, -8.5],
                               "longitude": [-34.9] * 4})
    mantido, trechos, nao_checadas = rec.filtrar_sensor_seco(consolidado, inventario)
    restante_c = mantido.loc[mantido["codigo"] == "C", "data"]
    assert len(restante_c) > 0 and restante_c.max() < dias[30]  # Zeros do mês seco ficam.
    assert (mantido["codigo"] == "A").sum() == 60 and (mantido["codigo"] == "B").sum() == 60
    assert [t["codigo"] for t in trechos] == ["C", "D"] and trechos[0]["fim"] == dias[-1]
    assert nao_checadas == ["D"]  # Sem vizinha no raio: comparada com a mediana da cidade.


def test_duplicata_identica_concorda_e_divergencia_e_contada():
    apac = leituras("X", [0.0, 5.0, 10.0, 0.2])
    cemaden = leituras("X", [0.0, 5.0, 20.0, 0.2])
    [r] = rec.comparar_duplicadas(apac, cemaden)
    assert r["dias_comuns"] == 4
    assert r["pct_concordancia"] == 75.0
    assert r["dias_divergentes"] == 1
    assert r["vies_mm"] == 2.5


def subdiarias(chuva_por_hora_utc):
    """Leituras horárias contínuas de 2024-03-01 04h UTC a 2024-03-06 03h UTC."""
    horas = pd.date_range("2024-03-01 04:00", "2024-03-06 03:00", freq="h")
    return pd.DataFrame({"codigo": "X", "data_hora_utc": horas,
                         "chuva_mm": [chuva_por_hora_utc.get(h, 0.0) for h in horas]})


def test_convencao_de_dia_que_bate_com_a_apac_e_identificada():
    # 14h UTC (11h local) de 03/03 é dia 03/03 no dia civil e 04/03 no dia que fecha às 07h.
    sub = subdiarias({pd.Timestamp("2024-03-02 08:00"): 5.0, pd.Timestamp("2024-03-03 14:00"): 8.0,
                      pd.Timestamp("2024-03-04 20:00"): 3.0})
    apac_07h = [5.0, 0.0, 8.0, 3.0]
    # X é publicada pelas duas fontes; V é um posto convencional da APAC a ~1 km.
    apac = pd.concat([leituras("X", apac_07h, dias=DIAS[1:]), leituras("V", apac_07h, dias=DIAS[1:])])
    inventario = pd.DataFrame({"codigo": ["X", "V"], "latitude": [-8.05, -8.05], "longitude": [-34.90, -34.91]})
    resultado = {c["fim_dia_utc_h"]: c for c in rec.comparar_convencoes(apac, sub, inventario, min_dias=3)}
    assert resultado[10]["pct_concordancia_duplicadas"] == 100.0
    assert resultado[27]["pct_concordancia_duplicadas"] == 25.0
    assert resultado[10]["pares_vizinhos"] == 2
    assert resultado[10]["pearson_medio_vizinhos"] == pytest.approx(1.0)
    assert resultado[27]["pearson_medio_vizinhos"] < 0.5


def test_pares_proximos_respeitam_raio_e_reportam_correlacao():
    inventario = pd.DataFrame({
        "codigo": ["A", "B", "C"], "nome": ["A", "B", "C"], "rede": ["APAC", "CEMADEN", "CEMADEN"],
        "latitude": [-8.05, -8.05, -8.05], "longitude": [-34.90, -34.91, -34.99]})  # B a ~1 km, C a ~10 km.
    chuva = [0, 3, 0, 12, 1, 0, 7, 0, 0, 5]
    consolidado = pd.concat([leituras("A", chuva), leituras("B", [2 * v for v in chuva]),
                             leituras("C", chuva)]).assign(origem="APAC")
    [par] = rec.comparar_pares_proximos(consolidado, inventario, raio_km=3, min_dias=5)
    assert (par["codigo_a"], par["codigo_b"]) == ("A", "B")
    assert par["dist_km"] == pytest.approx(1.1, abs=0.05)
    assert par["diaria"]["pearson"] == pytest.approx(1.0)
    [resumo_a, resumo_b] = rec.resumo_vizinhas([par])
    assert not resumo_a["revisar"] and resumo_a["pares"] == 1


def test_resumo_por_origem_mostra_o_que_o_cemaden_acrescenta():
    consolidado = pd.concat([leituras("A", [1.0, 2.0]).assign(origem="APAC"),
                             leituras("B", [1.0]).assign(origem="CEMADEN")])
    [ano] = rec.resumo_origem(consolidado)
    assert ano == {"ano": 2024, "estacoes": 2, "estacoes_apac": 1, "estacoes_cemaden": 1,
                   "estacao_dias_apac": 2, "estacao_dias_cemaden": 1}
