# Estado das vítimas na conversa nominal C281

**R02 passou a aquisição.** Dois processos novos do GPT-OSS-120B repetiram os mesmos turnos, com as mesmas entradas, escolhas SSE, 78 e 47 IDs amostrados até EOG, e passaram os validadores de prefixo e conteúdo. Em ON, o próprio PID do servidor detinha o FD do ficheiro de observação antes do primeiro pedido e depois do segundo. Esse mesmo inode forneceu 48 800 B após o fecho. OFF produziu apenas o PFJ1. Ambos excederam 10 s até ao primeiro conteúdo final de T2 e ficaram abaixo de 6 tok/s. [Protocolo](protocol.md) · [Build e controlo independente](build-result.md)

| Braço e turno | IDs oficiais | Em cache + novos | Saídas | Prefill (s) | Decode (s) | Decode (tok/s) | Primeiro final (s) | Resposta completa validada (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OFF T1 | 2 043 | 0 + 2 043 | 78 | 61,618 | 20,013 | 3,897 | 81,205 | 81,641 |
| ON T1 | 2 043 | 0 + 2 043 | 78 | 62,190 | 19,905 | 3,919 | 81,676 | 82,106 |
| OFF T2 | 2 197 | 2 044 + 153 | 47 | 10,871 | 10,079 | 4,663 | 20,754 | 21,031 |
| ON T2 | 2 197 | 2 044 + 153 | 47 | 10,893 | 10,118 | 4,645 | 20,793 | 21,083 |

Os tempos de prefill e decode vêm do servidor. O cliente mediu os dois limites de parede em cada pedido. Os rácios ON/OFF em T2 foram 1,00206 no prefill, 1,00396 no decode, 1,00190 até primeiro final e 1,00246 até completar a resposta. Os quatro ficaram na banda descritiva de 0,85–1,15 neste par. Cada braço tem uma realização.

## O que se pode levar ao replay

O PFJ1 começou com o sétimo fragmento SSE de T1 em ambos os braços. Antes do POST de T2 o cliente selou 47 303 registos de 73 chamadas unitárias e a seleção de 353 vítimas. Houve 2 156 ofertas e 1 698 identidades distintas. As listas ordenadas selecionadas pelos prefixos independentes tiveram SHA-256 `ce1114203187fcee91c3884441ef73eb460445d7c278e69a95946a7dfb135cc7`. São chaves de vítimas recuperáveis num banco hipotético. Nesta aquisição, recolher essas chaves não copiou os bytes dos experts.

Em ON, a chamada 74 foi o único ENTER de cinco posições, 2 044–2 048, com zero elementos em fila, reclamados ou LOADING. O contador do manager marcava 5 049, com decaimento a cada 2 304. O ficheiro contém os contadores de uso, idades de 40 slots e frequência de 128 experts para cada uma das 36 camadas. O journal fornece as identidades e gerações do primário. Cruzar o ficheiro ON com o seu próprio PFJ e o seu próprio selo pré-T2. Os FD, a ordem de serviço e os relógios pertencem a cada processo.

O controlo histórico e ambos os braços reproduziram em T2 as chamadas 5 + 148 e 46 × 1, incluindo a máscara da última camada, 2 987 callbacks e 7 012 linhas de quatro ranks lógicos na ordem do target. SHA-256 das rotas `01374db11885d840eece0e115317fd72d6f5d3798692c705dad9887a33b017b0`, da geometria `3da30bff9bbfff72cfd3998e5f9618a2686ea79013736e7f443ccd0f05563323`. Os 78/47 tokens incluem o EOG; o marcador do próximo batch confirmou os primeiros 77/46. A conservação de reservas, gerações, transições, READ/SET/PUBLISH, FIFO e saída dos quatro workers passou por processo. Os bridges numéricos C270 pertencem ao R0 original e ao PFJ1 pai. A DSO desta aquisição qualifica as trajetórias e o estado observados. A exatidão dos logits para esta DSO e a mudança de política no runtime ficam por medir.

| Identidade | SHA-256 |
|---|---|
| Build da DSO privada | `4762116405b6f4bf3fee225be62b4485c01228dccc647febdfd36b8515b5d5bc` |
| libllama carregada por OFF e ON | `a9920fb2a683bd8912ef2a823fdec2aee305f2c09809693c065a76930b7b5d5b` |
| Pré-voo R02 | `a5af7157f37407efe2e47d2aa846b97ea367253ddb2eea2d5753aa11fe1ae608` |
| Família R02 | `cb70c934dbbe0f1ca7452904718589b44fa906179208e7f95b0c934808d70a42` |
| Braço OFF | `838f80b80341df3571e92257a2b45f24d81473696dc7892eeaafdd331f0bad11` |
| Braço ON | `8428c5ee301281ddeb1a7b1e2ed6883073e53578027139a67c2daef5b4eaaaf5` |
| PFJ1 OFF, 9 707 200 B | `4d95a15539f6d5a9889ef3d41b6ee0ead8f7b844ed8ca36219cdbbff731c3e1f` |
| PFJ1 ON, 9 707 776 B | `5b4d1cb6827d518a72d418f0625c8ea3a6c90a2ac57ef46b9360e9a45613f311` |
| Selo pré-T2 ON | `77babd4f9a35a8f6335f9b18c86ee4cc39977d0bb3b658d6763f42443a3933dd` |
| Seleção privada ON | `27c15095be9af23ccaa997556dc650aafac2f22002fafd6f933f1e1073400fab` |
| Estado TPOLICY1 ON | `7bce9841c3645247fbd850a8e89091610022cb38b5eb37922dd7f7167e596dad` |

## Recursos e encerramento

C55 mediu 61 amostras em 60,347 s, alimentação AC e perfil performance. A C118 própria de cada arranque produziu 61 amostras, em 60,151 s no OFF e 60,149 s no ON. Ambos executaram com memory.high/max de 20 GiB, paragem preventiva a 19,5 GiB e swap máximo zero. Os picos dos cgroups foram 15 990 554 624 e 15 940 538 368 B; os máximos observados da GPU foram 6 848 MiB em ambos. CPU/GPU/NVMe chegaram a 83,63/58,49/49,85 °C em OFF e 83,50/58,09/51,85 °C em ON. O monitor observou dois FDs diretos do GGUF e zero em modo buffered. Os dados raw de cada processo somaram 11 261 537 e 11 311 899 B, dentro do teto de 64 MiB.

READY ocorreu em 3,838 s e 3,857 s após o arranque. Entre o fim da resposta T2 e o marcador END do journal passaram 38,923 ms em OFF e 37,787 ms em ON, no CLOCK_MONOTONIC do portátil. END confirma as saídas dos workers e precede a selagem final. A duração isolada do destrutor, do fdatasync e do encerramento do processo fica desconhecida. O monitor devolveu código 0 após o pedido de paragem do proprietário. A consulta posterior confirmou as duas unidades inativas e a ausência de processos compute na GPU. As envolventes foram 169,894 s (OFF), 169,892 s (ON) e 380,202 s da família, incluindo 40,383 s entre braços para libertar a porta.

**NOT_RUN dentro destes braços:** serviço a partir do pack C290/C291, materialização de vítimas em RAM, aplicação da política BACKED e medição de economia física de leitura. A única diferença no ambiente funcional da observação foi a escrita de TPOLICY1. Ambos usaram o GGUF pela via R0 com PFJ1 e opções originais C281.

## Primeiro ensaio e reprodução

R01 ficou preservada como FAIL. O seu OFF concluiu dois turnos. Antes da C118 de ON o bind estrito do porto 18442 devolveu EADDRINUSE. Um diagnóstico independente reproduziu o erro com TIME_WAIT, sem listener e com a unidade inativa. R02 preservou o bind original, verificou a saída do PID e unidade anteriores e admitiu até 75 s apenas para TIME_WAIT entre processos. O registo contém 41 observações e o bind final bem-sucedido. O arquivo privado, parte 62, contém R01 e o diagnóstico; SHA-256 do manifesto `2b36d9be1c715686d1d2435905aab16cd491af79ebdc99415ee855120c55295f`. A parte 63 foi reservada à família R02. [Adenda prospetiva e hashes R01](interarm.md)

Comando de aquisição de R02, a partir da checkout limpa `fcbf8144addbebabddd90a4207d201d876e0c879`, árvore `c53a60e3db5b235d1b893be53d4366182fb5fc07`. Os caminhos abaixo identificam os destinos históricos exclusivos. Uma repetição física requer C55 válida, novas unidades e novos diretórios. O pré-voo foi executado com os mesmos parâmetros, sem `--execute`, para `/tmp/tesy-policy-natural-precheck-20261125-r02`.

```sh
W=/tmp/tesy-natural-policy-measure-20261125-r02
P=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural
python3 -IB "$W/$P/profile.py" \
  --repo "$W" --commit fcbf8144addbebabddd90a4207d201d876e0c879 \
  --window /tmp/tesy-c281-policy-c55-20261125-r01 \
  --window-sha256 ba63cba5f28201ad746801ea044b05c280cd1055523915f0da00c6ecd63a8019 \
  --preflight-dir /tmp/tesy-env49-static-r01 \
  --c270 /tmp/tesy-c270-driver-20261125-r01/receipt.json \
  --placement /tmp/tesy-nvme-placement-20261124-01/receipt.json \
  --historical /tmp/tesy-c281-driver-20261125-r01 \
  --build-dir /tmp/tesy-policy-natural-build-20261125-r01 \
  --parent-build-dir /tmp/tesy-phase-fd-integrated-build-20261125-r01 \
  --fixture-dir /tmp/tesy-phase-fd-native-20261125-r02 \
  --startup-dir /tmp/tesy-phase-fd-startup-20261125-r01 \
  --bridge-dir /tmp/tesy-phase-fd-c270-physical-20261125-r01 \
  --prior-on-dir /tmp/tesy-phase-fd-c281-on-20261125-r02 \
  --unit-prefix tesy-c281-nvme-policy-20261125-r02 \
  --new-output-dir /tmp/tesy-policy-natural-physical-20261125-r02 --execute
```
