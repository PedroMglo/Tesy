# A largura 32 só disparou o pedido integral nas splits de uma camada

No scheduler CPU real do ik, desligar o lookahead integral com `GGML_MOE_PREFETCH_AHEAD=0` manteve o prefetch seletivo dos experts do top-4. A diferença dependeu da divisão do grafo: **as mesmas duas camadas**, executadas numa só split a 32 posições, pediram 495 616 B de páginas com ambas as configurações. Separá-las em duas splits CPU elevou o pedido para 13 373 440 B no modo por omissão. O controlo com AHEAD=0 manteve 495 616 B. Valores em páginas únicas consultadas por `mincore` em cada grafo completo. A syscall foi encaminhada ao kernel e a residência comunicada aos workers foi a real. [Recibo determinístico](result.json) · [Protocolo](protocol.md)

| Camadas / splits CPU observadas | Largura | OFF | ON, AHEAD por omissão (3) | ON, AHEAD=0 |
| --- | --- | ---: | ---: | ---: |
| 1 / 1 | 1, 5, 20 | 0 | 249 856 B | 249 856 B |
| 1 / 1 | 32 | 0 | 6 688 768 B | 249 856 B |
| 2 / 1 | 1, 5, 20, 32 | 0 | 495 616 B | 495 616 B |
| 2 / 2 | 1, 5, 20 | 0 | 495 616 B | 495 616 B |
| 2 / 2 | 32 | 0 | 13 373 440 B | 495 616 B |

Na última linha, os 12 chunks integrais somaram 13 418 496 B de páginas contadas com multiplicidade. O valor da tabela elimina as sobreposições. Nos ramos integrais observou-se por tensor a chamada integral do scheduler, seguida do hook do kernel e do pedido seletivo. Prevaleceu o ticket integral. Nos restantes ramos ON o hook do kernel pediu os intervalos dos quatro IDs. A leitura do GGUF, o TOP_K, os três MUL_MAT_ID por camada e a divisão do grafo usaram a biblioteca stock. A fronteira da segunda split foi imposta na fixture e confirmada pela API do scheduler. As duas famílias independentes repetiram os 13 grafos de cada modo, incluindo a troca de scores. Cada modo verificou 1 180 IDs ordenados e 151 040 valores F32 finitos. Os outputs completos dos modos ON coincidiram bit a bit com OFF, inclusive na troca de ranks que mudou as quatro linhas esperadas. Cada processo ON criou e encerrou quatro workers. [Cliente e observadores](graph.cpp) · [Revisor dos intervalos e dos outputs](screen.py)

A fixture GGUF contém seis matrizes MXFP4 sintéticas com 128 experts, dimensão de entrada/saída 128 e largura intermédia 256. O parser GGUF de stock recuperou nomes, tipos, geometria e offsets. A fixture forneceu o mmap e registou-o no backend. O próximo dado decisivo é saber qual alocador o **loader GPT-OSS** escolhe, como o scheduler divide o grafo desse modelo nas larguras do nominal e como o ramo CUDA paga os seus fills. Esta experiência não mede I/O do NVMe, operação CUDA ou latência de inferência. As dimensões e os tamanhos físicos do verdadeiro expert são distintos. [Condições do loader e da cache CUDA](../loader.md) · [Geometria original](../protocol.md)

## Reprodução sem modelo

R01 preservou os 13 resultados OFF e terminou antes do primeiro cálculo ON por falta de espaço virtual. O mesmo executável, SHA-256 `591c3e0281f603d26d66ab7d030dc66d746a7e62387d15da25fb09fb0ec3e0a9`, passou em R02/R03 com o cap residente original. As famílias duraram respetivamente 0,120 e 0,110 s no relógio do supervisor até à análise, com picos de 17 148 e 17 176 KiB nos três modos. Estes custos descrevem a fixture. [Falha preservada e guarda](r01.md) · [Dois testes de contraprova](test_screen.py)

No diretório desta unidade, usar `IK` para a checkout limpa do pin, `LIB` para o `libggml.so` CPU autenticado de R03, `W` para uma checkout Tesy que contenha o freeze de código, e `B`, `R2`, `R3` para três destinos novos.

```sh
REV=c0fe1d91
python3 -IB test_screen.py
REV=$(git -C "$W" rev-parse "$REV")
python3 -IB screen.py build --source "$IK" --lib "$LIB" --repo "$W" --revision "$REV" --new-output-dir "$B"
BSHA=$(sha256sum "$B/receipt.json" | cut -d' ' -f1)
for dest in "$R2" "$R3"; do
    python3 -IB screen.py run --source "$IK" --lib "$LIB" --repo "$W" --revision "$REV" \
        --build "$B" --build-sha256 "$BSHA" --new-output-dir "$dest" || break
done
cmp "$R2/receipt.json" "$R3/receipt.json"
```

As duas cópias desta medição deram SHA-256 `3373b370391025df9f8e0167b74fca70fcb67ded7e624b82ec0e01a7533a9bbb` para o recibo científico completo. A identificação do compilador, DSO, executável e fontes pertence ao recibo de build. Os custos e logs brutos de execução ficam separados do recibo científico. [Identidades e resumo](result.json)
