# SP-5 — Clusterização de bairros e escolha de k

**Sprint 1 · Should · 1 pt · Squad Inteligência · Ariel Cavalcanti · 05/11/2026**

## Pergunta

Os 94 bairros do Recife se organizam em quantos perfis territoriais? Qual k é defensável com as variáveis disponíveis hoje?

## Dados e método

- Unidade: **bairro** (n = 94).
- Variáveis da clusterização (somente territoriais, padronizadas):
  - `vulnerabilidade_score` (ZEIS, 25–100). Não é variável independente: é `min(100, max(30, 40 + 15·log1p(zeis_ha)))`, com 25 para bairros sem ZEIS e overrides manuais para ≥85 em `build_bairros_lookup.py:108,115–118`;
  - `log1p(zeis_ha)`;
  - `log1p(area_km2)` (área do polígono em SIRGAS 2000 / UTM 25S).
- **Casos ficam fora da clusterização** e entram apenas como validação externa (Kruskal-Wallis), para não criar circularidade.
- Algoritmo: **Ward** (hierárquico). Comparação com k-means apenas como checagem.
- Escolha de k: silhouette para k = 2..8 + estabilidade por **bootstrap** (30 reamostragens, ARI contra a solução completa).
- Critérios de admissibilidade definidos antes de olhar o resultado: **menor cluster ≥ 10** e **ARI no 5º percentil ≥ 0,4** (não o mínimo). Entre os admissíveis, maior silhouette.

## Resultado

| k | Silhouette (Ward) | Menor cluster | Tamanhos | ARI médio | ARI mediano | ARI p05 | % ARI < 0,4 |
|---:|---:|---:|---|---:|---:|---:|---:|
| 2 | 0,571 | 26 | [68, 26] | 0,667 | 0,738 | **0,220** | **23%** |
| **3** | **0,468** | **19** | **[26, 49, 19]** | **0,768** | **0,745** | **0,522** | **0%** |
| 4 | 0,505 | 6 | [49, 6, 19, 20] | 0,838 | 0,902 | 0,544 | 0% |
| 5 | 0,528 | 6 | [6, 20, 19, 12, 37] | 0,820 | 0,822 | 0,647 | 0% |
| 6–8 | 0,523–0,541 | 1 | — | — | — | — | — |

**k = 3 é o único admissível:** k=2 falha na estabilidade (ARI p05 = 0,220; 23% dos bootstraps abaixo de 0,4), e k≥4 falha no tamanho do menor cluster (6 ou 1). O silhouette de k=3 (0,468) é moderado, mas é o que os proxies atuais sustentam. Usar o p05 em vez do mínimo evita que um único bootstrap instável decida; k=2 continua instável mesmo pelo critério mais robusto (o mínimo é 0,174, mas a média de 0,667 esconde 23% de folds ruins).

### Perfis encontrados (médias em unidade original)

| Perfil | n | Casos médios | Casos/km² | Vulnerabilidade | ZEIS (ha) | Área (km²) | % com ZEIS |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Perfil 1 — muito ZEIS / território extenso** | 26 | 172,4 | 67,8 | 90,0 | 54,7 | 5,36 | 96% |
| **Perfil 2 — sem ZEIS / território compacto** | 49 | 50,8 | 70,3 | 25,0 | 0,0 | 0,92 | 0% |
| **Perfil 3 — ZEIS residual / intermediário** | 19 | 113,8 | 71,3 | 63,4 | 3,0 | 1,87 | 89% |

> **Como ler "Casos/km²":** é a média das densidades por bairro do cluster (`casos_medios / area_km2`), não a razão entre as colunas "Casos médios" e "Área". A razão dos totais daria outro valor (ex.: 172,4 / 5,36 ≈ 32,2 vs 67,8).

**Validação externa:** Kruskal-Wallis dos casos médios entre os 3 clusters: **H = 24,66, p = 4,4 × 10⁻⁶**. Em **casos por km² não há diferença** (H = 0,49, p = 0,78), e as densidades dos perfis são quase iguais (67,8 / 70,3 / 71,3). Ou seja, o sinal é de **casos totais/volume**, não de intensidade territorial; parte da diferença é tamanho populacional. A validação **não** sustenta "mais risco por km²".

