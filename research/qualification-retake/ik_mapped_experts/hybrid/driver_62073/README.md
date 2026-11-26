# O callback do grafo e o banco CUDA no 120B original

**GO para isolar o percurso dos pesos no NVMe.** Na RTX 4060 com o driver 620.73.04, os mesmos 402 176 logits F32 coincidiram bit a bit entre ON e OFF para cada banco e entre os bancos de 161 e 288 slots. O prefill recebeu 16 IDs e o passo seguinte recebeu o token 976. Os dois máximos únicos foram 3659 e 3992. Em OFF, os pedidos de matriz, os intervalos do GGUF, os slots de destino e os contadores por largura coincidiram com o respetivo ON. As rotas individuais ordenadas são observáveis em ON, onde os 597 quartetos também coincidiram entre os bancos e com o driver anterior. A instrumentação passiva em OFF permite verificar os bytes servidos. A ordem de ranks individuais em OFF fica DESCONHECIDA. [Protocolo congelado](real-protocol.md) · [Recibo compacto dos quatro braços](result.json)

| Braço na ordem física | Prefill entre ACKs, s | NVMe do scope no prefill, GB | Token fornecido entre ACKs, s | NVMe do scope nesse passo, GB | Vida do filho, s | Pico global de VRAM, MiB |
|---|---:|---:|---:|---:|---:|---:|
| ON 288 | 20,272 | 42,525 | 3,735 | 7,344 | 26,409 | 6 208 |
| OFF 288 | 19,284 | 41,573 | 3,655 | 7,122 | 25,440 | 6 198 |
| ON 161 | 18,372 | 40,831 | 3,669 | 7,304 | 24,535 | 4 608 |
| OFF 161 | 19,324 | 41,312 | 3,584 | 6,969 | 25,416 | 4 598 |

Todos os prefills enviaram 14 752 627 200 B de matrizes. No token fornecido, o banco maior enviou 1 692 057 600 B e o menor 1 837 468 800 B. O maior evitou 11 reposições e 145 411 200 B. Nos dois braços observados, em cada uma das 36 camadas e duas chamadas, as três multiplicações correram na GPU e as três adições de bias na CPU. Todos os filhos encerraram, com zero swap e 2 MiB de VRAM no fim. Os controlos C110, stock e ik CPU reproduziram os dois máximos. Os logits do ik CUDA diferem bit a bit das três referências independentes. [Evidência numérica e dispositivos por braço](result.json)

**O observador deixou de ser uma explicação suficiente para o volume de I/O.** Em OFF, o namespace inteiro registou 48,71 e 48,30 GB durante a vida dos processos. Os contadores do cgroup e do PID por fase, os refaults, o tempo de cleanup e o eventual intervalo entre a última amostra e a leitura final encontram-se no recibo. Mesmo em OFF permanecem os hooks de cópia/submissão e a telemetria. A ordem fixa, uma amostra por braço e page cache natural só permitem tratar as diferenças de segundos como DIAGNÓSTICO. Primeiro conteúdo final, tempo de resposta válida e tok/s nominal continuam por medir nesta receita. M3 PARTIAL e M4 NOT_MET.

## Recuperação e qualificação no portátil

O arranque tinha o módulo 620.70.06 carregado e dois firmwares dessa versão em falta. A CUDA de sistema devolveu 803 e a biblioteca 620.70.06 devolveu 999. A recarga transitória dos módulos instalados recuperou a RTX às 11:59 UTC. CUDA e NVML identificaram o mesmo PCI, driver 620.73.04 e 8 188 MiB de VRAM. Esta intervenção não alterou a configuração de arranque. O ensaio não verificou um reinício seguinte.

