# US20 — Hotspots espaciais (LISA) por temporada

**Sprint 2 · Must · 5 pts · Squad Inteligência · Ariel Cavalcanti · 26/11/2026**
**Operacionaliza:** [SP-4](SP-4-estatistica-espacial.md) · **Alimenta:** US30 e o M2

## Pergunta

A dengue nos bairros do Recife forma aglomerados espaciais em cada temporada? Quais
bairros são hotspots Alto-Alto (HH) e quais permanecem hotspots ao longo dos anos?

## O que mudou em relação ao SP-4

O SP-4 provou o método em **2024**, com uma única temporada, usando o painel de
notificações (US14) e o campo `CDISTSANTPSAD` do GeoJSON para o DS. A US20
operacionaliza o método:

- cobre **2016–2025**, com a série US04 de casos **não descartados**;
- exporta **um GeoJSON por temporada**, com `cluster` (p_sim < 0,05) e
  `cluster_bh` (BH 5%);
- inclui sensibilidades de **fonte** (US04 × painel) e de **pesos** (Queen × KNN k=4);
- usa o **DS canônico** de `distritos_sanitarios_*.csv`, não o `CDISTSANTPSAD`.

Por isso os números de 2024 **não são os mesmos do SP-4**. A diferença é explicada
abaixo, na seção “2024: por que o número mudou”.

## Dados e método

- **Fonte primária:** `sinan_bairro_se_2016_2025.csv` (US04), casos notificados
  **não descartados**, SE de notificação, 2016–2025.
- **Cobertura:** 94 bairros canônicos, 10 temporadas, **40.320 casos**.
  Pau Ferro não tem caso em nenhuma temporada e entra como zero; 93 bairros têm
  pelo menos um caso.
- **Perda de join:** 36 casos (0,09%) ficam fora do lookup canônico por grafia
  não mapeada (ex.: `CENTRO`, `VASCO`, `JIQU]`). O total é registrado no
  `us20_meta.json`.
- **Geometrias:** `bairros_esig.geojson`; peso calculado na geometria completa;
  a exportação usa EPSG:4326 e simplificação de 10 m em EPSG:31985 apenas para
  reduzir o tamanho dos arquivos.
- **Temporada:** ano civil da SE (`semana // 100`). A fronteira de temporada
  epidêmica do SP-3 fica para uma decisão posterior.
- **Pesos:** Queen, linha-padronizados; sem ilhas; média de **5,383 vizinhos**
  por bairro.
- **Inferência:** Moran global e LISA local com **999 permutações**, seed **42**,
  resetada antes de cada chamada.
- **Classificação:**
  - `cluster`: LISA com `p_sim < 0,05`;
  - `cluster_bh`: Benjamini-Hochberg 5% sobre os 94 p-valores;
  - `hotspot` e `hotspot_bh`: indicadores de HH nas duas camadas.
- **Unidade:** contagem de casos, não incidência. A população (US08) ainda é
  placeholder; a leitura favorece bairros populosos.

> **Por que a contagem serve para o LISA:** o Moran's I é invariante a uma
> multiplicação positiva constante dos valores. Com um denominador constante,
> a classificação HH/LL e os p-valores permutacionais são os mesmos de uma taxa.
> O que muda é a interpretação: bairros populosos tendem a ter mais casos.

## Resultado

### Moran global

| Temporada | Casos | Bairros com casos | Moran's I | p (999 perm.) | HH | HH com BH |
|---:|---:|---:|---:|---:|---:|---:|
| 2016 | 13.368 | 93 | 0,189 | 0,004 | 5 | 0 |
| 2017 | 980 | 76 | 0,140 | 0,011 | 5 | 0 |
| 2018 | 1.197 | 81 | 0,232 | 0,001 | 7 | 3 |
| 2019 | 4.637 | 91 | 0,171 | 0,007 | 8 | 2 |
| 2020 | 1.650 | 82 | 0,332 | 0,001 | 7 | 5 |
| 2021 | 7.392 | 93 | 0,352 | 0,001 | 8 | 6 |
| 2022 | 1.354 | 85 | 0,408 | 0,001 | 6 | 4 |
| 2023 | 1.513 | 83 | 0,466 | 0,001 | 8 | 5 |
| 2024 | 2.604 | 76 | 0,141 | 0,012 | 5 | 0 |
| 2025 | 5.625 | 92 | 0,306 | 0,001 | 8 | 4 |

