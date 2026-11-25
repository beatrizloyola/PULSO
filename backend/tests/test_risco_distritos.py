import pytest

from app.shared.territorio import normalizar_nome_bairro, todos_territorios

NIVEIS_VALIDOS = {"baixo", "moderado", "alto", "critico"}
IMPACTOS_VALIDOS = {"positivo", "neutro", "negativo"}


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return app.test_client()


def test_risco_distritos_contrato_padrao(client):
    resp = client.get("/risco/distritos")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()

    assert set(data.keys()) == {
        "semana_id",
        "semana_cod",
        "semana_alvo_cod",
        "horizonte",
        "modelo_status",
        "cobertura_dados",
        "distritos",
    }
    assert isinstance(data["semana_id"], str) and "-W" in data["semana_id"]
    assert isinstance(data["semana_cod"], int)
    assert isinstance(data["semana_alvo_cod"], int)
    assert data["horizonte"] == 1
    assert data["modelo_status"] == "mock_agregado"

    cobertura = data["cobertura_dados"]
    assert set(cobertura.keys()) == {
        "semanas_consolidadas",
        "fontes_disponiveis",
        "fontes_ausentes",
    }
    assert cobertura["semanas_consolidadas"] is True
    assert cobertura["fontes_disponiveis"] == ["SINAN", "APAC", "Open-Meteo"]
    assert cobertura["fontes_ausentes"] == ["Censo2022", "Ovitrampas", "Compesa"]

    distritos = data["distritos"]
    assert len(distritos) == 8
    assert [d["ds"] for d in distritos] == [str(i) for i in range(1, 9)]

    for distrito in distritos:
        assert set(distrito.keys()) == {
            "ds",
            "rpa",
            "nivel_risco",
            "incidencia_prevista",
            "casos_previstos",
            "bairros_chave",
            "fatores",
        }
        assert distrito["rpa"].startswith("RPA ")
        assert distrito["nivel_risco"] in NIVEIS_VALIDOS
        assert distrito["incidencia_prevista"] is None
        assert isinstance(distrito["casos_previstos"], (int, float))
        assert distrito["casos_previstos"] >= 0

        bairros = distrito["bairros_chave"]
        assert 1 <= len(bairros) <= 3
        for b in bairros:
            assert set(b.keys()) == {"bairro_id", "bairro_nome", "casos_previstos"}
            assert isinstance(b["bairro_id"], str) and b["bairro_id"]
            assert isinstance(b["bairro_nome"], str) and b["bairro_nome"]
            assert isinstance(b["casos_previstos"], (int, float))
        casos_bairros = [b["casos_previstos"] for b in bairros]
        assert casos_bairros == sorted(casos_bairros, reverse=True)

        fatores = distrito["fatores"]
        assert len(fatores) >= 1
        for f in fatores:
            assert set(f.keys()) == {"fator", "descricao", "impacto"}
            assert isinstance(f["fator"], str) and f["fator"]
            assert isinstance(f["descricao"], str) and f["descricao"]
            assert f["impacto"] in IMPACTOS_VALIDOS


def test_risco_distritos_soma_casos_bate_com_prioridade(client):
    resp_dist = client.get("/risco/distritos?semana_id=2025-W20&horizonte=2")
    assert resp_dist.status_code == 200
    data_dist = resp_dist.get_json()
    assert data_dist["semana_id"] == "2025-W20"
    assert data_dist["semana_cod"] == 202520
    assert data_dist["semana_alvo_cod"] == 202522
    assert data_dist["horizonte"] == 2

    resp_prio = client.post("/prioridade", json={"semana_id": "2025-W20", "horizonte": 2})
    assert resp_prio.status_code == 200
    bairros_prio = resp_prio.get_json()["todos"]

    ds_por_bairro = {t.bairro_normalizado: t.ds for t in todos_territorios()}
    esperado_por_ds = {str(i): 0.0 for i in range(1, 9)}
    for item in bairros_prio:
        ds = ds_por_bairro[normalizar_nome_bairro(item["bairro_nome"])]
        esperado_por_ds[ds] += item["metadados"]["casos_previstos"]

    for distrito in data_dist["distritos"]:
        assert distrito["casos_previstos"] == pytest.approx(
            round(esperado_por_ds[distrito["ds"]], 1), abs=0.11
        )


@pytest.mark.parametrize("horizonte", ["0", "5", "-1", "abc"])
def test_risco_distritos_horizonte_invalido_retorna_400(client, horizonte):
    resp = client.get(f"/risco/distritos?horizonte={horizonte}")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_risco_distritos_semana_invalida_retorna_400(client):
    resp = client.get("/risco/distritos?semana_id=2026-W01")
    assert resp.status_code == 400
    assert "error" in resp.get_json()
