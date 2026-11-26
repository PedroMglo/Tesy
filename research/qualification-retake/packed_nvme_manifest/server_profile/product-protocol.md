# O pack sozinho como controlo da conversa combinada

**Decisão de investimento.** Adiar a conversa isolada. O pack integral no NVMe diminuiu o serviço com LRU em 31,94% e 32,56% nos quatro grupos físicos. Os quatro foram selecionados por divergência de políticas e já tinham banco de vítimas. A C292 contemporânea demonstrou fidelidade selecionada com a DSO C291 no mesmo NVMe. Os tempos dos filhos incluíram captura de tensores e verificação dos bytes. A C293, com trabalho fornecido, obteve 7,47% e 6,05% de redução mediana total em nominal/código, abaixo dos 8%, e 8,45% e 5,16% no decode, abaixo dos 15%. Esse NO_GO mantém o workload e o limiar originais. M3 continua PARTIAL e M4 NOT_MET. [Serviço observado](../../phase_fd/integrated/t1_full_pack_service/README.md) · [C292](../capture_numeric/README.md) · [Critério C293](../../../C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md)

## Crivo sem modelo

Na captura natural C281 instrumentada, as calls 5+148 admitiram 51+1 212 gerações. Mantendo essas admissões e sem retries, o transporte passa de três preads de componentes para um por expert: 3 789 → 1 263. O GGUF devolveu 16 711 176 192 B. O pack pediria 16 699 244 544 B, menos 0,0714% em relação a esse volume. Cada pread do pack pede os três pesos de 4 406 400 B arredondados ao alinhamento de 4 096 B do construtor. São volumes no descritor. O tráfego NAND do pack, a contenção e a sobreposição das leituras com outros trabalhos ficam por medir no mesmo pedido. [Captura e hipóteses do relógio](../../phase_fd/integrated/README.md) · [Worker e arredondamento](../../../../patches/c291-integral-expert-store.patch) · [Construtor nativo](../README.md)

Fixando o decode **exatamente em 6 tok/s**, mantendo o resto desse T2 e dando todo o crédito possível antes do primeiro final, o prefill dispõe de até 2,430748179 s com 47 tokens e 2,597414846 s na relaxação de 46 avaliações. O pack exigiria respetivamente 6,870 e 6,429 GB/s úteis mesmo com todo esse orçamento disponível para E/S. A 4,5 GB/s a duração mínima imputada ao volume seria 3,710943232 s; faltariam 1,280 ou 1,114 s. O crivo fecha esse cenário. Um decode mais rápido alarga o orçamento, e a taxa de serviço e o paralelismo podem mudar. Para antecipar uma conversa do pack sozinho seria preciso medir essa margem nas admissões reais de R0 ou demonstrar que outra premissa do crivo mudou. O pack tem valor como controlo da combinação mesmo sem atingir M4 sozinho. [Denominadores e limites reproduzidos](../../phase_fd/integrated/nominal-r01/limits.json)

Reprodução a partir da raiz da checkout, passando o recibo do construtor R02 da parte privada 52. O comando lê dois JSON e verifica a fonte pinada.

```sh
python3 -IB - "$CONSTRUCTOR_R02/receipt.json" <<'PY'
import hashlib, json, sys
from pathlib import Path

def checked(path, expected):
    data = Path(path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected
    return data

checked("patches/c291-integral-expert-store.patch",
        "17d577e763e6d7dbc461bcb1d795149e1e378500750f994ef1c3f626d86a7083")
x = json.loads(checked("research/qualification-retake/phase_fd/integrated/nominal-r01/limits.json",
                       "47476b0d8f0435c5e4c04f56a73edbb85f81e22ef9f9ba80a92c3b19b67d5b74"))
ctor = json.loads(checked(sys.argv[1], "c81c15cb9614fd2780f35d5f3fc2b96ce280056f9da363ca74b42b112d1642f1"))
a = ctor["proof"]["offset_align"]
n = sum(call["origin_loads"] for call in x["calls"])
gguf = sum(call["origin_returned_bytes"] for call in x["calls"])
pack = n * ((3 * 4406400 + a - 1) // a * a)
print("preads GGUF/pack, B devolvidos/pedidos", 3*n, n, gguf, pack)
for name, case in x["scenarios"].items():
    ns = case["remove_all_remap"]["budget_ns"]
    print(name, "GB/s requeridos", round(pack/ns, 6), "défice a 4,5 GB/s (s)", round(pack/4.5e9-ns/1e9, 6))
PY
```