Há agrupamento espacial estatisticamente significativo em **todas as 10
temporadas**. O I varia de 0,140 (2017/2024) a 0,466 (2023). O número de HH
sem correção fica entre 5 e 8; com BH, entre 0 e 6.

### Hotspots HH por temporada

| Temporada | HH (sem BH) | HH (BH 5%) |
|---|---|---|
| 2016 | Barro, Caxangá, Ibura, Imbiribeira, Jordão | — |
| 2017 | Boa Viagem, Ibura, Imbiribeira, Jordão, Pina | — |
| 2018 | Boa Viagem, Ibura, Imbiribeira, Ipsep, Jordão, Pina, Vasco da Gama | Ibura, Imbiribeira, Jordão |
| 2019 | Areias, Beberibe, Boa Viagem, Cohab, Ibura, Imbiribeira, Ipsep, Jordão | Ibura, Jordão |
| 2020 | Areias, Boa Viagem, Cohab, Ibura, Imbiribeira, Ipsep, Jordão | Boa Viagem, Ibura, Imbiribeira, Ipsep, Jordão |
| 2021 | Areias, Boa Viagem, Cohab, Ibura, Imbiribeira, Ipsep, Jordão, Pina | Areias, Boa Viagem, Ibura, Imbiribeira, Ipsep, Jordão |
| 2022 | Boa Viagem, Ibura, Imbiribeira, Ipsep, Jordão, Pina | Boa Viagem, Ibura, Imbiribeira, Jordão |
| 2023 | Areias, Boa Viagem, Cohab, Ibura, Imbiribeira, Ipsep, Jordão, Pina | Boa Viagem, Ibura, Imbiribeira, Ipsep, Jordão |
| 2024 | Caxangá, Ibura, Imbiribeira, Iputinga, Pina | — |
| 2025 | Barro, Boa Viagem, Cohab, Ibura, Imbiribeira, Ipsep, Jordão, Pina | Boa Viagem, Ibura, Imbiribeira, Jordão |

> Os nomes aparecem com acentuação editorial. No CSV/GeoJSON, `key` é a forma
> canônica sem acento (ex.: `JORDAO`, `CAXANGA`); use `key` ou `bairro_id` no join.

### Persistência dos hotspots

| Bairro | DS | Temporadas HH | Temporadas HH com BH | Casos no período |
|---|---:|---:|---:|---:|
| **Ibura** | 7 | **10/10** | 7 | 2.213 |
| **Imbiribeira** | 6 | **10/10** | 6 | 1.929 |
| **Jordão** | 7 | **9/10** | 7 | 696 |
| **Boa Viagem** | 6 | 8/10 | 5 | 2.005 |
| **Ipsep** | 6 | 7/10 | 3 | 861 |
| **Pina** | 6 | 7/10 | 0 | 983 |
| Cohab | 7 | 5/10 | 0 | 2.297 |
| Areias | 5 | 4/10 | 1 | 1.128 |
| Barro | 5 | 2/10 | 0 | 437 |
| Caxangá | 4 | 2/10 | 0 | 342 |

**Leitura:** o núcleo persistente está no sul/sudoeste, em **Ibura, Imbiribeira
e Jordão**. Boa Viagem entra em 8 das 10 temporadas e sobrevive ao BH em 5.
**Pina** é HH em 7 temporadas, mas **nunca** sobrevive ao BH; é um caso em que a
vizinhança puxa a classificação, mas a evidência não é robusta após correção.
**Cohab** tem muitos casos (2.297), mas só 5 temporadas como HH e nenhuma com BH.

