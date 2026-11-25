# Quanto custa adquirir os bytes das últimas 353 vítimas?

**Manter só os metadados em T1 elimina as cópias desse turno, mas falha os dois gates de T2.** Com expulsão prioritária dos experts recuperáveis, 253 das 353 chaves foram efetivamente procuradas fora do primário. Materializá-las apenas então exige 1 340 leituras de disco até ao primeiro decode, incluindo a reposição, e 1 071 no decode. O cenário nominal admite até 808 e 872, respetivamente. A materialização diferida ainda elimina 33 e 262 leituras face à LRU sem banco. O ganho líquido de latência da conversa fica **INCONCLUSIVE** porque as cópias e o seu efeito na fila não foram cronometrados. [Pré-registo](protocol.md) · [Recibo por fase, política e tier](evidence/receipt.json)

## Três custos para a mesma escolha causal

A escolha das 353 identidades usa somente o prefixo selado de T1. Em T2, um hit primário nunca materializa a cópia de RAM. Na ablação diferida, cada primeiro miss numa chave selecionada lê todo o expert, escreve a cópia de RAM e entrega o expert ao destino. O replay mantém os top-4, serve a mesma wave, disponibiliza a nova cópia depois dessa entrega e repõe os residentes originais antes do primeiro decode. A preferência de expulsão considera recuperável a chave selecionada mesmo quando a primeira materialização ainda vai exigir disco.

| Política e preparação | Leituras no prefill com reposição | Leituras no decode | Bytes GGUF imputados até ao primeiro decode |
|---|---:|---:|---:|
| LRU sem banco | 1 373 | 1 333 | 18 166 620 160 |
| LRU, captura de vítimas em T1 | 1 234 | 1 143 | 16 327 434 240 |
| LRU, leitura dos 353 no corte | 1 234 + 353 | 1 143 | 20 998 045 696 |
| LRU, materialização diferida | 1 370 | 1 256 | 18 126 929 920 |
| Expulsão prioritária, captura em T1 | 1 184 | 974 | 15 665 852 416 |
| Expulsão prioritária, leitura no corte | 1 184 + 353 | 974 | 20 336 463 872 |
| Expulsão prioritária, materialização diferida | 1 340 | 1 071 | 17 729 966 080 |

Os 353 registos requerem 4 670 611 456 B no GGUF ou 4 667 326 464 B no pack, além da escrita de 4 666 377 600 B de payload em RAM. A leitura no corte cobra-os integralmente ao pedido. A preparação diferida com expulsão prioritária paga 17 primeiras leituras na call de 5, 135 na de 148, quatro na reposição e 97 no decode. São 194 experts CPU e 59 CUDA, correspondentes a 3 344 457 600 B de escrita do banco. As restantes 100 escolhas não chegam a precisar de cópia. A LRU com banco diferido lê 249 chaves distintas, 104 ficam por materializar. Com a mesma política LRU, o banco diferido isoladamente poupa apenas três leituras no prefill e 77 no decode. [Autoridade das waves e do estado de entrada](../t1_primary_victim/README.md)

## Construção durante o primeiro turno

O prefixo cobre 73 retornos unitários nas posições 2 047–2 119 e dura 18,735327960 s da primeira entrada ao último retorno. **2 156** é o número de eventos de oferta de uma vítima READY; **1 698** é o número de identidades distintas oferecidas; **353** é a capacidade e o número de chaves no corte. Partindo do banco vazio no trigger, houve 2 143 instalações e 13 promoções de uma cópia já existente. As primeiras 353 ofertas foram distintas. A partir da oitava chamada observada, 2,838100445 s após a entrada, o banco independe do estado que tinha antes do trigger.

| Em T1 | Primário CPU → RAM | Primário CUDA → RAM |
|---|---:|---:|
| Ofertas / chaves distintas | 1 543 / 1 182 | 613 / 516 |
| Instalações / reinstalações incluídas | 1 530 / 348 | 613 / 97 |
| Retidas ao final / descartadas no sufixo | 263 / 1 267 | 90 / 523 |
| Bytes copiados a partir de vazio | 20 225 376 000 | 8 103 369 600 |
| Mínimo com estado inicial gratuito mais favorável | 16 814 822 400 B | 6 847 545 600 B |
| Taxa média necessária no sufixo, banco vazio | 1,080 GB/s | 0,433 GB/s |
| Maior densidade necessária numa chamada completa | 1,447 GB/s | 0,813 GB/s |
| Menor janela reserva → início do primeiro SET | 1,661905 ms | 1,847094 ms |
| Taxa exigida nessa janela para o triplo inteiro | 7,954 GB/s | 7,157 GB/s |

Todos os prazos de reescrita foram identificados pela geração do mesmo slot. A última linha aplica-se a um mecanismo que só pode iniciar a cópia ao identificar a vítima e tem de conservar os três slabs antes de começar a sobrescrever o primeiro. Adiar o SET, copiar componentes em momentos distintos ou reter o staging original alteraria esse prazo e a ocupação de memória. Os valores são requisitos inferidos do journal de controlo. O início anterior do primeiro turno não foi observado; qualquer aquisição de bytes realizada nessa parte tem custo desconhecido. O estado inicial gratuito serve de limite inferior.

O envelope provisionado do banco, incluindo quatro reservas e metadados, é **4 720 263 168 B**. A margem entre o pico do processo observado e o stop do E20 foi 5 217 624 064 B. Sobrariam 497 360 896 B se o resto do pico se mantivesse. Não se mediram páginas residentes, D2H, contenção, energia ou duração de manutenção do banco numa execução integrada. A política diferida só alteraria o veredito nominal de volume nestes preços se reduzisse mais 532 e 199 leituras, respetivamente, ou se outra premissa medida alterasse os orçamentos. Para distinguir o custo líquido das variantes é preciso confrontar atraso de publicação e cópia efetiva no T1 com os retornos dos dois pedidos, usando o mesmo trabalho e estados. [Diagnóstico e custos já conhecidos de T1](../t1_local/README.md)

## Reprodução

Protocolo em `3546d27d`, código em `9a9cdb6b`. Os dois processos reproduziram o recibo SHA-256 `6c444c8edf073416d539ca07e3ea19797f69e4b28ac881f0bafc76af6e749160`. R01/r02 usaram 0,79/0,78 s e 76 216/76 248 KiB de RSS. Zero forwards, GPU e leituras de pesos. A decisão M3 PARTIAL / M4 NOT_MET permanece.

```sh
cd research/qualification-retake/phase_fd/integrated/t1_bank_capture
python3 -IB test_score.py
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- python3 -IB score.py \
    --part "$PART40" --model "$GGUF_NVME" --inventory "$C7_INVENTORY" \
    --prepared-dir "$T1_SEAL" --local-dir "$T2_LOCAL" --new-output-dir "$NOVO"
```

Parte privada 48, manifesto SHA-256 bb27c74ea463764329311083c4f20183e6f186a8081d89243d94687e8c38346b. As duas reproduções ocupam 36 892 B.
