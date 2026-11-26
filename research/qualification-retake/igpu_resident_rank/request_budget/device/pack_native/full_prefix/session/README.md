# Dois pedidos naturais com seleção selada entre turnos

**PASS_C281_FULL_PREFIX_NATURAL_PAIR.** O servidor confirmou os mesmos 78 IDs em T1 e 47 em T2 com o observador desligado e ligado. Cada processo recebeu 2043 tokens no primeiro pedido e reutilizou 2044 tokens no segundo, para o qual processou mais 153. No braço ON, duas seleções de 353 experts ficaram seladas antes de o cliente transmitir T2. O ensaio disponibiliza a trajetória necessária para avaliar as seleções offline. O servidor executou a política de produção em ambos os braços. [Recibo compacto](receipt.json) · [Protocolo](protocol.md)

| Medição | OFF | ON |
|---|---:|---:|
| T1 até ao primeiro conteúdo final, no cliente | 78,287 s | 77,902 s |
| T2 prefill, no servidor | 10,070 s | 9,925 s |
| T2 decode de 47 tokens, no servidor | 9,230 s | 9,214 s |
| T2 velocidade de decode | 5,092 tok/s | 5,101 tok/s |
| T2 até ao primeiro conteúdo final, no cliente | 19,059 s | 19,529 s |
| T2 até ao fim da resposta, no cliente | 19,311 s | 19,794 s |
| Pico de memória do cgroup | 15 771 963 392 B | 16 321 855 488 B |

Os quatro rácios ON/OFF pré-registados de T2 ficaram entre 0,986 e 1,025, dentro do intervalo [0,85; 1,15]. Houve um único par na ordem OFF→ON. O resultado descreve esse par e deixa a neutralidade temporal por demonstrar. Os dois braços excederam 10 s até ao primeiro conteúdo final e ficaram abaixo de 6 tok/s no decode de T2. [Critérios](protocol.md) · [Recibo](receipt.json)

O journal de T1 contém 87 736 registos, 86 chamadas, 141 tiles, 74 278 grupos de quatro ranks e 5727 publicações para 5727 reservas. Nove chamadas de prefill consumiram 61 + 7 × 256 + 190 tokens, seguidas de 77 chamadas unitárias até à posição 2119. A drenagem desse último retorno fixou o corte. O cliente releu e selou a seleção em 645,215 ms de parede, entre pedidos. O processo cliente acumulou 646,004 ms de CPU durante essa operação. O seu máximo de RSS passou de 43 008 para 43 200 KiB. T2 acrescentou 50 647 registos. O journal completo, com cabeçalho, ocupou 13 284 832 B. [Admissão e captura](capture.py) · [Auditoria do journal](../audit.py)

O seletor recebeu 4548 ofertas de vítimas READY, correspondentes a 2829 chaves distintas. Partindo de bancos vazios, a LRU teria instalado 3238 conteúdos vindos de CPU e 1268 de CUDA. A regra baseada na frequência de prefill teria instalado 1126 e 423, respetivamente. Ambas terminaram com 353 chaves. Estes números contam instalações hipotéticas. O custo de copiar os conteúdos e o benefício na procura de T2 requerem avaliação própria. [Seletor](../../natural_trace/prefill_retention/policy.py)

A família demorou 394,885 s, incluindo as janelas C118 de 60,153 e 60,144 s. A C55 anterior durou 60,005 s. Ambos os processos terminaram com código zero e libertaram unidade e porta. O pico de swap foi zero, o de Tctl foi 83,5 °C e o do NVMe 52,85 °C em ambos. A GPU atingiu 58,32 °C em OFF e 57,32 °C em ON. A parte privada 106 reúne a janela, a preparação e a família. O manifesto SHA-256 é `d54f29ed903b5dbc772af42be9bd489dc15b2e9819de8cb8ac8b4dea7988a89d`. [Identidades da família e do arquivo](receipt.json)

Antes da execução, o revisor reabriu o braço OFF da parte 97 e confirmou as duas respostas e as trajetórias de 78 e 47 IDs. A admissão também validou a ponte numérica C292 para o ELF desta campanha, as bibliotecas efetivamente selecionadas, o manifesto e a C55. Os cinco testes locais cobrem as permissões do arquivo, o espaço para T2, a criação exclusiva e releitura do selo, a recusa de um corte inválido antes do POST e a identidade passada ao revisor. [Runner](family.py) · [Testes](test_session.py)

