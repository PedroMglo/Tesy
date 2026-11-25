# Quanto custa converter as ativações de uma wave CPU estacionada?

**INCONCLUSIVE na tile CPU0.** O corte evitou a quantização nos casos elegíveis e as onze saídas físicas reproduziram o gold bit a bit. Dois pares ficaram cerca de 2,9 ms mais rápidos e dois ficaram cerca de 0,2 ms mais lentos. A mediana de 1,347 ms superou o mínimo de engenharia de 1 ms, mas o protocolo exigia ganho em todos os pares. A promoção para o runtime operacional continua por qualificar. [Pré-registo](protocol.md) · [Todos os braços e hashes](physical-r02/receipt.json)

| Par | Ordem | OFF (ms) | ON (ms) | OFF − ON (ms) | ON/OFF |
|---|---|---:|---:|---:|---:|
| 1 | OFF, ON | 46,399 | 43,484 | +2,915 | 0,93718 |
| 2 | ON, OFF | 46,498 | 46,700 | −0,202 | 1,00435 |
| 3 | ON, OFF | 48,095 | 45,199 | +2,896 | 0,93979 |
| 4 | OFF, ON | 47,515 | 47,719 | −0,203 | 1,00428 |

**MEDIDO.** Cada tempo vai do início do grafo do FFN à sua sincronização. O mesmo executável usou a mesma DSO candidata nos oito processos e o mesmo grafo DENSE de 110 nós, 24 MMID, oito waves e uma divisão CPU. O observador interno e cb_eval estavam desligados em ambos os modos. Os três primeiros processos qualificaram as mesmas 32 posições de C266 contra a referência integral de 92 160 F32, SHA-256 bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24. O original, a opção OFF e a opção ON demoraram respetivamente 50,431, 49,100 e 46,290 ms nestes controlos. Os quatro pares do quadro foram executados depois. [Dados de referência](../cpu0_suffix/README.md)

**REPRODUZIDO.** O relink com os objetos históricos devolveu a DSO C269 original byte a byte. Só se recompilou a unidade de tradução do kernel na DSO candidata. Na fixture GGML, cada um dos três modos produziu os mesmos 98 304 B em 192 casos. A área de trabalho Q8_0 ficou intacta em 0 casos no original, 0 no OFF e 24 no ON. As contraprovas incluem uma ativação comum a ranks ativos e estacionados, a última posição ativa, IDs transpostos, padding e um único token. O corte elimina conversões, preparação de listas e uma barreira interna, e distribui a escrita de +0 pelas threads. O tempo de grafo mede o efeito conjunto. [Kernel](kernel.py) · [Contraprovas nativas](test_kernel_graph.cpp)

**TRACE_DERIVED.** Na call 148 nominal C135, as cinco tiles tinham 166, 174, 165, 168 e 64 waves CPU inteiramente estacionadas. Em 73 dos 100 blocos CPU de largura 32 houve uma única wave ativa; nas 25 camadas da tile de largura 20 houve sempre entre duas e quatro. As 737 waves elegíveis correspondem a 2 211 chamadas de MMID, 394 260 480 valores F32 de entrada e 418 901 760 B de resultado Q8_0 da conversão. Estes volumes são lógicos. Uma transferência física ou um segundo do caminho crítico exigem observação própria. O mesmo corte tem alcance zero nas chamadas de um só token. [Verificador do trace original](exposure.py)

O efeito temporal numa conversa continua **DESCONHECIDO**. O serviço de experts faz parte do relógio do grafo e a fixture cobre apenas uma camada e densidade; as duas ordens contêm tanto um ganho como uma perda. A observação que separaria a variabilidade de serviço do custo do kernel seria o intervalo de compute em tiles com pesos previamente admitidos, emparelhado sob ambas as políticas e complementado pela duração do grafo com a mesma carga. Uma hipótese distinta procura um ganho maior ao omitir o SwiGLU e as suas duas entradas quando o down não as consome. O seu primeiro gate é observar as arestas no grafo efetivamente recebido pelo backend. [Gate da fusão](../parked_fusion/protocol.md)

## Proveniência, recursos e reprodução