| Métrica | H | p |
|---|---:|---:|
| Casos médios | 24,66 | 4,4 × 10⁻⁶ |
| Casos/km² | 0,49 | 0,78 |

### Sensibilidade

| Especificação | Silhouette (k=3) | Tamanhos |
|---|---:|---|
| Territorial (primário) | 0,468 | [26, 49, 19] |
| + histórico de surto | 0,584 | [25, 59, 10] |
| + casos médios (circular) | 0,313 | [27, 54, 13] |

Incluir o histórico de surto aumenta o silhouette, mas o histórico é derivado do próprio desfecho — por isso fica fora do modelo primário. Incluir casos derruba o silhouette e cria circularidade explícita.

## Decisão e recomendação

1. **Usar Ward com k = 3 como ponto de partida da US21**, com a regra de admissibilidade documentada (silhouette + ARI p05 + tamanho mínimo).
2. **Não tratar os nomes dos perfis como definitivos.** Eles descrevem proxies (vulnerabilidade/ZEIS/área), não o risco final.
3. **Reexecutar na S2** quando chegarem IDH (US09), densidade (US08), intermitência (US13) e LST (US11). Espera-se que o k e os nomes mudem.
4. **Levar para a US21:** dendrograma, curva de silhouette, ARI (mediana/p05/% abaixo de 0,4) e Kruskal-Wallis (casos e casos/km²) como critérios de aceite do perfil, não só o mapa.
5. **Mapeamento para a US21:** `cluster` 0/1/2 no CSV corresponde a `perfil` 1/2/3 e `perfil_nome` já gravados em `sp5_bairros_clusters.csv` e `sp5_perfis_clusters.csv`.

## Limitações

- Só três proxies territoriais, dois deles quase discretos (vulnerabilidade e ZEIS); o silhouette moderado reflete isso.
- `vulnerabilidade_score` e `log_zeis` são quase a mesma variável (Spearman **0,96 por construção**); na prática a clusterização tem **dois eixos: ZEIS e área**, e "alta vulnerabilidade" é quase "muito ZEIS".
- Sem população, "casos médios" mistura risco com tamanho populacional; em casos/km² não há diferença entre os perfis (p = 0,78), então a validação externa é de **volume**, não de intensidade.
- O `historico_score` do lookup é derivado de surtos e não deve entrar na clusterização sem revisão.
- k=3 é uma escolha condicionada aos dados atuais; não é uma verdade do território.
- Cluster ecológico de bairros; não vale para indivíduos.

## Fala de 15 min (roteiro)

1. Clusterizamos bairros com três proxies territoriais; casos ficam só para validar.
2. O silhouette sozinho sugere k=2, mas k=2 é instável: ARI p05 0,22 e 23% dos bootstraps abaixo de 0,4.
3. k≥4 cria clusters menores que 10 bairros; com os critérios definidos, k=3 é o único admissível.
4. Os perfis se diferenciam em casos totais (p = 4,4 × 10⁻⁶), mas não em casos/km² (p = 0,78): o sinal é de volume, não de intensidade territorial.
5. O resultado é preliminar: volta para a S2 com IDH, densidade, intermitência e LST.

## Artefatos

- Notebook: [`backend/notebooks/sp5_clusters_k.ipynb`](../../backend/notebooks/sp5_clusters_k.ipynb)
- Dendrograma: [`sp5_dendrograma.png`](../../backend/notebooks/saidas/sp5_dendrograma.png)
- Silhouette por k + estabilidade: [`sp5_silhouette_por_k.png`](../../backend/notebooks/saidas/sp5_silhouette_por_k.png)
- Silhouette por bairro: [`sp5_silhouette_clusters.png`](../../backend/notebooks/saidas/sp5_silhouette_clusters.png)
- Mapa dos perfis: [`sp5_mapa_clusters.png`](../../backend/notebooks/saidas/sp5_mapa_clusters.png)
- Perfis: [`sp5_perfis_clusters.csv`](../../backend/notebooks/saidas/sp5_perfis_clusters.csv)
- Bairros × cluster: [`sp5_bairros_clusters.csv`](../../backend/notebooks/saidas/sp5_bairros_clusters.csv)
- Validação externa: [`sp5_validacao_externa.csv`](../../backend/notebooks/saidas/sp5_validacao_externa.csv)