### Comando

O comando Bash abaixo regista os caminhos e identidades usados em R01. Uma reprodução física requer uma nova janela C55 e destinos exclusivos, incluindo uma nova identidade de unidade. O segundo processo recebe o SHA da preparação que o precedeu.

```bash
W=/mnt/sdisk-ssd-ext/Tesy/repo/build/tesy-natural-prefix-freeze-20261125-r01
COMMIT=712adbc0553593607d955eb7b995e80f22bc4c11
UNIT_PREFIX=tesy-c281-nvme-full-prefix-20261125-r01
BUILD=/tmp/tesy-full-prefix-dso-20261125-r01
BUILD_SHA=a125301f45a1a08c2774527d59c59ef09de5f4530fe9d6f8a80335288b2a5cad
FIXTURE=/tmp/tesy-full-prefix-fixture-20261125-r01
FIXTURE_SHA=f6296b6803fa168c0a854b79c363692dc05fb2bd736fea46dceab3dca3a59cc5
BRIDGE=/var/tmp/tesy-full-prefix-c292-physical-20261125-r01
BRIDGE_SHA=5f09f6228aa4b4bc1393331858bdccb04829c14e488827719374a33d35132d19
C55=/var/tmp/tesy-full-prefix-natural-c55-20261125-r01/receipt.json
C55_SHA=c53cadf44455e2e17dca8ad5c11876a27902cef2a2a23f3b68a8860836e65ef8
PREPARED=/var/tmp/tesy-full-prefix-natural-prepared-20261125-r01
PREPARED_SHA=450b7eb2bfa2d1e41e4b2289c11e72b3edfd6384046eba69fbcde884f924fdf1
FAMILY=/var/tmp/tesy-full-prefix-natural-physical-20261125-r01
D="$W/research/qualification-retake/igpu_resident_rank/request_budget/device/pack_native/full_prefix/session"
ARC=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01
args=(--repo "$W" --commit "$COMMIT" --unit-prefix "$UNIT_PREFIX"
  --preflight-dir /tmp/tesy-env49-static-r01
  --preflight-sha256 2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16
  --placement /tmp/tesy-nvme-placement-20261124-01/receipt.json
  --c270 /tmp/tesy-c270-driver-20261125-r01/receipt.json
  --c270-sha256 1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6
  --closure-dir /tmp/tesy-c281-pack-link-20261125-r01
  --derived-dir /home/pmglo/models/tesy-gpt-oss-120b-nvme/tesy-c291-manifest-20261125-r02
  --constructor-receipt /tmp/tesy-pack-manifest-constructor-20261125-r02/receipt.json
  --c292-receipt "$ARC/part-54/c292-nvme-numeric-pair-20261125-r01/receipt.json"
  --history-dir "$ARC/part-23/tesy-c281-driver-20261125-r01"
  --prior-family "$ARC/part-97/tesy-c281-pack-observer-natural-20261125-r01"
  --build-dir "$BUILD" --build-sha256 "$BUILD_SHA"
  --fixture-dir "$FIXTURE" --fixture-sha256 "$FIXTURE_SHA"
  --bridge-dir "$BRIDGE" --bridge-sha256 "$BRIDGE_SHA"
  --window "$C55" --window-sha256 "$C55_SHA")
python3 -IB "$D/test_session.py"
python3 -IB "$D/family.py" "${args[@]}" --new-output-dir "$PREPARED"
python3 -IB "$D/family.py" "${args[@]}" --prepared "$PREPARED/family.json" \
  --prepared-sha256 "$PREPARED_SHA" --execute --new-output-dir "$FAMILY"
```

O prefixo de unidade `tesy-c281-nvme-` é obrigatório. O journal escreve-se em `ON/observer/events.pfj`. Os dois selos `ON/before-t2-candidates.json` e `ON/before-t2.json` ficam fechados antes de T2. O relatório `ON/journal-audit.json` verifica a drenagem e a conservação do próprio processo. O recibo da família sela cada `arm.json`, que sela o `receipt.json` do respetivo cliente. Tempos de seleção, CPU do cliente e máximos de RSS do processo antes e depois da seleção constam do selo. Um máximo de RSS pode incluir trabalho anterior do mesmo processo.
