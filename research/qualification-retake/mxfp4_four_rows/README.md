# Quatro linhas por ativação no dot MXFP4

**NO_GO para integrar as duas variantes 4×1 no MUL_MAT_ID.** Partilhar o Q8 entre linhas reduziu o tempo contra a mesma intercalação com ponteiros independentes nos oito pares. O custo total com pesos percorridos em sequência subiu 74,55%–108,26% contra o R0 original. Ambos os candidatos falharam o gate de promoção nos dois tipos de núcleo. [Pré-registo](protocol.md) · [32 braços em nanossegundos](evidence/arms.tsv) · [Recibo físico e pares completos](evidence/r02.json)

| CPU e região | B vs R0 | B vs A | C vs R0 | C vs A | B vs C |
|---|---:|---:|---:|---:|---:|
| 0 · 64 linhas | +4,41 a +7,96% | +3,56 a +4,65% | −2,22 a +2,10% | −2,57 a −1,96% | +5,98 a +6,49% |
| 0 · 23 040 linhas | −108,26 a −98,03% | −108,63 a −93,08% | −149,45 a −136,01% | −149,90 a −130,11% | +16,09 a +16,51% |
| 4 · 64 linhas | +4,03 a +5,60% | +3,80 a +4,25% | +0,50 a +1,80% | −0,07 a +0,73% | +3,55 a +3,87% |
| 4 · 23 040 linhas | −80,54 a −74,55% | −80,83 a −74,52% | −103,22 a −97,41% | −103,18 a −97,73% | +8,55 a +14,11% |

Cada intervalo contém os dois pares MEDIDOS no portátil. Positivo significa redução de tempo. A encaminha as quatro linhas ao R0. C intercala quatro linhas com quatro ponteiros de ativação. B usa um único ponteiro. Em timing, todos apontam para a mesma ativação. Em B o assembly contém duas cargas vetoriais Q8 e dois índices de escala por par de blocos, contra oito de cada em C. Ambas as variantes usam oito FMA vetoriais sem spills no laço. O contraste B/C mostra o benefício local de partilhar o endereço. As duas comparações com R0 medem o custo completo. Sem contadores de cache ou stalls, a causa microarquitetural da perda em streaming permanece DESCONHECIDA. [Inspeção das instruções](native-bringup.json)

Os resultados de 23 040 linhas reais foram finitos e bit a bit idênticos ao DSO original e ao gold da família anterior. Os 3 840 casos com proteção de escrita incluíram 1 600 linhas com ativações comuns e 1 600 com ativações distintas. As 480 linhas de contraste distinguiram as ativações e os quatro casos de FMA de cauda coincidiram. O hash da ativação Q8 também coincidiu antes de iniciar os relógios. A variação dos braços, as duas repetições e a única ativação de layer 0 limitam o alcance do resultado.

A primeira tentativa de confirmação terminou antes do inventário e do cálculo, por divergência no nome do campo de SHA-256 entre builder e supervisor. Uma correção de uma linha lê o campo publicado. Na nova identidade mantivemos os binários, braços e critérios. O commit limpo da confirmação foi 4d38e1f4e299f256642a46a14d8a2263f3680a65. [Recibo da falha](evidence/preflight-fail.json)

A família física durou 61,80 s incluindo as 61 observações C118. O pico do cgroup foi 86 421 504 B, swap zero, CPU até 53,875 °C, NVMe até 32,85 °C e PSI full zero. Nas duas amostras do filho, a GPU ocupava 2 MiB, sem compute. O package registou 19,38 J nos 1,203 s do filho supervisionado. Reusámos os mesmos 35 251 200 B de pesos em ficheiro privado. A família não leu o GGUF nem executou um forward. A conversa e o histórico continuam qualificados pela receita R0 e pelos seus relógios próprios. [Referência física anterior](../mxfp4_vnni/README.md)

Reprodução no portátil a partir do commit congelado. REF aponta para o bundle privado r02 da primeira família. A montagem do scope, a política C55 e a raiz C7 usam a mesma convenção dessa unidade. Cada destino deve ser novo.

```sh
u=research/qualification-retake/mxfp4_four_rows
prlimit --as=1342177280 -- python3 -B "$u/build_four.py" --backend "$C7/backends/c269-layer-last-use" --out "$NEW_BUILD"
prlimit --as=1342177280 -- g++ -std=c++17 -O2 -Wall -Wextra -Werror "$u/clockbench4.cpp" -ldl -o "$NEW_CLOCK"
systemd-run --user --scope -p MemoryAccounting=yes -p MemoryHigh=1G -p MemoryMax=1G -p MemorySwapMax=0 \
  python3 -B "$u/run.py" --lab "$C7" --policy "$POLICY" \
  --reference-root "$REF" --reference-sha256 32ef813a048c3444b169606a6a3df1a66bcdd2f6269f473f877e37d73bbc5e24 \
  --build-dir "$NEW_BUILD" --build-sha256 "$(sha256sum "$NEW_BUILD/build.json" | cut -d' ' -f1)" \
  --clockbench "$NEW_CLOCK" --clockbench-sha256 "$(sha256sum "$NEW_CLOCK" | cut -d' ' -f1)" \
  --commit "$(git rev-parse HEAD)" --new-output-dir "$NEW_RUN"
```
