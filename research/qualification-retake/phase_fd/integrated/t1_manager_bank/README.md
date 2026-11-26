# Um expert expulso em T1 pode voltar ao primário em T2

**MEDIDO no portátil.** O manager C291 recuperou três dos quatro experts de T2 diretamente dos bytes que tinha guardado antes de sobrescrever os seus slots em T1. O controlo leu quatro vezes do pack. O candidato leu uma vez, poupando 39 665 664 B de retornos do descritor neste T2. Ambos publicaram as quatro gerações, executaram os mesmos 12 SET e terminaram com os mesmos 40 vínculos e os mesmos hashes de 120 componentes. **GO para qualificar a captura numa camada com consumidores reais.** R0 continua a ser o controlo de conversa, M3 PARTIAL e M4 NOT_MET. [Protocolo congelado](protocol.md) · [Resultado verificado](evidence/physical.json)

## O percurso dos bytes

O primário CPU tinha 40 slots, 128 experts lógicos e quatro workers. Os pedidos iniciais encheram o primário com 40 leituras e 120 SET. Em T1, quatro pedidos posteriores substituíram os donos dos slots 0–3. Antes de mudar cada vínculo, o candidato copiou as três matrizes MXFP4 gate/down/up ainda residentes para memória separada. Os quatro pares camada/expert vieram da reserva do próprio target. Guardou as três vítimas mais recentes, verificou os seus digests após a sobrescrita do primário e só admitiu T2 quando a fila, os claims e as gerações LOADING drenaram. Os quatro claims retidos fizeram falhar a tentativa de antecipar esse corte. [Fixture nativa](fixture.cpp)

Capturar quatro vítimas custou 52 876 800 B de payload durante T1. O banco reteve até 39 657 600 B. Em T2, esses três buffers imutáveis forneceram os ponteiros de origem dos SET para os slots novos. Ambos os positivos copiaram 52 876 800 B para o primário. A fonte de prova contém os hashes independentes do pack sintético e de cada uma das três componentes. Em cada processo, a releitura para autenticar o descritor no início e no fecho custou mais 159 105 024 B fora dos contadores de serviço. [Supervisor](run.py) · [Revisor independente](review.py)

| Braço | Preads T2 | FD pedidos / devolvidos em T2 (B) | SET T2 | Gerações publicadas em T2 | Parede do filho (s) | RSS máximo (KiB) |
|---|---:|---:|---:|---:|---:|---:|
| OFF | 4 | 52 887 552 / 52 887 552 | 12 | 4 | 0,517 | 594 320 |
| ON | 1 | 13 221 888 / 13 221 888 | 12 | 4 | 0,617 | 632 812 |
| EIO | 1 | 13 221 888 / 0 | 9 | 3 | 0,617 | 632 836 |
| Geração obsoleta | 1 | 13 221 888 / 13 221 888 | 12 | 3 | 0,617 | 633 140 |
| Shutdown | 1 | 13 221 888 / 13 221 888 | 12 | 0 | 0,567 | 632 852 |

No braço EIO, o miss do expert 36 no slot 5 ficou LOADING, geração 2 e claim limpo. Só os três hits válidos chegaram aos SET e à publicação. No braço de geração obsoleta, o expert 39 no slot 4 ficou LOADING na geração 3, com o novo claim ainda detido. O worker antigo chegou ao terceiro SET, mas a verificação da geração impediu a publicação. Os bytes deste slot ficaram em quarentena. No shutdown, as quatro gerações ficaram LOADING após os 12 SET e todas terminaram sem claim. A fixture não admitiu consumidores dos destinos incompletos. A barreira distingue quatro threads; o regresso do destrutor pinado confirma os joins. [Estados e contagens por braço](evidence/physical.json)

## Proveniência e recursos

