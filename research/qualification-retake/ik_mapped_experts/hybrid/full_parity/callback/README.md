# Controlo sem callback e custo de leitura do prefill

**REPRODUZIDO.** Ao reler os dois braços ON do GPT-OSS-120B, o verificador passivo reconstruiu cada triplo de camada/expert/slot para os três pesos, nas duas fases. De cada SET seguiu os offsets de ficheiro e de destino até à conclusão das cópias CUDA. A comparação com o ledger independente do callback encontrou zero fatias em excesso e zero em falta. O marcador OFF e a saída precoce por IDs inválidos passaram num ELF novo. Os dois forwards físicos OFF têm estado **NOT_RUN_GPU_REQUIRED**. [Critérios congelados](protocol.md) · [Prova de transporte por braço](rounding.json)

## Que parte das leituras cabe nas matrizes?

DIAGNÓSTICO a posteriori sobre o par ON. Para cada chamada CUDA que envia bytes do GGUF a um banco, arredondámos os dois extremos do intervalo a blocos de 4 KiB, 128 KiB e 2 MiB. O cenário cobra uma leitura fria integral por chamada, incluindo blocos que duas chamadas partilham. O quadro usa 2 MiB, o maior dos três cenários. GB decimais. [Verificador das cópias](transport.py) · [Cálculo dos intervalos](study.py)

| Banco e fase | Chamadas de cópia de matriz | Payload, GB | Uma leitura por intervalo arredondado, GB | Leituras do scope no NVMe, GB | Diferença, GB |
|---|---:|---:|---:|---:|---:|
| 288, prefill | 2 547 | 14,753 | 20,112 | 39,229 | 19,117 |
| 161, prefill | 2 544 | 14,753 | 20,105 | 39,437 | 19,332 |
| 288, token fornecido | 378 | 1,692 | 2,494 | 7,329 | 4,835 |
| 161, token fornecido | 411 | 1,837 | 2,703 | 7,017 | 4,314 |

**NO_GO** para a explicação de que as leituras do scope correspondem apenas a uma passagem por cada intervalo de matriz, com um destes três alinhamentos. Os 19,12–19,33 GB são resíduos dessa hipótese contabilística. Para os converter em poupança seria preciso identificar o acesso, eliminar o I/O e medir o efeito no caminho crítico. Releituras após expulsão, antecipação de páginas e acesso a outros tensores são explicações compatíveis. O pin do ik pede acesso sequencial ao descritor. O kernel pode antecipar folios de um ficheiro por ocasião de uma falta de página. A atribuição exige observação adicional neste portátil. [Fonte do ik no pin medido](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-mmap.cpp#L291-L341) · [Mecanismo de readahead do Linux](https://www.kernel.org/doc/html/latest/core-api/mm-api.html#readahead)

## Procedência e admissão

O protocolo do controlo foi congelado em `6f0ab337` e a construção em `d74e8809`. O porto de CUDA e o compilador são os do par ON. Recompilar a fonte histórica produziu o ELF original `ae22e3b4ece6120ffc7b513a1d597968994e65c6ddcccbc4a1e872896d8b9374`. O ELF com o seletor tem SHA-256 `90efe5e2c39b0da9a47f656670f3f041941f376a1c5bd251a6ef1178faf59c3c`. Com ON e OFF, o cliente escreveu o marcador correto e rejeitou os IDs vazios antes de abrir o modelo. Com a seleção ausente ou inválida rejeitou a configuração antes de escrever o marcador. O recibo local da construção tem SHA-256 `133315b9095ff5944b3017dc7b979287f7a3dcd35b485b59b86316c92b224b23`. As duas reanálises, a construção e o cálculo de alinhamento, com 13 ficheiros e 217 860 B, ficaram no lote privado 142. [Recibo do lote](../../../../private_archive/part-142.json) · [Construção](build.py)

No arranque do portátil de 26 de novembro às 10:56 UTC, o kernel carregou o módulo 620.70.06. O journal registou ENOENT para `gsp_ga10x.bin` e `ucodes_ga10x.bin` dessa release e falha de inicialização da RTX. O módulo e os dois ficheiros instalados em disco são 620.73.04. A NVML que corresponde ao módulo carregado devolveu zero dispositivos. A sessão gráfica usava a AMD. A recuperação transitória requer autenticação administrativa local. A construção e a reanálise deste lote fizeram zero forwards, zero pedidos HTTP e zero downloads de pesos.

Com o driver original, o supervisor reutiliza o C55, C118, o scope, a telemetria, a prova de colocação e as verificações de cleanup da família. Autentica ambos os braços ON e lança primeiro OFF288. Só o PASS dos dois vetores e do serviço abre OFF161. Para uma release de driver diferente, o protocolo começa pela fixture pequena e capacidade seguidas de controlos ON contemporâneos. O próximo discriminante após a paridade é reproduzir a mesma sequência de offsets com um destino CPU e comparar com o staging CUDA sob a mesma política de memória. A medição de produto no portátil continua dependente de pedidos naturais validados. [Admissão](run.py) · [Revisão numérica](grade.py)

```sh
python3 -IB research/qualification-retake/ik_mapped_experts/hybrid/full_parity/callback/study.py \
  --family "$TESY_PRIVATE_ARCHIVE/part-141/tesy-ik-e10-full-parity-20261126-r01" \
  --plan "$TESY_PRIVATE_ARCHIVE/part-138/tesy-ik-capacity-inventory-20261126-r01/plan.tsv" \
  --new-output-dir "$NOVO"
python3 -IB research/qualification-retake/private_archive/verify.py \
  "$TESY_PRIVATE_ARCHIVE" research/qualification-retake/private_archive/part-142.json
```
