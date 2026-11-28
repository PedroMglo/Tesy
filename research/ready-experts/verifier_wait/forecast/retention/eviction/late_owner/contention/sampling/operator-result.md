# O operador atual consegue promover um expert CPU sem copiar os pesos?

**Seguimento na camada CPU0 do target.** A última projeção down identificou a fronteira segura de libertação. Os preços nos dois casos dão INCONCLUSIVE para um hit isolado. [Teste de camada com quatro produtores](../../../../../../../cpu_wave/frame_lease/README.md)

**MEDIDO no Ryzen AI 9 HX 370. GO para usar IDs físicos nas projeções do backend atual.** Proteger a arena contra escrita e trocar apenas um identificador reproduziu, byte a byte, os 14 653 440 B do controlo. A referência independente, produzida antes desta unidade com staging e o leitor C291, tem o mesmo SHA-256 integral e por geração. Deixar o identificador antigo produziu o erro previsto. A dependência de endereçamento das matrizes ficou resolvida no GGML pinado. [Pré-registo](operator-protocol.md) · [Recibo nativo](evidence-operator-20261128-r01/operator.json)

| Braço no mesmo backend CPU | Frames endereçáveis | SET de pesos | ID físico do rank 1 na segunda geração | Resultado em relação ao controlo |
|---|---:|---:|---:|---|
| Planar, transferência tradicional | 40 | 15 | 13 | Reproduziu a referência independente |
| Arena protegida, troca de proprietário | 1 252 | 0 | 1 249 | Todos os bits iguais, nas duas gerações |
| Arena protegida, troca omitida | 1 252 | 0 | 13 | Repetiu a primeira geração e divergiu na segunda |

Cada braço calculou três projeções MXFP4 de 2 880 × 2 880, para quatro ranks e comprimentos 1, 20 e 32, em duas gerações drenadas. Todos os 3 663 360 valores F32 por braço eram finitos. O alvo numérico desta fixture usa cinco registos deterministas, com 13 219 200 B de payload cada. O candidato pré-inicializou os cinco, protegeu a arena de 16 553 803 776 B virtuais e trocou a associação do rank entre gerações. No produto, as faltas continuam a precisar do respetivo payload. O scope completo de compilação, três braços e verificações atingiu 228 356 096 B e zero swap em 1,271 s. As temperaturas máximas amostradas foram 57,50 °C na CPU, 40,68 °C na RTX e 33,85 °C no NVMe. A RTX foi observada como sensor. Zero forwards de modelo e zero pedidos HTTP. Energia desconhecida.

**O que o source permite.** No pin `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`, `llm_graph_context::build_moe_ffn` já fornece `ids_gemm` às projeções e os IDs lógicos originais aos biases e escalas. A wave seguinte depende de uma vista do resultado acumulado da anterior. O gestor preenche os pares reais e os lugares de parking sob mutex. Estas fronteiras permitem experimentar um frame físico para as matrizes conservando os IDs do router e a ordem de redução. Os hashes SHA-256 de `src/llama-graph.cpp` e `src/llama-moe-stream.cpp` são `d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288` e `584aecb73900aa1164f00ec93126bc5b8b07c4d330d0f421641331b0c278d5a0`. A ordem de duas waves de uma camada não prova a libertação de um frame partilhado pelo último consumidor de outra camada ou tile.

**Decisão de investimento.** NO_GO para uma reescrita integral com os mecanismos avaliados neste portátil. A alternativa que conserva todas as cópias falha até ao preço favorável. Com entrega CPU idealizada o piso integral de P106 ainda é 10,549 s. A margem creditada é 97,448 ms para esperas, captura, coordenação e cleanup no caminho crítico. O próximo discriminante é uma camada routed com um consumidor atrasado e promoção/captura concorrentes. Identificar o último consumidor e a geração do frame, comparar com a mesma agenda em cópia e um controlo independente, e verificar parking, biases, máscaras e cada redução antes de cronometrar. Reabrir um executor novo se a medição revelar uma espera que a interface atual não pode remover e houver margem no pedido integral. O melhor pedido nominal HTTP medido mantém 17,689 s e 5,357 tok/s. R0 slots40-persistent, M3 PARTIAL e M4 NOT_MET. [Preços por braço e por dispositivo](tiers-result.md) · [Conservação do banco inteiro](frames-result.md)

O primeiro pedido de scope foi recusado pelo systemd antes de existir um processo da fixture. O comando e a mensagem ficaram no arquivo. O segundo usou uma identidade nova e aplicou o limite de core com `prlimit` ao processo filho. O arquivo privado inclui as três saídas F32, o ELF, a telemetria, a janela C55 e a falha inicial. [Falha preservada](evidence-operator-20261128-r01/prelaunch.json) · [Arquivo verificado](evidence-operator-20261128-r01/archive.json) · [Comandos, versões e hashes](evidence-operator-20261128-r01/provenance.json)

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/operator.py" check "$S/evidence-operator-20261128-r01/operator.json"
```
