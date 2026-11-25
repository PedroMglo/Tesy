# O que muda ao combinar duas intervenções abaixo do limiar individual?

**Com a cache CPU causal e os preços medidos do pack, aplicar a compressão máxima às identidades que inspecionámos só recupera 16,8–17,2 ms no pedido nominal.** Na nova agenda há 1 048 leituras no prefill e 918 no decode. Só 22 e 13, respetivamente, correspondem aos 64 experts da amostra. Mesmo com todas as lacunas do prefill gratuitas, faltariam 1,267–1,517 s. São projeções condicionais a tempos de serviço, com descodificação e remapeamento gratuitos. [Protocolo](protocol.md) · [Resultados por braço](evidence/receipt.json)

Ao extrapolar o **melhor** expert dos 64 para todas as leituras e oferecer de graça os 254 READ CPU sem preço observado no mesmo sítio, duas ordens cruzam os dois alvos nominais. A tabela mostra a margem de parede até ao primeiro conteúdo final em 10 s. O sinal positivo indica o que ainda poderia ser gasto quando o decode também couber a 6 tok/s. A referência usa o mesmo U1262 e quatro workers, com o estado produzido pela própria LRU em T1 e T2.

| Prefill/decode, ordem dos dois ensaios de leitura | Cache sem compressão, G=0 | Só os experts inspecionados, G=0 | Todos ao melhor tamanho, G=0 | Todos ao melhor tamanho, pipeline ideal | Custo uniforme admissível por READ sem preço em G=0 |
|---|---:|---:|---:|---:|---:|
| RP/RP | −1 505,5 ms | −1 488,2 ms | −147,5 ms | −507,0 ms | Sem margem |
| RP/PR | −1 534,5 ms | −1 517,3 ms | −172,3 ms | −531,8 ms | Sem margem |
| PR/RP | −1 283,4 ms | −1 266,6 ms | +41,7 ms | −317,8 ms | 293 452 ns |
| PR/PR | −1 312,4 ms | −1 295,6 ms | +16,8 ms | −342,7 ms | 118 390 ns |

**NO_GO para a suficiência do pipeline ideal de duas tiles aos preços congelados.** No limite que concede todas as lacunas, o sinal depende da ordem e dos pesos sem amostra. O orçamento uniforme é calculado nos 222 callbacks com leituras novas, admitindo a sobreposição entre os respetivos workers. As leituras observadas conservam o seu preço por sítio, ajustado ao tamanho suposto. Um READ do disco no novo desenho precisaria ainda de transportar bytes reais. Os SET conhecidos da CUDA e o exterior do decode continuam a contar. O custo de construção de T1, a paridade de todo o pedido e a medição no cliente permanecem por qualificar. [Quantização e cobertura](../README.md) · [Cache causal e preços por sítio](../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/global_residency/causal/README.md)

### Reprodução

Pré-registo `45f59f41`, código `a4769e04`. A primeira execução falhou antes da análise porque o Git tentou criar threads no limite de 512 MiB. O recibo ficou preservado. A versão `966eb4af` aplicou ao inventário Git a mesma leitura de índice de uma thread do controlo. Dois processos em checkout limpa reproduziram todos os 12 preços sem compressão e os dois cenários. Duraram 0,99 / 0,82 s, com RSS máxima de 81 868 / 82 016 KiB e SHA-256 do recibo `08c4f7fe5c8487202be6a24bb0b47e21a0f3bad155fd6dfc225f5b552ff389d3`. Dois testes cobrem o máximo READ→SET, a sobreposição dos READs novos e o arredondamento do orçamento. A parte 73 inclui as três reproduções, o preço marginal das páginas partilhadas e os três braços da camada CPU0. [FAIL de inventário](evidence/failed-inventory.json) · [Recibo do arquivo privado](evidence/archive.json)

```sh
U=research/qualification-retake/mxfp4_cross_role/causal_pool
python3 -IB "$U/test_prices.py"
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120s python3 -IB "$U/screen.py" \
  --archive "$ARCHIVE" --new-output-dir "$NEW"
```
