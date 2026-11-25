# A agenda de duas tiles ainda deixa 334–366 ms por recuperar

**Neste segundo turno do portátil, mudar apenas a agenda de prefill não chega aos 10 s para o primeiro conteúdo final.** A política de prioridade e banco pede ao disco 1 058 payloads, ou **13 985 913 600 B úteis**. À banda de cenário de 4,5 GB/s, só estes bytes custam 3,107981 s. As 205 lacunas drenadas entre camadas somam mais 1,151151 s na execução serial. O pipeline causal mais favorável aqui admitido pode ocultar até 0,791666 s dessa parcela. Mesmo realizando toda a sobreposição gratuita, sobram 0,359485 s expostos. [Recibo das duas reproduções](evidence/receipt.json) · [Pré-registo](protocol.md)

| No mesmo T2 ON | Pack após GGUF (RP) | Pack antes de GGUF (PR) |
|---|---:|---:|
| Preço condicional do decode, exterior R0 + READ + SET comuns | 7,084608 s | 7,116859 s |
| Teto com 47 saídas / com 46 avaliações | 6,6341 / 6,4929 por s | 6,6040 / 6,4635 por s |
| Orçamento que fica para o prefill | 3,133747 s | 3,101496 s |
| Lacuna máxima a 4,5 GB/s, depois de pagar o payload | +25,766 ms | −6,485 ms |
| Défice com a agenda serial e a banda fixa | 1,125385 s | 1,157636 s |
| Défice com o pipeline otimista e a banda fixa | **0,333719 s** | **0,365970 s** |
| Banda útil mínima com as lacunas seriais | **7,054 GB/s** | **7,171 GB/s** |
| Banda útil mínima com o pipeline otimista | 5,041 GB/s | 5,101 GB/s |
| Banda útil mínima concedendo zero a todas as lacunas | 4,463 GB/s | 4,509 GB/s |

O orçamento de prefill e decode somados é 10,218355216 s, calculado com o primeiro final e as durações nativas do próprio T2. Os dois preços aplicam as leituras físicas dos 797 jobs de decode do pack, conservam o exterior de R0 e cobram os SET com correspondência no mesmo sítio. O débito divide as 47 saídas de produto, ou alternativamente as 46 avaliações de uma posição, pela mesma duração. A quantidade de trabalho não muda com a unidade do débito. A exatamente 6 por segundo, o orçamento de prefill baixa para 2,385022 s ou 2,551689 s, respetivamente. Nesses cenários, ainda faltam 1,082444 s ou 0,915777 s com o pipeline otimista. [Preço físico do decode, custos assumidos e limites](../replay/decode_clock/transport/service-result.md) · [Relógios do pedido](../accounting.md)

## Onde a sobreposição termina

O cliente parte de 2 044 posições em cache. A chamada de 5 tokens exige 34 leituras de disco e 25 admissões do banco. A chamada de 148, em tiles 32/32/32/32/20, exige 1 024 leituras e 201 admissões do banco. As duas dependem de 1 284 entregas ao primário. A métrica de banda usa o payload dos pesos. Com alinhamento, as solicitações ao pack são 13 988 757 504 B no prefill. As durações dessas leituras e das entregas às camadas ainda não foram medidas para este candidato no grafo. [Política e população reconstruídas](../replay/README.md)

Os estágios A (camadas 0–24) e B (25–35) podem trabalhar sobre tiles adjacentes respeitando o residual da própria tile, o KV das precedentes e os dois retornos. O cálculo concede até todas as lacunas elegíveis entre os estágios, incluindo transições ambíguas. Ficam **150,239 ms** na chamada de 5, **200,166 ms** na cabeça A da primeira tile da chamada de 148 e **9,080 ms** na cauda B da última tile. A melhor ordem de transporte deixaria conservar apenas 2,24% das lacunas do R0. Na outra ordem, o payload sozinho já ultrapassa o orçamento em 6,485 ms. Estes preços pressupõem os mesmos pedidos ao disco, as mesmas lacunas protegidas e a mesma autoridade para libertar trabalho por camada. [Dependências e regra de liberação](../../../../tile_pipeline/protocol.md)

Nos relógios host do R0, a chamada de 148 durou 10,390470 s. A posição dos marcadores admite no máximo 2,270165 s de sobreposição naquela chamada com aqueles preços de serviço. As quatro primeiras tiles terminam as callbacks na camada 34 e a última chega à 35. Ao passar para o cenário do pack, o custo serial já substitui aquele serviço por V/b. Por isso, o único crédito adicional da agenda é a parte elegível das lacunas, até 0,791666 s. O PFJ constata a sequência host e não mede a execução simultânea dos kernels.

**A decisão de engenharia é medir a taxa útil efetiva e as entregas do próprio prefill de 1 058 leituras antes de construir esta agenda.** Os requisitos de 7,054–7,171 GB/s em série e de 5,041–5,101 GB/s mesmo com a agenda ideal excedem a referência nominal de 4,5 GB/s. Para baixar o requisito podem mudar o volume que realmente chega ao NVMe, os custos das camadas nas pontas ou o decode. A banda de cenário e os tempos das lacunas conservadas são premissas. A execução do candidato no chat, os SET sem preço, as interações com os quatro workers e a exatidão de uma implementação com duas tiles ficam por demonstrar.

## O que permite o enlace do SSD

No portátil, depois dos ensaios físicos e em repouso, sysfs devolveu 16,0 GT/s ×4 como estado atual e máximo tanto para o NVMe Micron 2400 (`0000:c1:00.0`) como para a sua ponte (`0000:00:02.1`). À codificação 128b/130b da Gen4, isso corresponde a no máximo 7,877 GB/s por sentido antes dos pacotes. Por si só, esse teto não separa os cenários de 7,171 e 5,101 GB/s. O tamanho de payload PCIe negociado ficou desconhecido. A conta corrente tem acesso aos atributos de ligação em sysfs e não conseguiu ler o registo de configuração Device Control. A especificação de 4,5 GB/s da unidade aplica-se ao ensaio sequencial do fabricante. [Especificação e regime do fabricante](../../../../../../dual_store/capacity.md) · [Taxa de transmissão e overhead de pacotes, Intel AN855](https://cdrdv2-public.intel.com/666287/an855-683504-666287.pdf)

```sh
for bdf in 0000:c1:00.0 0000:00:02.1; do
  cat /sys/bus/pci/devices/"$bdf"/{current_link_speed,current_link_width,max_link_speed,max_link_width}
done
```

## Reprodução

Pré-registo `ade35288`, método `d375ada0`. Os três testes cobrem a fronteira inclusiva, o caso sem banda finita, a conservação por fase e a preservação de falha em destino exclusivo. Duas execuções sequenciais em checkout limpa leram as partes 63 e 66. R01 custou 0,68 s de parede e 77 696 KiB de RSS máxima. R02 custou 0,54 s e 77 968 KiB. Ambos os recibos têm SHA-256 `5225590f4a5ea17f7faa1d13fede10dc9abc771d53dbc388333709a4d86765c2`. O custo refere-se apenas à análise offline. [Implementação](screen.py) · [Testes](test_screen.py)

```sh
F=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/prefill_frontier
OPENBLAS_NUM_THREADS=1 python3 -IB "$F/test_screen.py"
OPENBLAS_NUM_THREADS=1 python3 -IB "$F/screen.py" \
  --part63 "$ARCHIVE/part-63" --part66 "$ARCHIVE/part-66" \
  --new-output-dir "$NEW"
sha256sum "$NEW/receipt.json"
```
