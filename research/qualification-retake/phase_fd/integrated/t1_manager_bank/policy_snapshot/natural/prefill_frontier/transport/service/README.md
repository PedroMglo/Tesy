# Leituras de prefill com quatro workers e todas as reservas disponíveis

**MEDIDO.** O pack poupou 1,473 s (20,99%) na ordem RP e 1,747 s
(24,72%) na ordem PR sobre o serviço de leitura do GGUF no mesmo NVMe.
Com estas duas medições, o crivo de suficiência da combinação fecha em
**NO_GO aos preços estudados**. A banda útil do pack foi 2,522/2,628 GB/s.
Os limiares correspondentes das duas ordens são 7,054/7,171 GB/s para
preservar o custo serial e 5,041/5,101 GB/s ao conceder a sobreposição de
duas tiles. O ganho de transporte permanece medido e pode integrar outro
candidato que reduza também a carga exigida. Uma nova medição de fila cheia
precisaria de alterar uma premissa deste crivo.

| Processo | Fonte | Call 5 ms | Call 148 ms | Total s | GB/s úteis | União de READ s | READ worker·s | Parede com quatro READs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| RP | GGUF | 224,665 | 6 793,979 | 7,018643 | 1,993 | 7,018434 | 28,006512 | 99,36% |
| RP | Pack | 207,774 | 5 337,512 | 5,545286 | 2,522 | 5,543975 | 22,106238 | 99,20% |
| PR | Pack | 174,156 | 5 146,889 | 5,321045 | 2,628 | 5,320859 | 21,230590 | 99,27% |
| PR | GGUF | 233,975 | 6 834,097 | 7,068072 | 1,979 | 7,067982 | 28,211689 | 99,47% |

As taxas usam GB decimais. Nas duas chamadas, o GGUF pediu 449 880 064 e
13 548 785 664 B; o pack pediu 449 544 192 e 13 539 213 312 B. O bloco NVMe
contou exatamente os bytes pedidos em três braços e mais 294 912 B na janela
P do RP. O dispositivo agrega processos. A releitura com hash custou 7,050/4,975 s
para R/P no RP e 4,754/7,051 s para P/R no PR. Os quatro braços passam os
12 696 controlos de componente na releitura. O recibo inclui os tempos até à primeira e à última leitura de cada chamada.
[Recibo compacto por chamada, concorrência, integridade e recursos](receipt.json)

| Processo | C118 s | Processo s | Fase ativa s | Cleanup s | Pico do scope B | Máximos CPU/GPU/NVMe °C |
|---|---:|---:|---:|---:|---:|---|
| RP | 60,160 | 85,61 | 24,921 | 0,140 | 111 927 296 | 68,125 / 47,45 / 49,85 |
| PR | 60,170 | 85,10 | 24,542 | 0,155 | 110 870 528 | 63,875 / 45,41 / 49,85 |

Foram consumidos 111 949 692 928 B em preads na família, 170,71 s nos dois
processos e 3 280 799 B em ficheiros privados. O portátil usou AC/performance,
Btrfs no NVMe Micron MTFDKBK1T0QFM-1BD1AABGB e GPU só em monitorização.
Ambos os scopes terminaram com swap zero e foram recolhidos pelo systemd.
Energia total do portátil ficou por medir. A amostra é de dois processos no
mesmo portátil e num único pedido nominal.

**Admissão e arquivo.** A C55 R01 preserva `NOT_ADMITTED` por faltar 512 MiB
ao gate de R0. Nove worktrees congeladas foram transferidas do tmpfs,
preservando commits e caminhos. A C55 R02 admitiu 22 011 707 392 B de cap
na política. A parte 70 conserva a primeira C55 e a transferência. A parte 71
conserva segunda C55, dois processos e duas revisões, 22 ficheiros e
3 378 022 B. Manifesto SHA-256
`6e6b4ca1bd6f41477f8928c7cab6b72432cf3c47d923ede8be20e71231f05646`.

## População e relógios

O ensaio mede a entrega das três matrizes de expert selecionadas na parte 63 do
mesmo pedido T2 ON. A chamada de 5 tokens tem 34 leituras e a de 148 tem 1 024.
As 25 e 201 admissões de banco dessas chamadas já têm os bytes no host e ficam
fora do transporte de disco. A identidade da reserva inclui tile, layer, wave,
tier, posição na fila, expert, slot e geração. Cada braço entrega 13 985 913 600 B
úteis. A preparação verifica o índice do pack, os offsets GGUF e os hashes das
três componentes. [Plano privado e censo reproduzível](../prepare/README.md)