Freeze em `6d5d756fecd6bb942e689276a0b7db6c3a6552c9`, árvore `963c3b7098b7d4a7bdfa7981c9abcf8fb3226926`. A fixture extraiu 34 blobs do C291 `c89c88b342054223e3f27a17fbfd0954803147ac` e aplicou os pontos de observação à cópia privada. Os três recibos estáticos R01, R02 e R03 passaram a verificação do pin e da aplicação desses pontos. R03 autentica a fonte da medição. Os três registam zero comandos e zero casos nativos. Não foi encontrada uma falha da família CPU no arquivo. O FAIL de admissão C118 da unidade de entrega aos dispositivos consta da parte 46. [Implementação dos pontos de observação](overlay.py) · [Entrega aos destinos nativos](../t1_native_sink/)

A compilação levou 4,175 s. Os cinco processos nativos somaram 2,936 s e os oito comandos em série somaram 7,385 s. Esses relógios incluem barreiras experimentais, hashing e verificação. O pico observado no scope de 1 GiB foi 744 939 520 B, com zero swap e zero eventos high/max/OOM. O pack sintético de seis registos ocupou 79 552 512 B no Btrfs do NVMe interno. O supervisor autenticou em cada processo os fornecedores de SET e SHA-256 e terminou a limpeza do pack. O gold permaneceu no arquivo. Zero modelos, forwards ou cálculo na GPU. [Recibo compacto](evidence/physical.json)

A parte 47 conserva 171 ficheiros e 6 698 847 B sob o manifesto `8457726e5c7688e3654dd11b1a0603f82413696565dc7bf2feecf8bde813dea7`. O recibo físico original tem SHA-256 `c64685ecb982b223d4a44e48faf6c8b71ce46e7fec1265fa4348692f8d84747c`. O revisor autenticou os dados locais e a cópia arquivada em duas execuções de 0,03 s. Ambas reproduziram o compacto byte a byte, SHA-256 `9aece0bd7fbdb928f95717bc980e1bc3d73579c17250ae5102c86ba39f4d4c3d`. Quatro testes de mutação cobrem a geração e o claim obsoletos, EIO, ordem das componentes e distinção entre bytes pedidos e devolvidos.

```sh
python3 -IB "$SOURCE/test_review.py"
python3 -IB "$SOURCE/review.py" --runs-root "$PART47" --manifest "$PART47/manifest.json" --new-output-dir "$NEW_REVIEW"
cmp "$NEW_REVIEW/receipt.json" "$SOURCE/evidence/physical.json"
```

Para a reprodução física, usar a checkout e os fornecedores congelados, escolher duas saídas novas e autorizar o scope da experiência. O pai dos dados do pack foi `/var/tmp` sobre Btrfs NVMe interno. O parâmetro UNIT contém o nome da unidade sem sufixo.

```sh
systemd-run --user --scope --unit="$UNIT" \
  -p MemoryMax=1G -p MemoryHigh=1G -p MemorySwapMax=0 -p RuntimeMaxSec=720 \
  python3 -IB "$SOURCE/run.py" --repo "$TESY" --backend "$C291" \
    --scope-unit "$UNIT.scope" --new-nvme-dir "$NEW_PACK" --new-output "$NEW_RAW"
```

O ensaio cobre três entradas de banco, uma camada com destino CPU e um único consumidor de teste. A captura síncrona dentro da reserva pode bloquear outros trabalhos do manager. Para um destino CUDA, a implementação precisa de demonstrar que a última utilização terminou antes de tirar a cópia e que esta terminou antes da sobrescrita. O tamanho de 353 entradas, a prioridade de expulsão de vítimas recuperáveis, a geometria 5+148 e o primeiro decode continuam a exigir os respetivos gates. A poupança do FD nas quatro procuras não mede a latência da conversa ou os bytes físicos de NAND.

O estudo de fonte seguinte especifica a guarda da última leitura na GPU e a fronteira entre tiles. [Consumidores CUDA e controlo de duas streams](cuda-consumers.md)
