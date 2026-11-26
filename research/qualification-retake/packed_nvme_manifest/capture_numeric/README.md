# Paridade selecionada C292 com o pack integral no NVMe

**MEDIDO — PASS_SELECTED_C292_NVME_PAIR.** Dois processos 120B independentes passaram no portátil, primeiro OFF e depois ON. Ambos reproduziram o C127 histórico e o C270 de controlo, e a comparação direta OFF/ON passou. Para além dos 1 500 payloads de seis fronteiras, 250 estados, duas entradas mascaradas e cinco vetores F32 integrais finitos de 201 088 logits, a árvore completa de cada braço teve os mesmos 3 266 ficheiros e 88 704 231 B por nome, tamanho e SHA-256. Os 996 checks de componentes cobriram seis componentes de 166 combinações de consumo, com 3 255 tensores e 896 posições sentinela no âmbito observado pelo ELF. O FD do pack esteve aberto com O_DIRECT nas amostras de ON. O par qualifica a fidelidade selecionada da leitura contígua do pack no NVMe. **M3 PARTIAL, M4 NOT_MET.** [Recibo reproduzido](evidence/physical.json)

| Medida física | OFF, GGUF | ON, pack |
|---|---:|---:|
| Processos de modelo / capturas válidas | 1 / 1 | 1 / 1 |
| Amostras com FD do pack / amostras do PID | 0 / 137 | 114 / 118 |
| Máximo de FD diretos / buffered do GGUF | 2 / 1 | 2 / 1 |
| C118, amostras / duração / idade ao spawn | 61 / 60,142 s / 50 ms | 61 / 60,146 s / 47 ms |
| Duração do filho / scope com inventário e cleanup | 36,021 / 96,914 s | 31,111 / 91,782 s |
| Pico do cgroup / VRAM máxima | 17 565 175 808 B / 6 878 MiB | 17 294 311 424 B / 6 880 MiB |
| Temperatura máxima CPU / GPU / NVMe | 70,63 / 51,49 / 45,85 °C | 72,38 / 51,55 / 47,85 °C |
| Bytes privados em raw, incluindo telemetria | 89 043 928 | 89 028 705 |

Cada PID carregou os 18 fornecedores de arranque, incluindo a mesma libllama C291, e inicializou 21 objetos no total. O driver, PTX JIT, NVVM e gpucomp pertenciam ao deployment 620.70.06. O GGUF permaneceu aberto para o caminho do modelo e a verificação dos bytes de referência. Ambos os processos saíram com código zero, encerraram o scope E20 e registaram zero swap e eventos OOM. A campanha durou 219,021 s. Os tempos incluem captura e verificações, com uma observação por braço. A leitura dos contadores de serviço, os tempos de chat e a utilidade exigem os respetivos workloads. [Recibo e custos por braço](evidence/physical.json)

A checkout física tinha HEAD `ee110ba4899f972cc4426c87cebd93105754e7b1`. O recibo da família tem SHA-256 `f7a5f270e427b8b9390b17ae1a49b2d154a57a822b9afc0ab1c1039f0641b9c7`; OFF `ac20bb9b1f470447983075dd19c738f8d9a5f77353cbbb0779c5c58ee46e2f18`; ON `8ae219bbaac973cacc531b8e1e7f33ed4998476675f405cdbfe42f1029aadd56`. O revisor leu apenas os ficheiros fechados, autenticou os logs do loader e da telemetria e reavaliou os três contrastes em 16,90 s e 214 536 KiB RSS. O compacto público tem 22 182 B e SHA-256 `34c8644f04d0a92330770dd18dc1655fde7fadbd52f545cd1c7c2e57f603de86`. O arquivo privado 54 preserva a família, a preparação e as duas tentativas do grader histórico em 6 597 ficheiros e 178 411 487 B, manifesto SHA-256 `1a6044954fe2c0db86a2c442151665fff3281b22dcd473eba3971585d92f75ec`.

A segunda revisão usou apenas as cópias arquivadas da família e da preparação (parte 54), da closure C292 (53), do mapa estático C270 (22) e do braço numérico C270 (23). Concluiu em 17,65 s e 214 348 KiB RSS e produziu o mesmo compacto byte a byte.

