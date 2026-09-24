# Complemento — Métricas Consolidadas de Público em Série Temporal

**Este documento é um complemento à especificação original** (`especificacao-monitoramento-feira.md`). Ele não substitui nem edita nenhuma seção daquele documento — apenas define uma lacuna identificada no Painel Analítico (Seção 8.3 do documento original): a ausência de métricas-padrão de fluxo/engajamento e do gráfico comparativo em série temporal.

O implementador deve tratar este documento como uma extensão aditiva: tudo o que já está especificado no documento original (arquitetura, modelos, regras de Seção 0, esquema SQLite) permanece válido e inalterado.

---

## 1. Lacuna identificada

`agregados_janela` (Seção 7 do documento original) já grava os números necessários por janela de tempo, mas a especificação original não definia:
1. As métricas-padrão da área de audience measurement (nomenclatura consolidada de mercado, não termos ad-hoc).
2. O gráfico específico que cruza fluxo × engajamento ao longo do tempo.
3. Uma ressalva técnica sobre a confiabilidade da contagem de pessoas únicas.

Este complemento resolve os três pontos.

---

## 2. Métricas consolidadas (terminologia padrão de audience measurement / vitrine física)

| Métrica | Definição | Fórmula | Fonte de dados |
|---|---|---|---|
| **Footfall (Fluxo)** | Total de pessoas únicas detectadas na área, por janela | `visitantes_unicos` | Já existe em `agregados_janela` |
| **Engajamentos Válidos** | Sessões de engajamento que passaram do filtro de ruído (`dwell_time ≥ 3s`, Seção 5 do doc. original) | `engajamentos_validos` | Já existe em `agregados_janela` |
| **Capture Rate (Taxa de Captura)** | Proporção de quem passou que efetivamente engajou | `engajamentos_validos / visitantes_unicos` | **Campo novo** — calculado na consolidação da janela |
| **Average Dwell Time** | Tempo médio de permanência na zona de proximidade | `tempo_medio_zona` | Já existe em `agregados_janela` |
| **Engagement Rate** | Proporção de sessões com `engagement_score` acima de um limiar de qualidade (não apenas presença, mas atenção real) | contagem de sessões com `score ≥ LIMIAR_QUALIDADE` dividido por `engajamentos_validos` | **Campo novo** — `LIMIAR_QUALIDADE` sugerido: 0.5, ajustável empiricamente como constante nomeada |
| **Peak Hours (Horário de Pico)** | Identificação das janelas com maior footfall — comparadas às janelas de maior capture rate, que podem não coincidir | leitura direta da série temporal, sem cálculo adicional | Visualização, não campo de banco |

### 2.1 Alteração mínima no esquema (aditiva, não destrutiva)
A tabela `agregados_janela` (Seção 7 do documento original) permanece como está. Adicionar apenas os dois campos calculados, sem alterar os já existentes:

```sql
ALTER TABLE agregados_janela ADD COLUMN capture_rate REAL;
ALTER TABLE agregados_janela ADD COLUMN engagement_rate REAL;
```

Esses campos são calculados pelo mesmo processo agregador já descrito na Seção 7 do documento original, no momento em que a janela é fechada — não requer nova infraestrutura.

---

## 3. Gráfico comparativo (Painel Analítico — adição à Seção 8.3 do documento original)

**Especificação do gráfico:** série temporal de duas linhas sobrepostas no mesmo eixo X (janelas de tempo), eixo Y compartilhado ou duplo:
- Linha 1: `visitantes_unicos` (footfall) por janela
- Linha 2: `engajamentos_validos` por janela

**Por que duas linhas e não duas métricas separadas:** o valor analítico está na comparação visual direta — uma janela com footfall alto e engajamento baixo é um sinal diferente de uma janela com footfall baixo e engajamento alto, e isso só fica óbvio quando as duas curvas estão no mesmo gráfico, não em painéis separados.

**Complementar (não obrigatório nesta fase):** um segundo gráfico de barras simples com `capture_rate` por janela, para destacar picos e vales dessa proporção sem depender de leitura visual das duas curvas absolutas.

---

## 4. Ressalva técnica — confiabilidade do footfall

O `visitantes_unicos` depende do tracker (ByteTrack, Seção 4 do documento original) manter o mesmo `track_id` durante toda a passagem de uma pessoa pela área. Em cenário de oclusão (uma pessoa temporariamente encoberta por outra, ou por um objeto físico), o tracker pode atribuir um novo ID à mesma pessoa, inflando a contagem de footfall — mais provável em horários de maior movimento, que ironicamente são os que mais importam para a métrica.

Isto é uma **limitação conhecida e documentada de sistemas de contagem por tracking visual**, não um defeito a ser eliminado por completo nesta fase. Tratamento recomendado:
- Documentar essa limitação visivelmente junto ao gráfico no painel (nota de rodapé ou tooltip), para que o organizador interprete picos de footfall com essa ressalva em mente.
- Não implementar correção heurística de deduplicação de ID nesta fase — isso reintroduziria exatamente o tipo de complexidade de re-identificação que a Seção 0 do documento original decidiu evitar.

---

## 5. Critérios de aceite deste complemento

- [ ] `agregados_janela` possui os campos `capture_rate` e `engagement_rate`, calculados sem alterar os campos existentes
- [ ] O painel analítico exibe o gráfico de footfall × engajamentos válidos como duas séries sobre o mesmo eixo temporal
- [ ] A limitação de contagem por oclusão está documentada visualmente junto ao gráfico, não apenas neste documento
- [ ] Nenhuma lógica de deduplicação/re-identificação de pessoa foi adicionada para compensar a limitação da Seção 4
