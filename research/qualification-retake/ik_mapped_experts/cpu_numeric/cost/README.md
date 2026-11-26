# Custo observado do D0 ik no E10

**D0 R01 terminou com código 34 na primeira verificação de VMA.** A mensagem identifica `blk.0.ffn_gate_exps.weight`; o teste combina dispositivo, inode e permissões. O recibo conserva a causa como disjunção. A única marca nativa foi o início de carga. O processo chegou à verificação de tensores, mas faltou a marca final desta fase. Contexto, prefill, teacher e cleanup nativo ficaram sem duração. Nenhuma linha F32 foi publicada. [Resultado reaberto](d0-r01.json) · [Contrato](protocol.md)

| Observação | Valor |
|---|---:|
| C118 anterior | 61 amostras / 60,145622216 s |
| Criação até saída observada pelo supervisor | 0,509437694 s |
| Única amostra de execução após criação | 0,126917310 s |
| Intervalo dessa amostra até observação de saída | 0,382520384 s |
| Pico integral do scope por `memory.peak` | 148 705 280 B |
| `memory.current`, amostra / após saída do filho | 30 306 304 / 29 736 960 B |
| `anon`, amostra / após saída do filho | 25 292 800 / 24 936 448 B |
| `file`, amostra / após saída do filho | 36 864 / 57 344 B |
| `io.stat` do scope, dispositivo 259:0, delta de leitura | 0 B / 0 operações |
| `nvme0n1` global, delta de setores × 512 | 0 B |

O pico integral inclui o supervisor, C118 e a execução. Só há uma amostra de execução para caracterizar anon/file e RSS do processo. O máximo instantâneo dos componentes fica desconhecido. A memória após saída refere-se ao scope ainda ocupado pelo supervisor. Os contadores finais `pgscan`, `pgsteal`, refault de ficheiro, PSI acumulado some/full, swap e eventos OOM estavam a zero. Os deltas zero de I/O entre os endpoints são compatíveis com cache de páginas; não estimam o tempo para carregar um GGUF frio. A duração isolada de fim do filho e do scope e a energia em joules ficaram por observar.

## Reprodução offline

Sobre o diretório do braço físico (ou cópia integral), passando um destino novo:

```sh
python3 -IB review.py --arm-dir "$ARM_DIR" \
    --receipt-sha256 7e48b95fc8274c008fad02fd03ee9831892a162ba5c8498f1f0a725524152f29 \
    --new-output-dir "$NEW_REVIEW"
cmp d0-r01.json "$NEW_REVIEW/receipt.json"
python3 -IB test_review.py
```

O fecho reproduzido tem SHA `4f228e51e6bbb09305ab764a7b293aa84f1db76e1237bb604e502e6f499e6f60`. O revisor autentica o recibo externo, os membros públicos e privados declarados pelo supervisor, o C118, a autoridade dos IDs, do modelo e das duas bibliotecas. Os timestamps nativos medem apenas os pares de marcas inscritos. O monitor conserva tempos relativos à criação do processo e não guardou a origem absoluta para atribuir cada leitura a uma fase nativa. Os counters do namespace incluem toda a atividade do dispositivo; a ferramenta conserva em separado os deltas por dispositivo de `io.stat`. Um recibo `REPRODUCED_CLOSED_ARM_COSTS` preserva o veredito físico do braço, incluindo `FAIL_PRESERVED`.