## Comparação reservada à próxima família de produto

**Software e controlo.** O executável C276/C281, common, server-impl e mtmd ficam fixos. R usa a libllama C269 independente. O usa C291 sem manifesto. P usa a mesma C291 e recebe o manifesto derivado do pack. O e P mantêm o primário R0 e a política original, sem banco. R/O mede o efeito de trocar de DSO e O/P o de trocar o transporte. Os ELFs existentes passaram a resolução estática do servidor, dos quatro consumidores e dos 24 fornecedores, recibo SHA-256 `9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116`. Antes de executar, adaptar o supervisor privado para validar a DSO e o FD do PID nos três modos. O perfil C281 original exige C269. A combinação exigirá DSO, ablação e gate numérico próprios. [Resolução do servidor](protocol.md) · [Supervisor C281](../../nvme_conversation/postupdate/profile.py) · [Prova de FD reutilizável](../capture_numeric/live.py)

**Primeiro bloco, só após admissão da combinação.** Ordem R, O, P, cada um com um servidor limpo e os dois pedidos sequenciais: no máximo três spawns e seis POSTs de geração. Validar READY, dono do listener, inputs oficiais e SSE até ao stop. T1 recebe 2 043 IDs. T2 usa a resposta efetiva de T1, com 2 197 IDs oficiais, 2 044 em cache e 153 novos. Conservar data 2026-10-05, seed 42, temperatura zero, cap 256, contexto 8 192, P12/ub32, 40 slots persistentes e quatro workers. Usar verbosidade 5 nos três braços para verificar offline os 78/47 IDs incluindo EOG e os canais. Preservar a resposta e terminar a família se divergirem trajetória, trabalho ou validador. Um bloco fornece contrastes descritivos. Qualificar desempenho requer ordem espelhada e repetição pré-registadas, proteção do caso de código e os restantes critérios M3/M4. [Cliente, hashes e validadores](../../nvme_conversation/protocol.md) · [Verificação dos IDs efetivos](../../history_lookup/native_ids/README.md)

**Medição e encerramento.** Recolher em ambos os turnos prefill e decode do servidor, tok/s, relógios do cliente até primeiro fragmento, primeiro conteúdo final, conclusão do transporte e resposta válida. Apurar arranque, intervalo entre turnos, INT, espera pela saída normal do servidor e libertação de porta/scope. Fechar o stream de cada turno, mantendo a agenda de sincronização do servidor. O destrutor C291 reúne os workers antes de libertar buffers e FDs. O endpoint não expõe a hora de cada publicação ou join. No nominal aplicar ≤10 s e ≥6 tok/s nas métricas respetivas. [Relógios da referência R](../../nvme_conversation/postupdate/physical-result.md)

Usar C55 vigente, C118 de 60 s fresca (≤3 s), E20 high/max 20 GiB, stop 19,5 GiB, swap zero, telemetria e guarda de pressão. Por braço: READY ≤30 s, pedidos ≤180/90 s, monitor ≤480 s, scope ≤650 s, raw ≤64 MiB e folga inicial ≥11 GiB. Nos três, ≤1 950 s e ≤192 MiB. Fixar estado térmico de admissão, alimentação, cache/prefixo e política de processo. Conservar caches naturais do SO e a ordem dos braços. Autenticar VMAs, executável, start_ticks, listener e loader encerrado. Verificar dev/inode, flags e acesso dos FDs no READY e após T2. Pack O_RDONLY|O_DIRECT só em P e GGUF em todos. O FD aberto prova a seleção; o contador interno do manager acumula payload após publicação e o endpoint não reporta preads por turno. Recolher pico do cgroup, VRAM, swap, térmicas CPU/GPU/NVMe e potência GPU. Estimar joules GPU por integração com timestamps e cobertura do intervalo. Publicar energia do host se existir contador acessível com domínio, unidade e cobertura conhecidos; caso contrário, DESCONHECIDO. Falha de origem, sensores obrigatórios, recursos, exatidão, processo ou limpeza encerra a sequência e conserva os raws. [Controlos e limites C281](../../nvme_conversation/protocol.md) · [Pack, GGUF e captura física](../capture_numeric/README.md)