### Distribuição por DS

Com o DS canônico:

- **DS 6 e DS 7** concentram a maior parte dos HH em praticamente todas as
  temporadas; o DS 6 chega a 4 HH em 2018, 2021, 2022, 2023 e 2025.
- **DS 4** aparece em 2016 (Caxangá) e 2024 (Caxangá e Iputinga).
- **DS 5** aparece em 2016 (Barro), 2019–2021 e 2023 (Areias) e 2025 (Barro).
- **DS 8** aparece só em 2018 (Vasco da Gama) na classificação sem BH.
- **DS 1, 2 e 3** têm poucos ou nenhum HH; Beberibe (DS 2) aparece em 2019.

A distribuição completa está em [`us20_hh_por_ds.csv`](../../backend/notebooks/saidas/us20_hh_por_ds.csv).

### 2024: por que o número mudou

| 2024 | SP-4 (painel) | US20 (US04) |
|---|---:|---:|
| Casos | 9.716 | 2.604 |
| Moran's I | 0,274 | 0,141 |
| p (999 perm.) | 0,001 | 0,012 |
| HH sem BH | 10 | 5 |
| HH com BH | 5 | 0 |
| Bairros HH | Areias, Barro, Boa Viagem, Caxangá, Cohab, Ibura, Imbiribeira, Ipsep, Jordão, Pina | Caxangá, Ibura, Imbiribeira, Iputinga, Pina |

A diferença **não é erro**: o SP-4 usou o painel US14, que conta **todas as
notificações, inclusive descartadas**; a US20 usa a US04, que exclui descartados.
Em 2024, isso reduz de 9.716 para 2.604 casos e muda a significância. O painel
continua sendo a base correta do forecast de demanda; a US04 é a base correta
para hotspots de dengue.

Há também uma diferença de **DS**: o SP-4 usava `CDISTSANTPSAD` do GeoJSON, que
coloca Ibura e Jordão no DS 8. O lookup canônico, derivado de
`distritos_sanitarios_*.csv`, coloca os dois no **DS 7**. A US20 usa o lookup
canônico; o GeoJSON/ESIG deve ser corrigido ou documentado em uma issue de dados.

## Sensibilidades

### Fonte: US04 × painel

| Temporada | Fonte | Casos | Moran's I | p | HH | HH com BH |
|---:|---|---:|---:|---:|---:|---:|
| 2024 | US04 | 2.604 | 0,141 | 0,012 | 5 | 0 |
| 2024 | Painel | 9.716 | 0,274 | 0,001 | 10 | 5 |
| 2025 | US04 | 5.625 | 0,306 | 0,001 | 8 | 4 |
| 2025 | Painel | 8.547 | 0,185 | 0,003 | 6 | 0 |

A fonte muda o resultado de forma material. **Não misturar as séries** em uma
mesma análise. O painel deve ser usado apenas como sensibilidade até que a US14
incorpore o filtro de descartados (ou uma coluna `casos_confirmados`).

### Pesos: Queen × KNN k=4

| Temporada | Esquema | Moran's I | p | HH | HH com BH |
|---:|---|---:|---:|---:|---:|
| 2024 | Queen | 0,141 | 0,012 | 5 | 0 |
| 2024 | KNN k=4 | 0,078 | **0,059** | 0 | 0 |
| 2025 | Queen | 0,306 | 0,001 | 8 | 4 |
| 2025 | KNN k=4 | 0,241 | 0,001 | 4 | 0 |

Em **2024**, o KNN k=4 deixa o Moran global **não significativo** a 5% e zera os
HH. Em **2025**, o KNN mantém o agrupamento global, mas os HH caem para
**Boa Viagem, Ibura, Ipsep e Jordão**, sem nenhum sobrevivente ao BH. A
persistência de **Imbiribeira** é sensível à matriz de pesos; **Ibura e Jordão**
são o núcleo mais robusto entre Queen e KNN.

