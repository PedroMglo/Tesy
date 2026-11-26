# Uma cache para as duas fases do turno com pack

**TRACE_DERIVED · NO_GO para a partição fixa de 176 lugares por frequência e 177 por recência.** O compromisso recuperou 94 dos 375 primeiros usos CPU e serviu 95 reservas CPU de decode. A cache alcançou os dois objetivos de cobertura e reduziu a aquisição em T1 em 1,428 GB face à recência. Na execução P106 faltaram **179,439 ms** para 6 tok/s mesmo concedendo custo zero às callbacks afetadas até à drenagem. Em P97 restaram 93,087 ms. As duas reproduções independentes do cálculo coincidiram. [Critérios prévios](protocol.md) · [Resultados por tier, fase e hipótese de custo](receipt.json)

| Escolha feita durante T1 | Captura em T1 (GB) | Primeiras faltas CPU cobertas | Hits CPU no decode | Piso primeiro final P97 / P106 (s) | Piso decode P97 / P106 (s) |
|---|---:|---:|---:|---:|---:|
| Recência, 353 | 59,566 | 65 | 143 | 12,905 / 14,168 | 7,304 / 7,565 |
| Frequência 176, recência 177 | 58,138 | 94 | 95 | 12,519 / 13,780 | 7,740 / 8,013 |
| Frequência, 353 | 20,477 | 101 | 41 | 13,423 / 14,668 | 8,179 / 8,452 |

O piso da tabela atribui às escolhas todo o tempo das callbacks que podem influenciar antes da drenagem, com entrega gratuita, e conserva o exterior. O banco misto melhora o primeiro final contrafactual face aos dois controlos nos dois relógios. O P106 precisaria ainda de retirar 3,780 s até aos 10 s. No cenário em que a influência persiste até ao fim, cobrar metade do serviço residual observado deixa 10,690 e 11,945 s até ao primeiro final. O recibo inclui os três preços de serviço nas duas hipóteses. Nenhuma destas durações mede uma nova conversa. [Atribuição histórica aos quatro workers](../request_cost/README.md)

Todos os braços conservaram 4 548 ofertas de vítimas em T1 e 2 354 reservas em T2, incluindo 1 263 no prefill e 1 091 no decode. Em T2 o banco candidato forneceria 2,948 GB durante o prefill e 1,613 GB no decode. Ficariam na origem, respetivamente, 13,748 e 12,809 GB de payload. A aquisição em T1, a entrega aos primários e a leitura da origem são operações distintas. O P97 e o P106 registaram a mesma trajetória de 47 saídas com clocks distintos. A proteção em código e o tempo para instalar bytes reais nesta política permanecem por medir.

Protocolo `b04dc60c`, código `ff046825`. A fixture verificou os dois extremos em todos os prefixos de 243 sequências, além da conservação e da impossibilidade de recuperar bytes já descartados sem nova oferta. Nos originais e nas partes 97 e 106 do arquivo, os processos CPU demoraram 2,43/2,49 s e usaram 76 748/75 960 KiB de RSS. Os recibos deram o mesmo SHA-256 `ef8a45e879514fb5081e24205236c37124102cc4ba522cd2e09476a1f223e12b`. [Arquivo 163](../../../../../../../private_archive/part-163.json) · [Verificador](score.py)

```sh
python3 -IB test_mixed.py
python3 -IB score.py --archive "$ARCHIVE" --p97 "$P97" --p106 "$P106" --new-output-dir "$NEW"
```
