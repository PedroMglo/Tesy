# Que parte do volume de prefill voltou ao disco dentro da chamada de 148?

Os dois journals do pack contêm **230 leituras** de um expert já consumido numa tile anterior da mesma chamada, 123 em CPU e 107 em CUDA. Pediram e receberam **3 041 034 240 B** de janelas alinhadas para **3 040 416 000 B** de pesos. As duas classificações por geração e os 125 IDs do target coincidiram. Este é o teto de volume da intervenção. A simultaneidade nos 40 slots, a latência que cada leitura expõe e o estado de entrada no decode determinam o ganho realizável. [Protocolo](reload-protocol.md) · [Recibo](reload-result.json)

| Chamada · tile | Reservas CPU | Recargas CPU | Reservas CUDA | Recargas CUDA |
|---|---:|---:|---:|---:|
| 5 · 1 | 40 | 0 | 11 | 0 |
| 148 · 1 | 193 | 0 | 133 | 0 |
| 148 · 2 | 38 | 3 | 31 | 3 |
| 148 · 3 | 107 | 20 | 92 | 21 |
| 148 · 4 | 79 | 45 | 72 | 38 |
| 148 · 5 | 351 | 55 | 116 | 45 |

Cada uma das 2 354 gerações teve um READ, três componentes servidas e um primeiro consumidor na mesma wave da reserva ou na seguinte. Das 1 263 reservas de prefill, 1 033 ficam fora da população de recargas. A primeira procura pode ter sido um hit. A chamada de 5 e os 46 passos de decode conservam todos os seus carregamentos. O valor 184 na C135 pertence ao trace e ao histórico daquela experiência. [Linhagem e conservação dos jobs P97/P106](../../../../../../../../../../../igpu_resident_rank/request_budget/device/pack_native/natural_trace/prefill_retention/request_cost/README.md)

**Composição condicional.** A 4,5 GB/s, evitar todas as 230 leituras acomodaria os 224–360 MB necessários se as cinco verificações novas fossem gratuitas. Restariam **0,626 ou 0,596 s** para todos os seus custos adicionais expostos antes do primeiro final, incluindo qualquer custo de retenção. Se esses grupos consumirem todo o orçamento de decode para exatamente 6 tok/s, a redução exigida sobe para 4 084 913 478 B nos dois preços. Mesmo o teto deixa **1 043 879 238 B** em falta. Com seleção perfeita apenas entre os grupos já temporizados, ficam por cobrar **4 546 227 739 B**. NO_GO nessas duas condições, INCONCLUSIVE para a combinação mais favorável. Combinámos o preço das propostas e o piso do contador de processo da parte 185 com IDs de geração dos dois outros processos. Atribuir esse volume a tempo poupado no cliente requer uma intervenção emparelhada no mesmo processo. [Relógios e hipótese de banda](io.md) · [Preço do decode](context.md)

Pré-registo `a4d609ba`, código `6a839517cd24536eb2056540f2f8f39e7194364e`. Quatro controlos cobrem hit herdado, preload, identidade por camada e separação de chamadas. As duas leituras autenticadas produziram o mesmo SHA-256 `32f91f7a2a5922e558e597e60589f176d3951c981cd49bf83580bba7b59433ae` em 1,71 e 1,58 s, com picos de cgroup de 90,6 e 60,5 MiB, zero swap, GPU ou forwards. A parte 188 preserva ambos os resultados e logs, 9 924 B em quatro ficheiros. [Verificador](reloads.py) · [Manifesto](../../../../../../../../../../../private_archive/part-188.json)

```sh
python3 -IB "$HTTP/reloads.py" --archive "$AR" --io "$IO_REVIEW" --context "$FILTER_REVIEW" \
  --capture "$CAPTURE" --verified "$VERIFIED" --plan "$PLAN" \
  --commit "$MEASUREMENT_COMMIT" --new-output-dir "$NEW"
```
