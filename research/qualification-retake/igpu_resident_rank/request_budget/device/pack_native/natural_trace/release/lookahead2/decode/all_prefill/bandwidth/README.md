# O primeiro final determina a banda necessária

**No P106 com o sinal RANKS observado, a banda útil mínima do cenário está entre 4,829 e 4,830 GB/s.** A 4,829 GB/s faltam 0,720 ms para o primeiro final em 10 s. A 4,830 GB/s sobram apenas 0,200 ms para qualquer trabalho novo antes desse final; o decode tem 3 544,688 ms de margem para 47 saídas a 6 tok/s. Se tanto a previsão +1 como a autoridade local ficarem disponíveis na fronteira mais cedo permitida pelo grafo, o mínimo desce para **mais de 4,258 e até 4,259 GB/s**. O instante em que os pesos se tornam antecipáveis muda o requisito em cerca de 571 MB/s. [Recibo](receipt.json) · [Protocolo](protocol.md)

| Conversa | Liberação do sinal | Mínimo do decode sozinho (GB/s) | Mínimo para os dois relógios (GB/s) | Margem do primeiro final a 4,5 GB/s |
|---|---|---:|---:|---:|
| P97 | Fronteira anterior | (1,928; 1,929] | (3,558; 3,559] | +1 315,099 ms |
| P97 | RANKS observado | (2,061; 2,062] | (3,908; 3,909] | +759,616 ms |
| P106 | Fronteira anterior | (1,959; 1,960] | (4,258; 4,259] | +262,365 ms |
| P106 | RANKS observado | (2,116; 2,117] | (4,829; 4,830] | −325,789 ms |

Nos quatro casos o relógio limitante é o primeiro final. Os intervalos dão o último ponto que falha e o primeiro admissível, a 1 MB/s de resolução decimal. Conservam a mesma agenda R0, a seleção FREQ353, quatro identidades por destino, staging transitório e preços observados dos três SET. O prefill compra 966 payloads do pack e 297 do banco. O decode compra 1 015 e 76, respetivamente. A projeção, o serviço do banco e a coordenação ainda consomem a margem se ficarem expostos. A bissecção é válida porque aumentar a taxa permite reproduzir qualquer alocação de EDF do ritmo anterior, e reduzir a duração do transporte só pode manter ou baixar o máximo com os SET. [População e prazos por geração](../README.md)

### Enlace, ficha do SSD e serviço observado

A identificação recolhida para `nvme0` foi Micron `MTFDKBK1T0QFM-1BD1AABGB`, firmware `V3MA101`, enlace PCIe negociado de 16 GT/s ×4. Com codificação 128/130, o máximo teórico unidirecional fica em 7,876923 GB/s antes de pacotes e restantes despesas de protocolo. Para cada 13 219 200 B úteis, o C291 pede uma janela de 13 221 888 B. Se toda a janela transitar no enlace, o teto útil antes dessas despesas cai para **7,875322 GB/s**. Neste regime, 8 GB/s úteis exigiriam que parte do serviço viesse de outro tier ou que mudasse o caminho físico. Mesmo no teto de 7,875322, a margem do primeiro final P106 com RANKS seria só 1 522,026 ms. [Identidade e método do SSD](../../../../../../../../../../dual_store/capacity.md)

A ficha Micron 2400 rev. C indica **4 500 MB/s de leitura sequencial** para a variante de 1 TB. A nota 11 especifica blocos de 128 KB, QD32 e unidade nova. O fim superior do intervalo P106 com RANKS é **7,33% superior** ao número comercial; o limite com liberação mais cedo fica 5,36% abaixo. A especificação tem aquele método de ensaio. As quatro leituras paralelas de um pedido real têm concorrência variável, tamanhos e prazos diferentes. [Micron 2400, ficha rev. C, tabela de capacidades e nota 11](https://www.mouser.com/datasheet/2/671/2400_ssd_product_brief-3476111.pdf)

| P e fase | READs do pack | União de READ (s) | Primeiro início ao último fim (s) | GB úteis/s pela união | GB úteis/s pelo intervalo |
|---|---:|---:|---:|---:|---:|
| P97 prefill | 1 263 | 6,189 | 9,599 | 2,698 | 1,739 |
| P97 decode 3–46 | 1 067 | 5,817 | 8,696 | 2,425 | 1,622 |
| P97 decode 47–48 | 24 | 0,131 | 0,231 | 2,421 | 1,373 |
| P106 prefill | 1 263 | 6,228 | 9,913 | 2,681 | 1,684 |
| P106 decode 3–46 | 1 067 | 5,736 | 8,942 | 2,459 | 1,577 |
| P106 decode 47–48 | 24 | 0,134 | 0,251 | 2,366 | 1,264 |

As três fases de cada processo têm os quatro workers representados. A união conta uma vez cada intervalo com pelo menos um READ em voo; o segundo denominador inclui os hiatos até à última conclusão. Por exemplo, no prefill P106 os workers somaram **20,444 worker-s** de READ numa união de 6,228 s. O numerador é a soma de payloads úteis do pack observados em R0, antes de subtrair qualquer hit contrafactual do banco. Estes valores caracterizam o serviço obtido naquelas janelas. Para decidir a viabilidade física é preciso observar a disponibilidade do sinal e o payload entregue aos mesmos prazos sob a política candidata. [Bytes, workers e ocupação por fase](receipt.json)

### Reprodução

Protocolo `3839b6bb`, código `af4526e1`. Os três testes sintéticos cobrem patamares, o extremo que falha, o relógio limitante e READs simultâneos; Ruff passou. R01/R02 leram só fontes e arquivos selados, numa CPU a nice +10 após o fecho de C292. Produziram os mesmos 11 173 B, SHA-256 `11cfef208de11890c1da9210029b00526dbbbe1b36085536de0fed2c5b9ccc7a`, em 8,27/8,23 s com RSS de 65 392/65 320 KiB. [Verificador](screen.py) · [Testes](test_screen.py)

```sh
python3 -IB test_screen.py
nice -n 10 taskset -c 4 timeout 90 prlimit --as=536870912 --cpu=90 -- \
  python3 -IB screen.py --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r01"
nice -n 10 taskset -c 4 timeout 90 prlimit --as=536870912 --cpu=90 -- \
  python3 -IB screen.py --archive "$PARTS" --backend "$C291" --new-output-dir "$FRESH/r02"
cmp receipt.json "$FRESH/r01/receipt.json" && cmp receipt.json "$FRESH/r02/receipt.json"
```