A tabela completa está em
[`us20_sensibilidade_pesos.csv`](../../backend/notebooks/saidas/us20_sensibilidade_pesos.csv).

### BH 5%

O BH é conservador porque corrige 94 testes espaciais dependentes. Em 2016,
2017 e 2024 ele zera todos os HH. A recomendação é publicar as duas camadas:
o mapa usa `cluster` (LISA convencional) e o selo `cluster_bh`/`hotspot_bh`
indica os hotspots que sobrevivem à correção.

## Decisão e recomendação

1. **Adotar Moran global + LISA (Queen, 999 permutações) por temporada como método
   da US20**, com temporada = ano civil.
2. **Publicar `cluster` como camada principal e `cluster_bh` como confiança.**
   Ações de campo devem priorizar `hotspot_bh`; o mapa completo continua útil
   para leitura exploratória.
3. **Usar a US04 como fonte primária** e o painel apenas como sensibilidade.
   Levar para a US14 a recomendação de filtrar descartados ou expor
   `casos_confirmados`.
4. **Usar o DS canônico** de `distritos_sanitarios_*.csv`; registrar a divergência
   de `CDISTSANTPSAD` para Ibura/Jordão (DS 8 no GeoJSON, DS 7 no lookup).
5. **Levar o GeoJSON por temporada para a US30**, com o contrato de propriedades
   documentado abaixo.
6. **Reexecutar quando a US08 chegar** (incidência por 100 mil) e quando a US01
   definir a SE por `DT_SIN_PRI`; reavaliar a fronteira de temporada do SP-3.

## Contrato do GeoJSON (handoff para US30)

Cada `us20_lisa_<temporada>.geojson` tem 94 features, CRS84/EPSG:4326 e as
propriedades:

| Campo | Tipo | Uso |
|---|---|---|
| `temporada` | int | filtro |
| `bairro_id` | string | join com a API |
| `key` | string | chave normalizada |
| `bairro` | string | exibição |
| `ds` | string | agregação por DS |
| `casos` | int | casos observados |
| `valor` | float | hoje igual a `casos`; vira incidência com a US08 |
| `p_sim` | float | p permutacional |
| `p_bh` | float | p corrigido por BH |
| `quadrante` | int | 1–4 |
| `I_local` | float | Moran local |
| `cluster` | `HH/LH/LL/HL/ns` | classificação primária |
| `cluster_bh` | `HH/LH/LL/HL/ns` | classificação com BH |
| `hotspot` | bool | `cluster == "HH"` |
| `hotspot_bh` | bool | `cluster_bh == "HH"` |

## Limitações

- **Contagem, não incidência:** a população (US08) ainda é placeholder; bairros
  populosos são favorecidos. O Moran é invariante a denominador constante, mas
  a leitura de risco por bairro não é.
- **SE de notificação:** a US04 usa `SEM_NOT`/semana de notificação; a decisão
  US01 (`DT_SIN_PRI` × `DT_NOTIFIC`) está pendente.
- **Temporada = ano civil:** a fronteira epidêmica do SP-3 não foi aplicada.
- **BH conservador:** em 2016, 2017 e 2024 ele zera todos os HH; publicar as
  duas camadas evita esconder o sinal, mas não transforma `cluster` em evidência
  confirmatória.
- **Sensibilidade a pesos:** em 2024 o KNN k=4 não é significativo; em 2025,
  Imbiribeira sai do HH. O núcleo robusto é Ibura/Jordão.
- **Zero-inflação:** em anos de baixa (2017 e 2024, 76 bairros com casos), LL
  pode refletir ausência de casos, não um coldspot verdadeiro.
- **Fonte por nome:** a US04 é keyed by name; 36 casos (0,09%) foram descartados
  por grafia não mapeada.
