import json

from app import config
from app.services import socioterritorial

IDH_FILE = config.DATA_DIR / "idh_atlas_2010.json"


def _dados():
    with open(IDH_FILE, encoding="utf-8") as f:
        return json.load(f)


def _nomes_lookup():
    with open(config.BAIRROS_LOOKUP_FILE, encoding="utf-8") as f:
        return [b["nome"] for b in json.load(f)]


def test_todos_os_bairros_do_lookup_tem_idh_de_2010():
    dados = _dados()
    nomes = _nomes_lookup()

    assert dados["ano_referencia"] == 2010
    assert "Atlas" in dados["fonte"]
    assert set(dados["bairros"]) == set(nomes)
    assert dados["cobertura"]["bairros"] == len(nomes)

    for nome, item in dados["bairros"].items():
        assert 0 < item["idh"] <= 1, nome
        assert item["udhs"] >= 1, nome
        assert 0 <= item["udhs_compartilhadas"] <= item["udhs"], nome


def test_udhs_estao_mapeadas_para_bairros_existentes():
    dados = _dados()
    nomes = set(dados["bairros"])

    assert len(dados["udhs"]) == dados["cobertura"]["udhs"]
    for udh in dados["udhs"]:
        assert udh["bairros"], udh["nome"]
        assert set(udh["bairros"]) <= nomes, udh["nome"]
        assert 0 < udh["idhm"] <= 1, udh["nome"]
        assert udh["populacao"] > 0, udh["nome"]


def test_servico_resolve_bairro_ignorando_acento_e_caixa():
    item = socioterritorial.por_bairro("Água Fria")
    assert item is not None
    assert item["idh"] == _dados()["bairros"]["AGUA FRIA"]["idh"]
    assert socioterritorial.por_bairro("bairro inexistente") is None


def test_referencia_expoe_defasagem_da_fonte():
    referencia = socioterritorial.referencia()
    assert referencia["ano"] == 2010
    assert referencia["fonte"].startswith("Atlas do Desenvolvimento Humano")
    assert referencia["cobertura"]["udhs"] == 194


def test_api_de_prioridade_expoe_idh_por_bairro():
    from app.main import app

    client = app.test_client()
    response = client.post("/prioridade", json={"horizonte": 1})
    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()

    assert data["idh_referencia"]["ano"] == 2010
    assert len(data["todos"]) == 94
    for bairro in data["todos"]:
        assert 0 < bairro["idh"] <= 1, bairro["bairro_nome"]
        assert bairro["idh_udhs"] >= 1, bairro["bairro_nome"]

    bairros = client.get("/bairros").get_json()
    assert bairros["idh_referencia"]["ano"] == 2010
    assert all(0 < b["idh"] <= 1 for b in bairros["bairros"])
