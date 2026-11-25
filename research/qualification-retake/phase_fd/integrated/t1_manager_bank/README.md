# Preparação para revisão

O recibo estático R03 tem estado PASS_PIN_AND_PRIVATE_OVERLAY_ONLY, SHA-256 92493e28b5f3229cb413c1347a67ddbb2ac255b2f97349596dcbcd7f7a882fb4, em 0,09 s/23 900 KiB RSS. R02 permanece com o seu código anterior. O C++ foi formatado com clang-format 23.1.1 já instalado com a extensão C/C++; o dry-run de formatação passou. A verificação reproduz os 34 blobs pinados e exige exatamente uma ocorrência de cada ponto de instrumentação no C291 extraído. O supervisor e o overlay passaram o Ruff. A passagem estática não compila C++, não aloca as caches GGML e não inicia os quatro workers. O ciclo funcional fica NOT_RUN até ao ensaio separado.

O comando de preparação usou diretório novo e privado. A pasta do resultado físico e a do pack também têm de ser novas e distintas.

```sh
python3 -IB "$SOURCE/run.py" --source-only --repo "$TESY" --backend "$C291" --new-output "$STATIC"
```

Definir UNIT como o nome da nova unidade sem sufixo. O backend usado no precedente foi `/mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc/backends/c291-expert-store`, e o pai do pack foi `/var/tmp` no Btrfs interno.

Após congelar os ficheiros e qualificar a janela, o supervisor liga exclusivamente a GGML-base/crypto autenticadas, regista os stdout/stderr/digest/RSS de cada processo e encerra à primeira falha. A pasta do pack deve pertencer aos dados de projeto sobre Btrfs no NVMe interno. Uma execução com êxito remove os dois ficheiros sintéticos gerados depois de reconfirmar a identidade. Uma falha preserva o pack para diagnóstico.

```sh
systemd-run --user --scope --unit="$UNIT" \
  -p MemoryMax=1G -p MemoryHigh=1G -p MemorySwapMax=0 -p RuntimeMaxSec=720 \
  python3 -IB "$SOURCE/run.py" --repo "$TESY" --backend "$C291" \
    --scope-unit "$UNIT.scope" --new-nvme-dir "$NEW_PACK" --new-output "$NEW_RAW"
```

O ciclo usa captura síncrona em host dentro da reserva. Esse trabalho tem custo e pode bloquear os restantes workers. A ordem serial de publicação no banco corresponde à ordem observável de reserva, sem consultar T2. O código suporta um único manager e uma execução de teste por processo. Prova de segurança para um primário CUDA precisaria de ligar o término de consumo da geração antiga à cópia e a sobrescrita à conclusão dessa cópia. A validação do volume de 353 entradas, da política que dá prioridade a vítimas recuperáveis, da composição primária na fronteira 5+148 e do custo de T1→T2 são experiências próprias.
