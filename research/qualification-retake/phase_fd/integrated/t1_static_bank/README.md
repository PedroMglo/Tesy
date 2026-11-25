# Um banco fixo de vítimas de T1 consegue servir T2?

**NO_GO com 239 entradas. INCONCLUSIVE com 353.** Num único segundo pedido nominal, o banco de 239 entradas com maior poupança de pread ainda exigiria 11 603 591 168 B até ao retorno de 148. Excede em 163 284 552 B até o orçamento mais favorável. Com 353 entradas, cada limiar pode ser atingido isoladamente. Nenhuma das três seleções que maximizam os indicadores individuais satisfaz os três em conjunto. A decisão vale para um banco protegido, sem admissões durante T2. [Pré-registo](protocol.md) · [Recibo completo](evidence/receipt.json)

A entrada reproduziu as 1 698 identidades observadas como vítimas READY e seladas antes do segundo pedido. Em T2, 1 263 gerações completaram a leitura das três componentes no prefill 5+148. Os preads devolveram 16 711 176 192 B no total, incluindo o alinhamento e as leituras repetidas. O retorno de 148 tinha fila e pendências vazias. Seguiram-se 1 091 cargas em 46 passos de decode; são necessários pelo menos 219 acertos para atingir 20%. O orçamento condicional de prefill é 10 690 306 614 B com 47/6 e 11 440 306 616 B com 46/6. [Origem e critérios da sessão](../t1_local/protocol.md)

| Entradas | Seleção maximizada | Pread poupado até 148 (B) | Pread residual (B) | Acertos no decode | Piso até primeiro final, 1× / 0,8× (s) |
|---:|---|---:|---:|---:|---:|
| 0 | Controlo | 0 | 16 711 176 192 | 0 | 12,277 / 11,023 |
| 239 | Volume | 5 107 585 024 | 11 603 591 168 | 97 | 11,667 / 10,536 |
| 239 | Acertos | 1 389 248 512 | 15 321 927 680 | 322 | 11,404 / 10,325 |
| 239 | Tempo | 1 309 978 624 | 15 401 197 568 | 220 | 10,052 / 9,243 |
| 353 | Volume | 6 616 281 088 | 10 094 895 104 | 140 | 11,424 / 10,341 |
| 353 | Acertos | 2 024 366 080 | 14 686 810 112 | 436 | 10,982 / 9,988 |
| 353 | Tempo | 2 831 577 088 | 13 879 599 104 | 279 | 9,396 / 8,718 |
| 1 698 | Universo | 10 465 984 512 | 6 245 191 680 | 674 | 8,995 / 8,398 |

O piso usa os preços locais de READ das 875 primeiras faltas em 441 grupos e mantém fixos 6,008451991 s fora das callbacks. Cada grupo paga pelo menos a maior cadeia de serviço residual e um quarto inteiro do worker-tempo residual. Outros serviços e cópias recebem custo temporal zero. A escala 0,8× multiplica esses preços. Os tempos são projeções sobre o relógio deste pedido. As execuções do crivo reproduzem a conta a partir da mesma captura.

O banco de 353 entradas ocupa 4 720 263 168 B com reservas e estruturas auxiliares, dentro dos 5 217 624 064 B medidos de folga. Só preparar as chaves do testemunho de volume em T1 custa pelo menos 3 780 691 200 B de cópias CPU e 885 686 400 B de GPU para RAM. As suas 640 entregas de T2 ainda servem 8 460 288 000 B de payload, dos quais 2 101 852 800 B se destinam à GPU. O universo completo precisaria de 22 503 788 544 B. O resultado de cada seleção, a distribuição por tier e os hashes estão no recibo.

A condição de reabertura com 353 entradas é encontrar um mesmo subconjunto elegível que cumpra os três critérios, ou apresentar um limite conjunto que exclua todos os subconjuntos. O primeiro caso admitiria a investigação da seleção causal e da cobrança das cópias na conversa. O transporte da ordenação entre sessões conserva o FAIL da campanha física. [Diagnóstico na própria captura](../t1_local/evidence/local.json)

## Reprodução

Protocolo em `cf9b7c05`, código em `cc125f17421c424431439a6d8346eba1088f40f1`. Os dois replays usaram os respetivos pares de selos e diagnósticos previamente reproduzidos, com o mesmo digest para cada entrada. O GGUF colocado no NVMe só é consultado por stat. As quatro fixtures sintéticas cobrem repetição e alinhamento, corte com carga em voo, componente duplicada, compatibilidade conjunta e enumeração exaustiva pequena.

```sh
cd research/qualification-retake/phase_fd/integrated/t1_static_bank
python3 -IB test_screen.py
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  timeout 120s prlimit --as=536870912 --cpu=120 --fsize=1048576 -- python3 -IB screen.py \
    --part "$PART40" --model "$GGUF_NVME" --inventory "$C7_INVENTORY" \
    --prepared-dir "$T1_SEAL" --local-dir "$T2_LOCAL" --new-output-dir "$NOVO"
```

R01 e R02 terminaram em 0,64 s cada, com 75 316 e 75 060 KiB de RSS máximo. Os dois recibos têm SHA-256 `fafd225a2bc8bfeefbb431a21e768aa32eb49f2faa94ee2afe5606677c4c0083`. Zero forwards, uso de GPU e leituras de pesos no crivo; M3 PARTIAL e M4 NOT_MET.
