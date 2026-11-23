# C199: época de utilidade H1/H2

Base publicada c97484433925cd0664ca27e1b5dcba76b1cb66f3. Nova autorização do owner: H1 slots40/44 ub32 E20; H2 GOMP_SPINCOUNT=0 slots40 ub32 E18, condicional. Sem publicação remota, serviço ou default.

Epoch `post-c198-useful-latency-portfolio-20260930T235456Z`: 4h wall, 7200s live, 2GiB raw. Reservas 2880s confirmação, 600s qualificação, 180s cleanup, 600s wall de fecho. Ledger append-only, nenhuma transferência do saldo C198.

SOURCE_AUDITED: servidor e libraries C75 originais preservados; hashes dos raw C140/C196 e capturas C127 revalidados sem inferência. Modelo com inode/stat originais; checksum prévio reutilizado, sem aquecer page cache por rehash integral.

REPRODUZIDO_MODEL_FREE: 47 testes dirigidos, incluindo Popen real/ownership do C2, ambiente selectivo e libgomp efectivamente mapeada. Não é a suite integral. O teste detectou o estado token_ids não inicializado numa falha anterior à tokenização; inicialização prospectiva conserva a falha no recibo. Hooks estreitos reutilizam o lifecycle existente, sem novo runner de servidor.

O primeiro freeze incompleto C200 e o freeze C202 anterior ao fim dos reparos permanecem NOT_RUN, sem scope/inventário/Popen/weights. C203 é a primeira família física H1. Não houve recuperação de tentativa física.

Os pedidos usam exactamente o transcript final publicado C196, finais48327, data2026-09-30 e IDs2043/2197/2292. As novas respostas não mudam os prompts seguintes. Isto é geração livre sobre história fornecida, não compute igual nem a conversa natural C196.

Holdout independente clientes/pedidos/reembolsos e seis fixtures Python estão congelados antes dos screens; não usam dados C164. A conversa JSON de qualificação também está definida antes dos outputs.

H2 SOURCE_AUDITED: CMake GGML_OPENMP=ON, libggml-cpu ligada a GNU libgomp instalada16.2.1. Fixture usa ggml_graph_compute_with_ctx, graph custom com oito callbacks e barreira real; máscara255 e resultado aritmético exacto em todos os casos. ABBA, delays0/50/500/5000µs,64 repetições, teto30s. A redução CPU nos casos500/5000 satisfaz o gate25%; isto justifica somente o bridge, não um speedup120B. Wall/wake overhead inclusive delay0 estão publicados.

A semântica de GOMP_SPINCOUNT=0 é suportada pela [documentação primária GCC](https://gcc.gnu.org/onlinedocs/libgomp/GOMP_005fSPINCOUNT.html); [OMP_WAIT_POLICY](https://gcc.gnu.org/onlinedocs/libgomp/OMP_005fWAIT_005fPOLICY.html) permanece unset no controlo. O comportamento instalado é observado pela fixture. KMP_BLOCKTIME pode ser definido internamente a200 pelo init GGML; /proc/environ observa o ambiente inicial exec e GNU libgomp não usa esse parâmetro Intel.

Next gates: H1 screen após admissão operacional própria; H2 bridge same-profile bitwise, depois screen se passar; seleccionar no máximo um finalista. Slots40/ub32 opt-in e M3 parcial continuam. M4 NOT_MET. C196 NO_GO, C197 NOT_RUN e C164 NO_GO preservados.
