# Admissão para o primeiro cálculo CPU do fork no portátil

A janela observada em 26 de novembro de 2026 admitiu **E10**. Ambos os cálculos
C55 deram um teto de 20 669 530 112 B (19,25 GiB), 768 MiB abaixo de E20. Entre
as 61 amostras, o mínimo canónico de MemAvailable foi 22 865 895 424 B e a
reserva externa 2 GiB. Máximos de 55 °C no CPU, 41,34 °C na GPU e 32,85 °C
no NVMe; zero PIDs de compute e PSI full avg10 máximo zero. A C55 terminou
às 00:00:54,886 UTC, sem abrir os pesos. O início de cada C118 deve preceder
00:55:54,886 UTC; uma execução posterior requer nova C55. O recibo original
E20 continua como NOT_ADMITTED sob `/var/tmp/tesy-ik-c110-admission-20261126-r01`,
SHA-256 `8dd4dbd14c5898f9768124d0cf238cc649cff9d59b3d308e737a5b85d47b70bd`.
A escolha do envelope foi publicada em `90c63ca6` antes da observação.
[Protocolo](protocol.md) · [Política canónica de recursos](../../../../../tools/host_resource_policy.py)

Cada braço E10 tem MemoryMax=10 GiB e MemoryHigh=9,5 GiB, MemorySwapMax=0,
escopo novo e C118 de 60 s. O [supervisor](profile.py) autentica CPU R03 e o
loader real, verifica VMAs das bibliotecas/ficheiro e a identidade dos FDs e
reconcilia as 216 vistas dos experts com o C283. D0 e D1 diferem no pool de
prefetch (zero/quatro workers, AHEAD=0). As fases explicitam carga e preparação
de contexto, as chamadas 16+1 e o escoamento. A folga de 512 MiB até MemoryMax
serve a reclaim de páginas. O RuntimeGuard de FILE_PAGING observa OOM, swap,
reserva, energia, PSI global e temperaturas. Guardam-se também pressão do
cgroup, faults, reclaim, anon, file, PSS/RSS, VmPeak/VmSize e bytes de leitura
por dispositivo. Como no arranque mapeado do stock, o delta de setores no
namespace NVMe tem um teto de 1 TiB por braço. Esse contador inclui os outros
utilizadores do namespace. A energia do CPU em joules fica por medir.

C110 tem contexto 8192, b256/ub32, 1 sequência, 8+8 threads, F16 K/V,
SWA completa, KV unificado, 12 camadas CUDA e 32 slots; o fork usa CPU, mmap
e deferred experts. O stock e95426f em E10 usou cache CUDA, SWA compacta, KV
separado e uma sonda de arranque. As formas e IDs da avaliação são comparáveis.
Os dois provedores históricos deram os mesmos top-5 das posições 15/16, com
diferenças nos bits. O recibo guarda as duas comparações separadamente.
[Canário C110](../../../../../results/c110-decode-triangle-20260929T0900Z/protocol.json)
· [Recebido stock](../../../stock_numeric/physical-r1/receipt.json)
· [Contrato do cliente](../driver/protocol.md)

No checkout congelado, o script seguinte prepara D0 e produz unicamente ficheiros
de entrada e recibo. O coordenador pode executar um braço de cada vez na
unidade delegada substituindo a invocação por `systemd-run` como abaixo.
O nome da unidade deve começar por `tesy-ik-e10-` ou `tesy-ik-e20-` conforme
a janela específica. O supervisor exige o SHA externo do D0 para admitir D1.
Resultados, stdout, stderr e as linhas F32 permanecem privados.

```bash
module=research/qualification-retake/ik_mapped_experts/cpu_numeric/admission
results=/mnt/sdisk-ssd-ext/Tesy/repo/c7-native-placement-screen-20260927-1117utc/results
stock=/mnt/sdisk-ssd-ext/Tesy/repo/build/stock-numeric-raw-20261125r1/raw/candidate.logits.f32
nvml=/tmp/tesy-env49-static-r01/monitor
common=(--envelope 10 --commit "$(git rev-parse HEAD)"
        --c55 /var/tmp/tesy-ik-c110-admission-20261126-r01/receipt.json
        --c55-sha256 8dd4dbd14c5898f9768124d0cf238cc649cff9d59b3d308e737a5b85d47b70bd
        --placement /tmp/tesy-nvme-placement-20261124-01/receipt.json
        --raw-parent "$results" --stock-raw "$stock"
        --objects /tmp/tesy-ik-ggml-build-20261125-r03/objects
        --build /tmp/tesy-ik-numeric-driver-build-20261126-r03
        --build-sha256 c8ff04f94d867ab8447598750ada85891fa767e9ebebe863e8b1833d50e7393f
        --synthetic /tmp/tesy-ik-numeric-driver-synthetic-20261126-r03/receipt.json
        --synthetic-sha256 caba065a2dfa9e8859f8000e804362387b2483de7ba266333be3d56f021b924b)
env LC_ALL=C LD_LIBRARY_PATH="$nvml" /usr/bin/python3 -IB "$module/profile.py" \
    "${common[@]}" --arm D0 --new-output-dir "$NEW_PREPARE"
# Cada chamada é uma admissão independente. 'extra' fica vazia para D0.
extra=()
# Para D1: extra=(--d0 "$D0/receipt.json" --d0-sha256 "$AUTHENTICATED_D0_SHA")
systemd-run --user --scope --quiet --unit="$UNIT" -p MemoryMax=10G \
    -p MemoryHigh=9728M -p MemorySwapMax=0 -p RuntimeMaxSec=500 \
    /usr/bin/env LC_ALL=C LD_LIBRARY_PATH="$nvml" /usr/bin/python3 -IB \
    "$module/profile.py" "${common[@]}" --arm "$ARM" --unit "$UNIT" --execute \
    "${extra[@]}" --new-output-dir "$NEW_ARM"
systemctl --user show "$UNIT.scope" -p ActiveState -p SubState -p Result
```

A preparação R01 detectou uma mudança de HEAD concorrente na checkout partilhada
antes de abrir as referências. A R02 no checkout destacado
`3c394e8fcd66b18038efe07abadde9e783d26719` reabriu C110/stock, as identidades
de 216 vistas previstas, os controlos sintéticos e toda a resolução ELF,
obtendo PREPARED_ONLY sem C118 nem abertura do modelo. Os
hashes externos por braço encontram-se no [compacto da preparação](preparation.json).
O freeze de execução inclui as duas máximas únicas obrigatórias (3659 e 3992)
e 10 segundos de cleanup. Uma falha conserva o código do filho, a marca
terminal disponível, as linhas F32 já publicadas e os logs privados.
