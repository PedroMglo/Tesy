# Serviço no NVMe das primeiras procuras obrigatórias

**NO_GO com os preços observados e o resto do pedido fixo.** Para chegar a primeiro conteúdo final em 10 s no T2 nominal, restavam 4,003104286 s para 875 trabalhos no NVMe. Mesmo concedendo despacho perfeito dentro de cada grupo, as duas travessias físicas exigiriam 5,742773394 e 5,691524326 s com as durações de syscall observadas. Faltaram 1,740 e 1,688 s. Preservar as libertações por wave e apenas retirar os outros trabalhos, cópias e cálculo das callbacks ficou aquém nas duas observações. [Protocolo](protocol.md) · [Plano autenticado](plan.md) · [Recibo físico de ambos os braços](physical/receipt.json)

| Medição em segundos | Travessia 1 | Travessia 2 |
|---|---:|---:|
| Soma dos pisos por grupo, com quatro workers | 5,742773 | 5,691524 |
| Piso nos 165 grupos do prefill, 567 trabalhos | 3,573292 | 3,521460 |
| Piso nos 276 grupos do decode anteriores ao primeiro conteúdo final, 308 trabalhos | 2,169481 | 2,170064 |
| Soma dos makespans de despacho à barreira | 6,050554 | 5,996193 |
| Soma da união de leituras de cada grupo | 6,024619 | 5,971242 |
| Soma das durações dos syscalls nos workers | 13,859564 | 13,747700 |
| SHA-256 dos payloads após as barreiras | 4,769809 | 4,771414 |
| Amostragem do monitor durante a travessia | 2,291613 | 2,235883 |
| Travessia completa, incluindo intervalos e verificação | 13,293567 | 13,184701 |

**Como interpretar o relógio.** Para cada grupo o piso é o máximo entre a maior cadeia obrigatoriamente serial das três componentes de um expert e a soma dos tempos de serviço dividida por quatro. Somam-se apenas os pisos de grupos sequenciais. Em 288 das 441 waves havia um único trabalho, ocupando 2,094252 e 2,065138 s do piso. As leituras das duas travessias corresponderam a 92,16% e 91,33% do piso de 6,231568365 s do journal. O máximo admissível era 64,24%. Com os 5,996895714 s exteriores às callbacks da conversa conservados, os pisos condicionais do primeiro conteúdo final tornam-se 11,739669 e 11,688420 s. Esses valores combinam preços da fixture e trabalho observado da conversa; nenhum cliente recebeu uma resposta durante a fixture.

**Integridade e recursos.** Ambos os processos leram o mesmo inode no NVMe interno em Btrfs, com O_DIRECT e os quatro workers. Em cada travessia validaram-se 2 625 componentes, 11 566 800 000 B lógicos e 11 577 561 088 B alinhados. Os 2 625 hashes SHA-256 dos payloads coincidiram, incluindo a ordem. O contador do namespace completo avançou 22 612 424 setores de 512 B em cada processo; este contador abrange também atividade alheia. Os 61 pontos de admissão ocuparam 60,205 e 60,150 s. AC/performance, zero swap, sem forwards ou trabalho na GPU. Os picos do cgroup foram 183 721 984 e 183 525 376 B de um teto de 256 MiB. O processo completo ocupou 73,82 e 73,67 s. Picos CPU 60,0/55,875 °C, GPU 44,38/44,72 °C e NVMe 38,85 °C. O estado da cache interna do SSD ficou desconhecido. [Manifesto e digests de telemetria](physical/receipt.json)

**Condição de reabertura.** Seria necessária uma observação com serviço suficiente para caber no orçamento ou uma intervenção que mudasse o número de leituras obrigatórias, o ponto causal em que os bytes podem chegar, ou o restante caminho do pedido. O resultado qualifica o recorte de libertações desta conversa e destas duas medições no NVMe. Os critérios completos de M3/M4 continuam vigentes. [Limite no pedido original](../mandatory.md)

A preparação dos metadados está descrita no plano. Para reexecutar as travessias na máquina, a partir da checkout congelada `007056b5a76b7032b196a34ecc14c12cb875aab9`, escolher duas novas identidades de scope e novas saídas, obter uma C55 contemporânea admissível e conservar o GGUF autenticado do recibo de colocação. Usar o mesmo plano selado em ambos. Executar cada comando no respetivo scope limitado a 256 MiB e swap zero, com telemetria, limites e C118 aplicados pelo runner.

```sh
runner=research/qualification-retake/phase_fd/integrated/cold_read_fixture/runner.py
python3 -IB "$runner" --commit "$COMMIT" --arm 1 --plan "$PLAN" --plan-sha256 "$PLAN_SHA" \
  --placement "$PLACEMENT" --c55 "$C55" --c55-sha256 "$C55_SHA" --unit "$UNIT1" --new-output-dir "$R1"
python3 -IB "$runner" --commit "$COMMIT" --arm 2 --plan "$PLAN" --plan-sha256 "$PLAN_SHA" \
  --placement "$PLACEMENT" --c55 "$C55" --c55-sha256 "$C55_SHA" --unit "$UNIT2" --new-output-dir "$R2" \
  --first-dir "$R1" --first-sha256 "$R1_RECEIPT_SHA"
```
