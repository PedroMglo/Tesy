# Fusão do dot inteiro no Ryzen do portátil

**NO_GO para promover este kernel de uma linha ao MUL_MAT_ID.** R0, a ablação reconstruída, o candidato VNNI e o fallback coincidiram bit a bit nos 23 040 valores finitos de gate/up e nos 160 controlos sintéticos. O oráculo inteiro independente passou nos 8 192 grupos de blocos do bring-up. Houve ganho em cada par mas nenhum estrato satisfez o mínimo de 10% nos dois pares contra os dois controlos. [Pré-registo](protocol.md) · [Bring-up](native-bringup.json) · [Recibo físico](evidence/r02.json)

| CPU e região | Redução contra R0, par 1 / par 2 | Redução contra ablação, par 1 / par 2 |
|---|---:|---:|
| 0 · 64 linhas | 11,89% / 7,64% | 8,47% / 7,74% |
| 0 · 23 040 linhas | 5,38% / 4,64% | 4,89% / 5,92% |
| 4 · 64 linhas | 8,13% / 7,51% | 7,46% / 7,57% |
| 4 · 23 040 linhas | 7,91% / 6,41% | 6,78% / 6,66% |

Valores MEDIDOS. Cada repetição percorre pesos já materializados. Em cada CPU e região a ordem é R,A,B,B,A,R. A L3 local é 16 MiB na CPU 0 e 8 MiB na CPU 4. A fusão reduz instruções de cálculo do dot. O ganho de uma linha e uma thread cobre apenas parte do FFN e o seu relógio exclui NVMe, quantização da ativação, scheduler e restantes dependências do pedido. [24 braços individuais em nanossegundos](evidence/arms.tsv)

A confirmação em árvore limpa 70ba0277017bee7dd155f000ed744d98c88b5d22 autenticou as oito matrizes originais no NVMe interno, 35 251 200 bytes lógicos, e a ativação C265 CPU0 em quatro ranks. O processo usou exclusivamente o backend CPU. Em 61,57 s de família houve 61 observações de pré-arranque, pico de cgroup de 155 029 504 B, swap zero, PSI full zero, CPU até 47,375 °C e NVMe até 32,85 °C. O contador do package marcou 13,13 J nos 0,720 s do filho do operador com supervisão, incluindo paridade e preparação. São dois pontos de telemetria na janela dos filhos. As duas cópias de modelo, os dados brutos e os binários permanecem no portátil. Não se executou um forward do modelo.

A primeira tentativa de construir o operador parou na leitura do prefixo VEX pelo verificador. As janelas C55 anteriores falharam ao localizar o material C281 no checkout e ao admitir o destino raw externo. A terceira janela foi admitida. A primeira família do operador parou por cadência C118 antes dos pesos e do primeiro braço. A segunda identidade usou o mesmo protocolo. [Falha preservada](evidence/preflight-fail.json)

Reproduzir num checkout limpo do commit acima. C7 aponta para o laboratório histórico pinado. POLICY é a política C55 derivada no portátil na hora anterior, PLACEMENT é o recibo privado autenticado da cópia NVMe. Cada destino é novo. A opção de harness usa a biblioteca padrão C++ e dl. Os hashes concretos do harness, dos seis ELFs e do build constam no recibo físico.

```sh
u=research/qualification-retake/mxfp4_vnni
python3 -B "$u/build_native.py" --backend "$C7/backends/c269-layer-last-use" --out "$NEW_BUILD"
g++ -O3 -std=c++17 "$u/clockbench.cpp" -ldl -o "$NEW_CLOCK"
systemd-run --user --scope -p MemoryAccounting=yes -p MemoryHigh=1G -p MemoryMax=1G -p MemorySwapMax=0 \
  python3 -B "$u/run.py" --lab "$C7" --placement "$PLACEMENT" --policy "$POLICY" \
  --build-dir "$NEW_BUILD" --build-sha256 "$(sha256sum "$NEW_BUILD/build.json" | cut -d' ' -f1)" \
  --clockbench "$NEW_CLOCK" --clockbench-sha256 "$(sha256sum "$NEW_CLOCK" | cut -d' ' -f1)" \
  --commit "$(git rev-parse HEAD)" --new-output-dir "$NEW_RUN"
```