A fixture independente executou RESIDENT, BANK9 e BANK7, 32+1 posições. Todos os homólogos reproduziram logits, quartetos e dispositivos da versão anterior. BANK9 reproduziu os 1 056 F32 do residente. BANK7 voltou a mudar cinco máximos no prefill. Os três picos amostrados foram 134, 130 e 126 MiB. O scope de 2 GiB atingiu 599 871 488 B e zero swap. A seguir, o contexto 8192 do 120B abriu sem forward com 288 slots, 108 matrizes mapeadas, 108 pares de bias e zero H2D inicial de matrizes. O pico foi 6 150 MiB, com 2 MiB no fecho e zero swap. [Fixture e stop conditions](protocol.md) · [Arquivo de enumeração, fixture e capacidade](../../../private_archive/part-143.json)

A unidade usou o Ryzen AI 9 HX 370, a RTX 4060 Laptop, o NVMe interno e o GGUF original de 63 387 346 208 B. O commit dos três processos pequenos foi `a2974e1c`. O commit de capacidade e dos quatro processos grandes foi `e7815dc6179d8b8d1a740cd9dc6f7f0d8ebaeb7b`. Cada família tem C55 novo e cada processo C118 próprio. No total, três inícios da fixture, cinco inícios do 120B, oito forwards C110 do 120B, zero pedidos HTTP e zero downloads. O consumo energético integrado ficou DESCONHECIDO. Os originais e o arquivo produziram o mesmo JSON de revisão. [Arquivo de paridade e revisão](../../../private_archive/part-144.json)

## Próximo discriminante e memória a cobrar

TRACE_DERIVED. Reconstituir por ordem cada SET dos braços OFF dá 2 547 e 2 544 transferências no prefill. O maior SET contém 26 438 400 B. Um scratch reutilizado após cada conclusão precisa de 26 439 680 B para preservar o offset dentro da página. Reter todos os SET de uma camada até uma única barreira requer até **648 155 136 B** nos dois braços. No token fornecido esse pico cai para 52 936 704 B. A cache de ficheiro partilha com esse scratch o orçamento de RAM. A duração de uma barreira ou transferência futura permanece DESCONHECIDA. [Picos e fingerprints ordenados](staging-capacity.json) · [Verificador sem modelo](schedule.py)

O ensaio de serviço deve manter o mesmo destino e os bytes selecionados e comparar a origem mapeada com um buffer explícito de host. O controlo também reserva o scratch, preserva o alinhamento e paga as mesmas barreiras. Medir o custo de encher o scratch, submeter o H2D e aguardar o último consumidor, com o estado inicial das páginas observado. A API CUDA permite que uma transferência assíncrona a partir de memória paginável faça staging ou sincronização internos. A documentação não quantifica esse custo neste portátil. [Semântica da API no CUDA 13.3](https://docs.nvidia.com/cuda/archive/13.3.0/cuda-runtime-api/api-sync-behavior.html) · [Antecedente de transporte com origem quente](../warm_transfer/physical/README.md)

## Reproduzir

```sh
python3 -IB research/qualification-retake/ik_mapped_experts/hybrid/driver_62073/review_real.py \
  --tiny "$TINY" --tiny-sha256 2e335fc94cbd2c07c05958890e481db70b882e2ec71a34d29b0be3db775a15ea \
  --capacity "$CAP" --capacity-sha256 0101f07a0d8267562b0169f6e93ee53885a183a0db818c06d30406c8ff792c0d \
  --pair "$PAIR" --pair-sha256 97291f30c38c5f29fe9c5a6a08aaa3fd0d21b7132da486e2ca54a09244c1b502 \
  --plan "$PLAN_C283" --historical "$ON_62070" --c110-parent "$C110_RESULTS" \
  --stock-file "$STOCK_LOGITS" --cpu-d0 "$CPU_D0" --cpu-d1 "$CPU_D1" --new-output-dir "$NOVO"
```

`TINY` e `CAP` são as famílias `tesy-ik-hybrid-device-sys73-20261126-r01` e `tesy-ik-e10-capacity-sys73-20261126-r01` no lote 143. `PAIR` é `tesy-ik-e10-full-parity-sys73-20261126-r01` no lote 144. O plano vem do lote 138 e o par ON anterior do lote 141. [Referências e caminhos do par anterior](../full_parity/README.md)
