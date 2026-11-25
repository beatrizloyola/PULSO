import gzip

import pandas as pd
import pytest

from app.ingestao import cemaden

# Layout do download "Dados Pluviométricos" do Mapa Interativo (valores sintéticos).
CABECALHO = "municipio;codEstacao;uf;nomeEstacao;latitude;longitude;datahora;valorMedida"
CABECALHO_NOVO = "MUNICIPIO;COD_ESTACAO;UF;NOME_ESTACAO;LATITUDE;LONGITUDE;DATA_HORA;MEDIDA"


def csv(linhas, cabecalho=CABECALHO):
    return "\n".join([cabecalho, *linhas]) + "\n"


def linha(hora, valor, codigo="261160621A", nome="Areias", municipio="RECIFE"):
    return f"{municipio};{codigo};PE;{nome};-8,102;-34,929;{hora};{valor}"


def test_download_oficial_vira_leituras_utc_sem_ausente_virar_zero():
    texto = csv([
        linha("2024-03-01 03:10:00.0", "1,4"),
        linha("2024-03-01 04:00:00.0", "0"),
        linha("2024-03-01 05:00:00.0", "-"),
        linha("2024-03-01 04:00:00.0", "0,2", codigo="260790101A", municipio="JABOATAO DOS GUARARAPES"),
    ])
    df = cemaden.parse_download(texto)
    assert df["codigo"].unique().tolist() == ["261160621A"]  # Outro município fica fora.
    assert df["chuva_mm"].tolist() == [1.4, 0.0]  # '-' é leitura ausente, não zero.
    assert df["data_hora_utc"].iloc[0] == pd.Timestamp("2024-03-01 03:10:00")
    assert df[["latitude", "longitude"]].iloc[0].tolist() == [-8.102, -34.929]


def test_cabecalho_novo_do_mapa_interativo_e_aceito():
    texto = csv([linha("01/03/2024 03:10", "1.4")], cabecalho=CABECALHO_NOVO)
    df = cemaden.parse_download(texto)
    assert df.iloc[0][["codigo", "chuva_mm"]].tolist() == ["261160621A", 1.4]
    assert df.iloc[0]["data_hora_utc"] == pd.Timestamp("2024-03-01 03:10:00")


def test_extrato_de_recife_comprimido_le_igual_ao_download_de_uf(tmp_path):
    texto = "\ufeff" + csv([
        linha("2024-03-01 04:00:00.0", "0", codigo="260790101A", municipio="JABOATAO DOS GUARARAPES"),
        linha("2024-03-01 03:10:00.0", "1,4"),
    ]).replace("\n", "\r\n")
    extrato = cemaden.extrair_recife(texto)
    assert extrato.splitlines() == [CABECALHO, linha("2024-03-01 03:10:00.0", "1,4")]
    caminho = tmp_path / "cemaden_recife_2024_03.csv.gz"
    caminho.write_bytes(gzip.compress(extrato.encode()))
    pd.testing.assert_frame_equal(cemaden.ler_download(caminho), cemaden.parse_download(texto))


@pytest.mark.parametrize("texto, erro", [
    ("data;valor\n2024-03-01;1\n", "formato alterado"),
    (csv([linha("2024-03-01 03:10:00", "-0,2")]), "precipitação inválida"),
    (csv([linha("2024-03-01 03:10:00", "1,0"), linha("2024-03-01 03:10:00", "2,0")]), "conflitantes"),
    (csv([linha("ontem", "1,0")]), "data/hora"),
    (csv([linha("2024-03-01 03:10:00", "1,0", codigo="260790101A")]), "nenhuma leitura de Recife"),
])
def test_formato_inesperado_interrompe_leitura(texto, erro):
    with pytest.raises(ValueError, match=erro):
        cemaden.parse_download(texto)


def horarias(dia, horas, chuva=None, codigo="261160621A"):
    """Leituras horárias em UTC do dia pluviométrico `dia` (07h local de D-1 a 07h de D)."""
    inicio = pd.Timestamp(dia) - pd.Timedelta(hours=14)
    chuva = chuva or {}
    return pd.DataFrame([{"codigo": codigo, "data_hora_utc": inicio + pd.Timedelta(hours=h + 1),
                          "chuva_mm": chuva.get(h, 0.0)} for h in horas])


def test_dia_pluviometrico_termina_as_07h_local():
    leituras = horarias("2024-03-02", range(24), chuva={0: 1.0, 23: 2.0})
    # A leitura das 10:00 UTC (07h local) de 02/03 fecha o dia 02/03; a das 10:10 já é do dia 03/03.
    leituras.loc[len(leituras)] = ["261160621A", pd.Timestamp("2024-03-02 10:10"), 4.0]
    diario = cemaden.agregar_diario(leituras)
    assert diario[["data", "chuva_mm", "horas_com_dado"]].values.tolist()[0] == ["2024-03-02", 3.0, 24]
    assert diario["data"].tolist()[1] == "2024-03-03"


def test_dia_com_transmissao_insuficiente_fica_ausente_e_nao_soma_parcial():
    leituras = horarias("2024-03-01", range(12), chuva={0: 5.0})
    diario = cemaden.agregar_diario(leituras)
    assert diario["horas_com_dado"].tolist() == [12]
    assert diario["chuva_mm"].isna().all()


def test_acumulado_despejado_apos_falha_invalida_o_dia():
    # 194 mm numa leitura de 10 min (caso real de 601A em 14/06/2019): não é chuva do intervalo.
    leituras = horarias("2024-03-02", range(24), chuva={5: 194.06})
    [dia] = cemaden.agregar_diario(leituras).to_dict("records")
    assert dia["leitura_suspeita"] and pd.isna(dia["chuva_mm"])


def test_cadastro_jsonp_filtra_recife():
    texto = ('estacoes([{"atualizado":"x","estacao":['
             '{"codestacao":"261160621A","nomeestacao":"Areias","codibge":2611606,'
             '"latitude":-8.102,"longitude":-34.929,"sigla":"CEMADEN","tipoestacao":"Pluviométrica"},'
             '{"codestacao":"260790101A","nomeestacao":"X","codibge":2607901,'
             '"latitude":-8.1,"longitude":-35.0,"sigla":"CEMADEN","tipoestacao":"Pluviométrica"}]}])')
    cadastro = cemaden.parse_cadastro(texto)
    assert cadastro[["codigo", "latitude", "rede"]].values.tolist() == [["261160621A", -8.102, "CEMADEN"]]
