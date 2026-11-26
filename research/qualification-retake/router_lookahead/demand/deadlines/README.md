# Uma oferta certa chega a tempo de substituir a leitura?

**O prefill CPU do C292 tem a maior margem para um worker assíncrono.** Dos 222 acertos da projeção nesse tier, uma FIFO que lê também as ofertas erradas terminaria 140 leituras inteiras a tempo a 4,5 GB/s, ou 160 a 8 GB/s. No decode CPU, os mesmos cenários permitem 1 e 35 dos 69 acertos. São contagens condicionais aos prazos históricos e a um dispositivo disponível para a antecipação. Nenhum destes números mede espera eliminada. [Pré-registo](protocol.md) · [Seleção e cobertura do estudo pai](../README.md) · [Recibo com as distribuições](receipt.json)

As três tiles de prefill e quatro posições de decode com ativações arquivadas fornecem 243 decisões +1. Das 553 ofertas (até quatro por destino e tile), 432 coincidem com a primeira geração ausente que o destino realmente pede. Em **180 das 432** o manager já reserva essa geração durante uma wave anterior à do primeiro consumo. O revisor liga reserva, aceitação FIFO pelo worker, READ, três SET, publicação, procura e barreira por identidade de geração. A cobertura temporal usa o mesmo processo C292 que forneceu todas as 4 501 leituras reais do pack. A ponte numérica anterior reconcilia as ativações e os 3 400 quartetos ordenados com o C270. [Verificador](score.py)

## Três prazos para um registo completo

O instante inicial é o fim da **última callback de remap** da camada fonte na mesma tile. O FFN dessa camada ainda pode estar por executar. Cada leitura ocupa o dispositivo durante 2,938198 ms a 4,5 GB/s ou 1,652736 ms a 8 GB/s (arredondamento superior ao ns). No oráculo só entram acertos verdadeiros e os prazos são conhecidos. Todos têm custo igual; ordená-los pelo prazo e rejeitar o próximo quando a conclusão já não cabe maximiza o número de leituras completas. Os intervalos desde a oferta até ao último prazo relevante de sítios consecutivos não se sobrepõem no arquivo. A FIFO causal envia todas as propostas pela ordem selada, sem consultar a procura, e transporta qualquer backlog até ao sítio seguinte. A FIFO submete **7 311 704 064 B** de leituras simuladas, incluindo **1 599 848 448 B** das 121 ofertas sem um job elegível.

| Prazo no C292, ambos os tiers e ambas as fases | Oráculo 4,5 GB/s | FIFO 4,5 GB/s | Oráculo 8 GB/s | FIFO 8 GB/s |
|---|---:|---:|---:|---:|
| Reserva oficial E11, na wave de reserva | 122 | 115 | 211 | 187 |
| Antes de o worker aceitar E13 e de o consumidor abrir a espera E19 | 216 | 199 | 294 | 257 |
| Abertura da espera E19 na primeira wave de consumo, concedendo redirecionamento do serviço anterior | 237 | 222 | 304 | 274 |

E10 identifica a lista de gerações necessárias da wave de consumo. E19 abre a verificação de que todas estão prontas. O método separa a identidade de quem as reservou e de quem as consome. Para evitar a duplicação de um READ já aceite conservou-se também o prazo E13, usando o **mínimo** de E13 e E19. E20 já inclui serviço pelo qual o consumidor esperou.

| Trabalho com prazo min(E13,E19) | Acertos | Oráculo / FIFO a 4,5 GB/s | Oráculo / FIFO a 8 GB/s |
|---|---:|---:|---:|
| Prefill CPU | 222 | 156 / 140 | 189 / 160 |
| Prefill CUDA | 97 | 52 / 51 | 58 / 54 |
| Decode CPU | 69 | 1 / 1 | 39 / 35 |
| Decode CUDA | 44 | 7 / 7 | 8 / 8 |

## Quanto pode demorar o projetor?

Subtrair o serviço de uma leitura inteira ao **primeiro prazo a vencer entre os acertos daquele sítio**, mantendo o disco inicialmente livre, dá o atraso máximo que se poderia introduzir para entregar essa chave. A 4,5 GB/s esta folga é não negativa em **79/182** sítios com acerto, ou **79/243** de todos os sítios (32,5%). A 8 GB/s são **121/182**, ou **121/243** (49,8%). Se se puder escolher qualquer acerto, inclusive aquele cujo prazo vence mais tarde, caberia pelo menos um em 102/243 e 141/243 sítios, respetivamente. O custo do projetor efetivamente integrado continua por medir.

| Prazo do primeiro acerto a vencer, min(E13,E19) | Sítios com acerto / todos | Cabem a 4,5 GB/s | Mediana da folga (ms) | Cabem a 8 GB/s | Mediana da folga (ms) |
|---|---:|---:|---:|---:|---:|
| Prefill CPU | 71 / 72 | 71 | +0,914 | 71 | +2,199 |
| Prefill CUDA | 28 / 31 | 4 | −1,414 | 7 | −0,129 |
| Decode CPU | 57 / 96 | 1 | −1,154 | 39 | +0,132 |
| Decode CUDA | 26 / 44 | 3 | −1,924 | 4 | −0,638 |

**Decisão.** Há margem nos dois preços para testar publicação e leitura assíncronas em prefill CPU do C292. O limite favorável do decode a 4,5 GB/s é **8/113 acertos** considerando os dois tiers. Para converter uma chegada em prontidão do expert, ainda é preciso cobrar projeção, I/O concorrente, staging, três SET, posse do slot e sincronização. Antecipar serviço pode mover a própria wave que define o prazo. A sessão instrumentada contém as ativações de uma parte do trabalho fornecido de 189+32 tokens e o modelo não atribui serviço às tiles e camadas sem sinal. Não se mediram alterações de parede, dos 10 s/6 tok/s ou da conversa C281.

Protocolo `129f4519`, código `143d7e36`. Os três testes cobrem o agendamento por comparação exaustiva com permutações pequenas, a igualdade de prazo ao ns, desperdício que atravessa o próximo sítio e um preload de wave anterior com procura posterior. Duas reproduções na checkout limpa, 0,99/1,01 s e 200 456/199 316 KiB RSS. Ambas produziram o SHA-256 `f953723d30a144f2eece5dd8af2457c9f172a0a0c4ad9f542ad31b4f4a3d6e0b`. No comando abaixo, `BUNDLE` é a pasta do manifesto privado das 39 fatias e `ORIGINAL` contém o recibo do estudo pai com SHA `5e83418c…2c05`. [Teste de prazos](test_score.py)

```sh
env LC_ALL=C PYTHONUTF8=1 PYTHONCOERCECLOCALE=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 90 prlimit --as=536870912 -- "$TESY_REPO/.venv/bin/python" -IB "$UNIT/score.py" \
  --part23 "$ARCHIVE/part-23" --part95 "$ARCHIVE/part-95" --c7 "$C7" \
  --bundle "$BUNDLE" --original "$ORIGINAL" --new-output-dir "$NEW"
```