Medição em 67be776eed9a478747d7204e76984b1c77e2c590, árvore a1b43233c44d988faca9d132269b4cc0781308a6. Build SHA-256 6da2f9ff2695e9b80b34ce4c8ceff0796ba7541ad219541b7f9ac82936f6a05c, 1,375 s e 128 704 KiB de RSS máximo dos filhos. A janela C55 R01 detetou o compilador cc1plus e recusou o arranque. O supervisor preservou o FAIL com zero braços. Uma nova janela de 60,997 s encontrou 26 340 388 864 B disponíveis no mínimo, alimentação AC e zero trabalhos concorrentes. O ensaio R02 em cgroup de 4 GiB terminou em 62,135 s incluindo 60,175 s de C118, com pico de 197 582 848 B, zero swap e zero filhos restantes. Os onze processos requereram 727 203 840 B de leituras alinhadas e produziram 4 055 040 B de saídas idênticas. A unidade abriu apenas o pack de experts já preparado. Utilização de GPU compute e forwards do modelo completo foram zero. [Falha R01](physical-r01/receipt.json) · [Recibo R02](physical-r02/receipt.json)

O arquivo privado qualification-20261124-nvme-01/part-25 contém as duas admissões, ambas as saídas físicas e o build, 81 ficheiros regulares e 9 037 516 B. SHA-256 do manifesto ff248aa3ed417373cf839dc3cf214bd476e8ac229552692bba49ea1c9ba0c15d. Na checkout de medição, os comandos abaixo reproduzem a contagem e o veredito com os originais locais e sem GPU. Cada compactação exige um destino novo.

```sh
study=research/qualification-retake/parked_mmid
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B "$study/exposure.py" --trace "$TESY_C135_TRACE"
python3 -IB "$study/compact.py" --raw-root "$TESY_PART25/tesy-parked-mmid-physical-20261125-r02" \
  --build-dir "$TESY_PART25/tesy-parked-mmid-build-20261125-r01" \
  --receipt-sha256 c3ad764ba9ce561baaeb5b6c6d800cbe52d176e5b0cf33eb220dd7dff0c5349d \
  --build-sha256 6da2f9ff2695e9b80b34ce4c8ceff0796ba7541ad219541b7f9ac82936f6a05c \
  --new-output-dir "$NOVO_COMPACTO"
```

A repetição física usa o pack autenticado da camada e o executável CPU0-suffix congelado, num checkout limpo da revisão de medição. Após o build, recolher uma janela C55 nova e confirmar o valor de `status` no JSON. A biblioteca NVML selecionada para o monitor tem o recibo privado `PASS_CPU_CAMPAIGN_MONITOR`. As bibliotecas GGML dos filhos são escolhidas e autenticadas pelo supervisor.

```bash
set -eu
repo=$(git rev-parse --show-toplevel)
study="$repo/research/qualification-retake/parked_mmid"
head=$(git rev-parse HEAD)
test "$head" = 67be776eed9a478747d7204e76984b1c77e2c590
digest() { sha256sum "$1" | cut -d' ' -f1; }
python3 -IB "$study/build.py" --repo "$repo" --backend "$C269" --suffix-build "$CPU0_SUFFIX_BUILD" \
    --new-output-dir "$NOVO_BUILD"
jq -e '.status == "PASS_C269_PARKED_MMID_BUILD"' "$NOVO_BUILD/receipt.json"
env LD_LIBRARY_PATH="$TESY_MONITOR_LIB" python3 -B "$study/../nvme_admission/window.py" \
    --nvme-model "$TESY_NVME_MODEL" --new-output-dir "$NOVA_C55"
jq -e '.status == "PASS_RESOURCE_WINDOW_ONLY" and (.reason | length) == 0' "$NOVA_C55/receipt.json"
env LD_LIBRARY_PATH="$TESY_MONITOR_LIB" python3 -IB "$study/profile.py" --checkout "$repo" \
    --expect-head "$head" --build-dir "$NOVO_BUILD" --build-sha256 "$(digest "$NOVO_BUILD/receipt.json")" \
    --input-dir "$CPU0_INPUT" --input-sha256 a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269 \
    --libs "$C269/build-c269-cuda/bin" --c55-receipt "$NOVA_C55/receipt.json" \
    --c55-sha256 "$(digest "$NOVA_C55/receipt.json")" --unit "$NOVA_UNIDADE" --new-output-dir "$NOVO_RAW"
```
