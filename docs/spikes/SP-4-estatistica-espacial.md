# SP-4 — Estatística espacial: Moran global e LISA

**Sprint 1 · Should · 1 pt · Squad Inteligência · Ariel Cavalcanti · 05/11/2026**

## Pergunta

A incidência de dengue nos bairros do Recife em 2024 está espacialmente agrupada? Onde estão os agrupamentos alto-alto (hotspots)?

## Dados e método

- Casos de 2024 por bairro, agregados do painel bairro × SE (US14): **9.716 casos**, **94 bairros**.
- Geometrias: `bairros_esig.geojson` (94 bairros, join 100% por nome normalizado).
- Variável: **casos notificados** — proxy de incidência enquanto a população (US08) não chega.
- Pesos espaciais: **Queen**, linha-padronizados; **sem ilhas**; média de 5,38 vizinhos por bairro.
- **Moran global** e **LISA** com **999 permutações**; significância `p_sim < 0,05`.

> **Por que o resultado é metodologicamente válido sem população:** o Moran's I é invariante a uma multiplicação positiva constante dos valores. Com denominador constante, a classificação HH/LL/HL/LH e os p-valores permutacionais são idênticos aos da taxa por 100 mil. O que muda é a unidade de leitura e a interpretação de bairros populosos.

## Resultado

| Métrica | Valor |
|---|---:|
| Moran's I | **0,2738** |
| Esperado sob aleatoriedade | −0,0108 |
| z | **4,886** |
| p (999 permutações) | **0,001** |
| p (normal) | 6,96 × 10⁻⁶ |

Há **agrupamento espacial estatisticamente significativo**: bairros vizinhos tendem a ter contagens parecidas.

### Classificação LISA

| Categoria | Bairros |
|---|---:|
| **Alto-Alto (hotspot)** | **10** |
| Baixo-Alto (outlier) | 3 |
| Baixo-Baixo (coldspot) | 2 |
| Alto-Baixo (outlier) | 0 |
| Não significativo | 79 |

**Hotspots HH:** Areias, Barro, Boa Viagem, Caxanga, Cohab, Ibura, Imbiribeira, Ipsep, Jordao, Pina.

**Distribuição dos HH por DS:** DS 6 (4), DS 8 (3), DS 5 (2), DS 4 (1). O agrupamento concentra-se no sul/sudoeste (Ibura, Cohab, Jordão, Barro e Boa Viagem), com Caxangá isolado a noroeste.

**Coldspots LL:** Encruzilhada e Graças.

**Outliers LH** (baixo cercado de alto): Cacote, Cidade Universitária e Jiquiá.

Dois casos mostram por que o LISA agrega informação além do ranking bruto: **Ipsep** (129 casos) e **Caxanga** (140) entram como HH porque os vizinhos puxam o agrupamento, embora não estejam entre os maiores totais absolutos.

## Decisão e recomendação

1. **Adotar Moran global + LISA (Queen, 999 permutações) como método de hotspots da US20.**
2. **Exportar o GeoJSON classificado** para a camada de mapa do produto; o arquivo já está pronto em `saidas/sp4_lisa_2024.geojson`.
3. **Reexecutar com a US08 antes de levar o mapa para a tela.** A lista de HH em contagens inclui Boa Viagem, que tem população muito alta; em incidência por 100 mil ela pode sair do HH. O mapa atual é descritivo, não decisório.
4. **Na US20, acrescentar:** correção de múltiplas comparações (Benjamini-Hochberg) e checagem de sensibilidade com KNN (k=4) além de Queen.

## Limitações

- População placeholder: contagens, não incidência por 100 mil; bairros populosos são favorecidos.
- Contagens pequenas tornam as taxas instáveis; o resultado é ecológico e descritivo.
- LISA testa cada bairro separadamente; sem correção de múltiplas comparações nesta versão.
- MAUP: o resultado depende da malha de bairros e não vale para setores ou indivíduos.
- A escolha Queen é uma decisão metodológica; KNN é a sensibilidade natural.
- Associação espacial não implica causalidade.

## Fala de 15 min (roteiro)

1. A pergunta é se os casos se agrupam no espaço, não só se há bairros com muitos casos.
2. Moran global: I = 0,274, z = 4,89, p = 0,001 — há agrupamento.
3. LISA localiza 10 hotspots HH, concentrados nos DS 4, 5, 6 e 8.
4. Dois bairros entram como HH sem estarem no topo absoluto (Ipsep e Caxanga): é o efeito de vizinhança.
5. Sem população, o mapa é de casos; a próxima iteração troca o denominador e reexecuta.

## Artefatos

- Notebook: [`backend/notebooks/sp4_moran_lisa.ipynb`](../../backend/notebooks/sp4_moran_lisa.ipynb)
- Mapa LISA: [`sp4_mapa_lisa_2024.png`](../../backend/notebooks/saidas/sp4_mapa_lisa_2024.png)
- Diagrama de Moran: [`sp4_moran_scatter_2024.png`](../../backend/notebooks/saidas/sp4_moran_scatter_2024.png)
- GeoJSON classificado: [`sp4_lisa_2024.geojson`](../../backend/notebooks/saidas/sp4_lisa_2024.geojson)
- Tabela por bairro: [`sp4_lisa_2024.csv`](../../backend/notebooks/saidas/sp4_lisa_2024.csv)
- Resumo do Moran: [`sp4_moran_global.csv`](../../backend/notebooks/saidas/sp4_moran_global.csv)
