# Spikes — Inteligência

Resumos de 1 página dos spikes e da história US20 do Squad Inteligência, para a
sessão com o orientador. Cada resumo aponta para o notebook/script executável e
para as saídas em `backend/notebooks/saidas/`.

| Spike/História | Tema | Sprint | Status | Resumo |
|---|---|---|---|---|
| **SP-2** | Modelos de contagem: Poisson vs binomial negativa, offset | S0 | ✅ concluído | [SP-2-modelos-contagem.md](SP-2-modelos-contagem.md) |
| **SP-4** | Estatística espacial: Moran global e LISA | S1 | ✅ concluído | [SP-4-estatistica-espacial.md](SP-4-estatistica-espacial.md) |
| **SP-5** | Clusterização e escolha de k | S1 | ✅ concluído | [SP-5-clusterizacao-k.md](SP-5-clusterizacao-k.md) |
| **US20** | Hotspots LISA por temporada (operacionaliza o SP-4) | S2 | ✅ concluído | [US20-hotspots-por-temporada.md](US20-hotspots-por-temporada.md) |

> **US20 não é um spike novo:** é a história que operacionaliza o SP-4, com 10
> temporadas (2016–2025), GeoJSON por temporada e sensibilidades de fonte e pesos.

## Como reproduzir

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -r requirements-analysis.txt
source .venv/bin/activate
python -m ipykernel install --user --name pulso-analise --display-name "Pulso análise"
python scripts/gerar_painel.py
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=pulso-analise \
  notebooks/sp2_glm_contagem.ipynb notebooks/sp4_moran_lisa.ipynb notebooks/sp5_clusters_k.ipynb

# US20 — hotspots por temporada (script, não notebook)
python scripts/gerar_hotspots.py
```

Detalhes em [`backend/notebooks/README.md`](../../backend/notebooks/README.md).
A sensibilidade de fonte da US20 usa o painel; sem ele, o script avisa e pula
essa tabela.

## Decisões que os spikes e a US20 destravam

- **US24 (GLM binomial negativa):** NB2 com offset `log(população)` é o modelo
  interpretável; o Poisson não serve (dispersão 5,87).
- **US20 (hotspots LISA):** Moran global + LISA (Queen, 999 permutações) por
  temporada, 2016–2025, com a US04 (casos não descartados); núcleo persistente
  em Ibura, Imbiribeira e Jordão; BH conservador e sensível à fonte/pesos.
- **US21 (perfis territoriais):** Ward com k=3 é o único admissível com os
  proxies atuais; reexecutar com IDH, densidade, intermitência e LST.

## Pendências que afetam as análises

| Pendência | História | Efeito |
|---|---|---|
| População por bairro | US08 | offset do SP-2, incidência do SP-4 e da US20, densidade do SP-5 |
| IDH | US09 | variável do SP-5 / US21 |
| Intermitência de água | US13 | variável do SP-5 / US21 |
| LST / ilhas de calor | US11 | variável do SP-5 / US21 |
| Decisão `DT_SIN_PRI` × `DT_NOTIFIC` | US01 | semana epidemiológica de todos (a US20 usa notificação) |
| Integração do histórico SINAN ao painel | US14 | a US20 já usa a série 2016–2025; SP-2/SP-3 ainda no painel 2024–25 |
| DS divergente no GeoJSON ESIG (Ibura/Jordão) | issue de dados | tabela HH por DS; a US20 usa o lookup canônico |

Enquanto a US08 não chega, os resultados das análises (SP-2, SP-4, SP-5 e US20)
são **preliminares** e estão rotulados como tal nos resumos.

> O plano canônico continua em [`docs/Plano de ação PULSO (Scrum + DDD).md`](<../Plano de ação PULSO (Scrum + DDD).md>).
> O link `docs/PLANEJAMENTO.md` citado nos cartões do Linear ainda não existe no
> repositório.