## Configuração

O teste compara a leitura direta das três matrizes no GGUF (OFF) com a leitura dos mesmos bytes contíguos no pack C290 (ON). Usa o mesmo executável C292, a mesma libllama C291 e o mesmo corpus C127 de 189 posições de prefill e 32 passos de decode fornecidos. Os 43 IDs de continuação presentes no ficheiro são a oferta do corpus. O cliente consome os primeiros 32. A referência independente C270 foi executada com a libllama C269 no deployment atualmente qualificado. [Protocolo](protocol.md) · [Caminho de produto](../../phase_fd/integrated/t1_full_pack_service/product-path.md)

## Reanálise histórica e preparação

O primeiro revisor confundiu duas populações no contador de parking da C292. O ELF incrementa `sentinel_count` apenas depois da condição `byte_check`, nas fases prefill0 e decode0 e nas camadas 0, 25, 29 e 35 que produzem dados. A leitura de todas as vistas preservadas contou 62 200 sentinelas no OFF histórico. A população que o código nativo contabiliza tem 896. O FAIL do revisor R01 ficou preservado com SHA-256 `3ec2671c5530b3b550661919e96679b59421ddbfd478587fcf22ca4b69b35c3d`, 11,84 s e 221 068 KiB RSS. [Predicado e contador na fonte C127](../../../../tools/c127_slots40_boundary_capture.cpp) · [Contraprova do âmbito](test_grade.py)

Na revisão R02 executaram-se os dois gates C127 originais e três comparações C292 entre as capturas **históricas** OFF/ON e o C270. As três árvores tinham 3 266 ficheiros e 88 704 231 B, SHA-256 nome/tamanho/conteúdo `3b1c13734120f430d779960e3e8123eb58ffeee1947a1844636743b1e3aa1f03`, incluindo a árvore independente C127. O recibo R02 tem SHA-256 `1c28b27b2d698411cc04b7a01ac96bbaf3fd13cb2b971c7ee5cf07836663fb91`; a reanálise usou 28,73 s e 221 088 KiB RSS, zero GPU e zero forwards. A paridade dos cinco vetores integrais compara os padrões F32 depois da verificação de finitude. [Grader](grade.py) · [Comparador histórico de bytes](../../../../tools/expert_store_numeric_gate.py)

O pré-voo dos dois novos braços terminou `PREPARED_ONLY` em 1,653 s, zero processos de modelo, recibo `dc568982a389b69fd2bfbc453f5aabb6c3876912b98e16a56a001df2f798b3c2`. Ele liga os argumentos, corpus, ambientes, perfis e cadeia de metadados R02 à closure estática `7b0ca3bcc778f527dfc4cdfab3aaa3f93687045cba5e12d5a74b8310aeb7b670`. [Supervisor](profile.py) · [Prova dos fornecedores](../capture_profile/README.md)

## Reprodução offline

O comando exige o recibo **terminal** da família e o respetivo SHA externo. Lê os dois journals pós-execução, o bruto dos braços admitidos e o controlo C270. Valida o número de processos, as provas de exatidão, recursos, argumentos e biblioteca selecionada, utilizando as associações originais do loader preservadas no arquivo. Os pesos e a GPU ficam fora desta reanálise.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -IB "$UNIT_DIR/report.py" \
  --family "$FAMILY" --family-sha256 "$FAMILY_SHA" --prepared "$PREPARED" \
  --closure "$C292_CLOSURE" --preflight-dir "$C270_STATIC" --r0-dir "$C270_PHYSICAL" \
  --new-output-dir "$NEW_AUDIT"
```

O banco de vítimas, a prioridade de expulsão, os quatro grupos de serviço, o endpoint C281 e o histórico de uma conversa pertencem a outras intervenções. Os clocks deste cliente incluem captura de tensores e testemunhos de bytes nos consumidores. A conclusão deste par tem o âmbito dos estados e saídas observados no corpus fornecido. [Custo histórico C293](../../../C293-INTEGRATED-EXPERT-STORE-COST-NO-GO-20261006.md) · [Serviço combinado em quatro waves](../../phase_fd/integrated/t1_full_pack_service/README.md)