Quatro workers persistentes recebem a fila inteira no início de cada chamada.
Adquirem em FIFO e cada worker termina a sua leitura síncrona (P) ou sequência
de três leituras (R) antes de adquirir outro job. A chamada seguinte aguarda
o retorno da anterior. O relógio soma os dois intervalos entre o despacho
e a última conclusão. Cada worker usa o seu buffer pré-alocado. O monitor corre
em paralelo. A gravação do journal, preparação da lista de extents e verificação
dos hashes ficam fora desses intervalos. O contador de concorrência mede
chamadas `pread` da aplicação. As fatias simultâneas de worker-tempo pertencem
à mesma duração de parede. [Protocolo](protocol.md)

O pack e o GGUF estão no mesmo NVMe interno. Os FDs ficam abertos do início do
primeiro braço até à conclusão das duas releituras de integridade. Cada leitura
controla o offset, tamanho e retorno completo. A seguir, cada braço volta a
percorrer as duas filas, confrontando os 3 174 digests com o índice selado. O
digest aplica-se ao payload dessa releitura. Os dados de tempo provêm de uma
travessia prévia sobre os mesmos FDs, inodes, tamanhos e versões. Os buffers de
staging dessa travessia já foram reutilizados.

O alvo deste crivo é a combinação com o ganho de decode no mesmo pedido. A
agenda concede todas as rotas da chamada no primeiro despacho. Não mede a
descoberta causal dos experts, o SET dos pesos, a atenção, a FFN, o cliente
ou a duração do pedido. As frequências de filas e os tempos medidos caracterizam
esta agenda e estes quatro braços na máquina. [Revisão independente da combinação](../joint/)

## Reprodução

O método foi pré-registado em `f2ee6660` e o medidor em
`a174ae7a862152f2359116c26cf4454010551907`, árvore
`4b86237bbfa80a47508c42fdcfc382cd81ad79c0`. O plano tem SHA-256
`f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f`
e o recibo de preparação
`cdeae2ad6b637c11c1f9dc51ab34664ca756f468ab334f209cca64abd5f3739b`.
O teste portátil cobre FIFO, dois retornos, 3:1 preads, bytes, hashes incorretos
e leitura curta. [Verificador sintético](test_measure.py)

Para reproduzir a fixture sem pesos, usar `python3 -IB test_measure.py` neste
diretório. O ensaio físico usa os argumentos de `measure.py --help`, uma
checkout limpa e dois destinos privados novos. Para cada processo criar um
scope de utilizador com `MemoryHigh=384M`, `MemoryMax=384M` e
`MemorySwapMax=0`. Passar o commit, o nome do scope, o plano e os dois hashes
acima, o recibo C55 e respetivo digest, bem como os dois recibos de colocação
autenticados. Usar `--process 1` para RP. Em `--process 2`, juntar o recibo
anterior e o seu SHA-256. Cada processo executa o próprio C118, impõe o stop
de RAM a 336 MiB e o limite de 240 s. A família inteira autoriza
55 974 846 464 B de leituras cronometradas e igual volume para validar payload.
O ensaio usa zero forwards e zero operações CUDA.

Com as variáveis locais de paths e autoridade já preenchidas, a invocação do
primeiro par foi equivalente a

```sh
systemd-run --user --scope --quiet --collect --unit="$UNIT" \
  -p MemoryHigh=384M -p MemoryMax=384M -p MemorySwapMax=0 -- \
  env LD_LIBRARY_PATH="$NVML_LIB" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /usr/bin/python3 -IB "$SERVICE/measure.py" --process 1 --unit "$UNIT" \
  --commit a174ae7a862152f2359116c26cf4454010551907 --plan "$PLAN" \
  --plan-sha256 f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f \
  --plan-receipt-sha256 cdeae2ad6b637c11c1f9dc51ab34664ca756f468ab334f209cca64abd5f3739b \
  --c55 "$C55" --c55-sha256 "$C55_SHA" --placement "$R_PLACEMENT" \
  --pack-placement "$P_PLACEMENT" --new-output-dir "$OUT"
```