- **Ecológico/MAUP:** o resultado vale para bairros, não para indivíduos, e
  depende da malha de bairros.
- **Associação não é causalidade.**

## Artefatos e reprodução

```bash
cd backend
source .venv/bin/activate          # ambiente de requirements-analysis.txt
python scripts/gerar_hotspots.py   # 2016–2025, Queen, 999 permutações, seed 42
```

A sensibilidade de fonte precisa do painel; se ele não existir, rode antes:

```bash
python scripts/gerar_painel.py
```

Saídas em `backend/notebooks/saidas/`:

- GeoJSONs: [`us20_lisa_2016.geojson`](../../backend/notebooks/saidas/us20_lisa_2016.geojson) …
  [`us20_lisa_2025.geojson`](../../backend/notebooks/saidas/us20_lisa_2025.geojson)
- Tabela por bairro × temporada: [`us20_lisa_bairro_temporada.csv`](../../backend/notebooks/saidas/us20_lisa_bairro_temporada.csv)
- Moran global: [`us20_moran_global.csv`](../../backend/notebooks/saidas/us20_moran_global.csv)
- Contagem LISA: [`us20_contagem_lisa.csv`](../../backend/notebooks/saidas/us20_contagem_lisa.csv)
- HH por DS: [`us20_hh_por_ds.csv`](../../backend/notebooks/saidas/us20_hh_por_ds.csv)
- Persistência: [`us20_hotspots_persistentes.csv`](../../backend/notebooks/saidas/us20_hotspots_persistentes.csv)
- Sensibilidade de pesos: [`us20_sensibilidade_pesos.csv`](../../backend/notebooks/saidas/us20_sensibilidade_pesos.csv)
- Sensibilidade de fonte: [`us20_sensibilidade_fonte.csv`](../../backend/notebooks/saidas/us20_sensibilidade_fonte.csv)
- Mapa das temporadas: [`us20_mapa_lisa_temporadas.png`](../../backend/notebooks/saidas/us20_mapa_lisa_temporadas.png)
- Mapa de persistência: [`us20_mapa_persistencia.png`](../../backend/notebooks/saidas/us20_mapa_persistencia.png)
- Moran por temporada: [`us20_moran_por_temporada.png`](../../backend/notebooks/saidas/us20_moran_por_temporada.png)
- Metadados: [`us20_meta.json`](../../backend/notebooks/saidas/us20_meta.json)

Código:

- Dados e estatística: [`backend/notebooks/hotspots.py`](../../backend/notebooks/hotspots.py)
- Pipeline: [`backend/scripts/gerar_hotspots.py`](../../backend/scripts/gerar_hotspots.py)
- Testes: [`backend/tests/test_hotspots.py`](../../backend/tests/test_hotspots.py) e
  [`backend/tests/test_gerar_hotspots.py`](../../backend/tests/test_gerar_hotspots.py)

## Fala de 15 min (roteiro)

1. A pergunta é onde os casos se agrupam no espaço, temporada a temporada, não
   apenas quais bairros têm mais casos.
2. Usamos 10 temporadas da US04 (casos não descartados), 94 bairros, Queen e 999
   permutações; o Moran global é significativo em todas.
3. O núcleo persistente é **Ibura, Imbiribeira e Jordão**; Boa Viagem entra em
   8 de 10 e sobrevive ao BH em 5.
4. O BH é conservador: em 2016, 2017 e 2024 ele zera os HH. Por isso publicamos
   as duas camadas.
5. A fonte importa: em 2024, o painel (com descartados) dá 10 HH/5 BH; a US04
   dá 5 HH/0 BH. Não misturar as séries.
6. O KNN k=4 mostra que 2024 é frágil e que Imbiribeira é sensível à matriz de
   pesos; Ibura e Jordão são o núcleo robusto.
7. O próximo passo é reexecutar com população (US08) e levar o GeoJSON para a
   US30.
