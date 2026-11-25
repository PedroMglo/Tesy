# CPU0 do 120B após duas permutas de páginas

**MEDIDO no portátil.** As três tiles consecutivas de CPU0, posições [32,64), [64,96) e [96,128), reproduziram bit a bit todos os 276 480 valores F32 da referência C266 nos braços COPY e ALIAS. A troca deliberada dos conteúdos de 45 e 49 na reposição final alterou 92 160 das 92 160 coordenadas da última tile. A contraprova manteve a mesma tabela, os mesmos ranks, o mesmo escalonador e valores finitos. [Protocolo](protocol.md) · [Recibo](evidence.json)

| Medida por processo | COPY | ALIAS | WRONG |
|---|---:|---:|---:|
| F32 diferentes nas tiles 32, 64 e 96 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 92 160 |
| Leituras concluídas no FD do pack parcial | 5 | 5 | 5 |
| Bytes devolvidos pelo FD | 66 109 440 | 66 109 440 | 66 109 440 |
| Bytes copiados para captura e reposição | 211 550 208 | 0 | 0 |
| Publicações do manager C291 | 13 | 13 | 13 |

As quatro entradas 45, 49, 57 e 60 mudaram dos slots 0, 4, 3, 1 para 4, 3, 1, 0 e regressaram a 0, 4, 3, 1. As suas gerações avançaram de 1 para 2 e 3, enquanto o expert 98 permaneceu em 2/geração 1. Os cinco carregamentos e as oito reposições contam como trabalho do manager. A medição de bytes identifica as cinco leituras efetivas. Em cada tile verificaram-se as 24 MUL_MAT_ID, o backend CPU e o uso dos mesmos tensores, buffers, endereços e strides CPU_Mapped. O router de 153 posições conferiu 612 IDs ordenados e os pesos de routing.

O lease nasce quando o scheduler comunica a primeira wave ativa. Em cada corte, o host espera pelo fim do grafo, sincroniza, reserva os quatro destinos, comprova quatro claims bloqueados sob o mutex e só depois devolve os leases. Esta ordem conservadora prova a correção do handoff no ensaio. A fronteira mínima de sincronização no runtime multibackend exige observação própria. A falha por sobreposição antecipada e as conclusões obsoletas foram exercitadas separadamente. [Teste de ciclo de vida](../README.md)

**Contabilidade de memória.** A diferença de 211 550 208 B conta o comprimento das chamadas memcpy explícitas de captura e reposição. Cada transição do controlo cria quatro capturas e quatro backing stores de destino de 13 221 888 B cada. Enquanto todos os workers aguardam a libertação, estes oito registos coexistem com os cinco originais. Em ALIAS os cinco backings originais suportam as duas localizações lógicas. A diferença de 105 775 104 B de conteúdo materializado nessa barreira resulta das alocações e das cópias completas. Os metadados e os picos de todo o processo têm contabilidade diferente. O pico do cgroup da família foi 299 175 936 B, com zero swap. A proteção térmica e de memória e as três janelas C118 passaram. A família durou 182,590 s, incluindo as três janelas de inventário de pelo menos 60 s.

**Alcance.** O grafo 2880² usa os pesos MXFP4 originais e os cinco registos autenticados no NVMe. Os destinos da permuta foram prescritos para testar identidade e mudança de geração com trabalho idêntico. O teste cobre o FFN da CPU0 e não produz um token. O primeiro decode do C270 usa os IDs 28, 24, 8 e 16; os quatro pesos e biases, o gold específico e uma identidade separada são os pré-requisitos da sua prova. O estado da conversa permanece M3 PARTIAL, M4 NOT_MET.

## Reproduzir

Na checkout limpa `ba591bf289dad2300ab8bf780b08f14733e7bb2d`, usar o estudo abaixo de `natural/cpu_alias/manager/real_layer`, o backend C291 e os providers verificados. O protocolo foi congelado em `99593a42`. Os dois destinos são exclusivos. O SHA-256 do recibo de build foi `ff498df964ecd7062029bd813abac4b3af3a01dbe2ff6184a4498ec5a8545027` e o do recibo físico foi `d2caf754ec2d3d085dc6bcfa4ea6c7e18cfb20ef8d679a65d07068e2cd2114dc`.

```sh
python3 -IB "$STUDY/build.py" --backend "$C7/backends/c291-expert-store" \
  --libs "$C269_LIBS" --new-output-dir "$NEW_BUILD"

systemd-run --user --scope --quiet --unit="$UNIT" -p MemoryMax=4G -p MemoryHigh=4G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=890 env LD_LIBRARY_PATH="$MONITOR_NVML" \
  python3 -IB "$STUDY/profile.py" --commit "$HEAD" --unit "$UNIT" \
  --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_RECEIPT_SHA" \
  --input-dir "$C266_PREPARED" --libs "$C269_LIBS" --c55-receipt "$C55/receipt.json" \
  --c55-sha256 "$C55_RECEIPT_SHA" --new-output-dir "$NEW_RUN"
```
