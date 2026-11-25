# Referência numérica independente de CPU0 para a primeira avaliação de decode

**PASS. A referência residente da C127 já calculou o FFN de um token na posição 189.** O input, os quatro ranks lógicos, as suas ponderações e todos os **2 880 F32** da saída coincidem bit a bit com a captura C270 R0. A saída independente reutilizável tem 11 520 B e SHA-256 `6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333`. O preparador selou os sete tensores observados e o plano de pesos para o consumidor C291. Foram necessários zero bytes do GGUF ou do pack e zero novos forwards. [Protocolo](protocol.md) · [Recibo de referência](evidence/reference.json) · [Prova do pré-estado](evidence/prestate.json)

| Rank | Expert lógico | Estado antes da procura | Slot/geração no consumidor | Presente na última tile CPU0 |
|---:|---:|---|---|---|
| 0 | 28 | READY | 3 / 6 | sim |
| 1 | 24 | ABSENT_RELOAD | 14 / 6 | não |
| 2 | 8 | READY | 6 / 5 | sim |
| 3 | 16 | READY | 35 / 4 | sim |

A C127 qualificou a execução residente C77 no namespace de 128 experts e na CPU, com os pesos, os biases e o router originais. O executável carregou a camada de 1 697 956 352 B e confrontou a sua saída calculada com a captura ON. Revalidámos o stdout/monitor dessa execução, a origem em `tools/c7_layer_reference.cpp`, o SHA da árvore usada (3 266 ficheiros e 88 704 231 B) e a linha única de decode0 com igualdade dos IDs, pesos de routing e FFN, sem valores não finitos. Em seguida procurámos as mesmas fronteiras pelo nome da fase, camada e posição no manifesto independente de ficheiros C270. A referência C266 da fixture anterior cobre a geometria do prefill de 153. O seu pack parcial de cinco experts tem interseção vazia com estes quatro. [Operador residente](../../../../../../../../../../tools/c7_layer_reference.cpp) · [Origem da captura do cliente](../../../../../../../../../../tools/c127_slots40_boundary_capture.cpp)

**Quatro fontes para preparar a fixture, uma fonte em falta no decode do cliente.** O índice C291 no NVMe e o índice histórico C290 concordaram nos quatro registos inteiros e nos 24 descritores de componentes. O plano privado sela, por rank, os offsets absolutos, 12 matrizes MXFP4 e 12 biases F32 com os respetivos tamanhos e SHA. Os 24 checks históricos no consumidor cobrem a identidade, slot, geração, papel e bytes. Nos índices C290 a ordem das três matrizes é gate/down/up. No testemunho C127/C270 é gate/up/down. O plano liga explicitamente as duas numerações. Os dois ficheiros do router da preparação C266 já têm hashes que o consumidor pode verificar ao abri-los.

Ler as quatro entradas completas para uma fixture autónoma custaria **53 035 008 B**, incluindo os biases e padding. O endpoint na posição 189 já tinha três experts presentes na mesma slot/geração em que o FFN acabou por consumi-los. Só o expert 24 precisava de voltar ao primário. Uma leitura de payload C291 para essa falta pediria **13 221 888 B** alinhados; os biases da execução C291 estão fora da janela de três pesos. A última tile C270 tinha 29 posições [160,189) e 55 experts distintos. Para reconstruir o top-4 por posição foi preciso respeitar o stride de 512 B entre colunas, lendo os quatro I32 do início de cada coluna. A presença de um ID na tile e a residência à entrada do decode são observações separadas. O arquivo demonstra ambas para estes três experts, sem descrever os outros 36 vínculos do primário. [Protocolo da junção](prestate.md)

**Uso no próximo ensaio de runtime.** A decisão de routing, os pesos associados aos ranks e o gold completo devem manter-se com os novos endereços. Comparar no remap nativo de um token e guardar a saída antes da comparação. A contraprova de dados prevista troca os backings gate dos dois primeiros ranks lógicos e exige que a medição física detete uma diferença finita. Os testes desta preparação detetam um bit alterado, rank trocado, NaN, slot trocada, padding mal interpretado e papel em falta. A mutação física permanece pendente. Uma fixture que chegue da trajetória C266 com cinco experts diferentes pode testar a aritmética de decode, mas terá quatro misses locais; a mistura 3 READY + 1 reload precisa de uma entrada própria. A posição 189 do corpus C127/C270 e a posição 2197 do T2 natural têm histórias distintas. [Preparação e testes](prepare.py)

## Reprodução

Fixar a checkout limpa do preparador em `48f09284`, precedida pelo protocolo `9d682e75`. O anexo usa `df1108ea` e o protocolo `a974d891`. A raiz `LAB` contém `results/` das campanhas C127, C270 e C290. O manifesto, a preparação da tile e os ficheiros de entrada são autenticados antes de qualquer saída qualificada. Usar um novo destino privado para cada execução.

```sh
U=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias/manager/decode_reference
python3 -IB "$U/test_prepare.py"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$TESY_VENV/bin/python" -IB "$U/prepare.py" \
  --lab "$LAB" --manifest-dir "$MANIFEST_C291_R02" --tile-input "$PREPARED_CPU0_R01" \
  --new-output-dir "$NEW_REFERENCE"

# A partir da revisão do anexo
python3 -IB "$U/test_prestate.py"
timeout 120 prlimit --as=536870912 python3 -IB "$U/prestate.py" \
  --lab "$LAB" --prepared "$NEW_REFERENCE" --new-output-dir "$NEW_PRESTATE"
```

O bundle privado tem `plan.json`, `receipt.json` e sete ficheiros `<stage>.bin` de 24 112 B no conjunto. A abertura e comparação das duas árvores produziu ficheiros byte a byte iguais nas duas reproduções, SHA-256 do recibo principal `8f9b7bb692c9974eac9bca2cb8a4d08436ef83a1e245ba2bbe37442430c6e10f`, plano `1f1caaba34f4581f253691feee436358a8e3bcb2c67b5fd489418f52176510f1`. Durações do preparador 0,46/0,30 s e RSS 76 084/75 964 KiB. O anexo confirmou a prestate em 0,05 s por processo, 28 056/27 928 KiB, com o mesmo SHA-256 `9bc5d91831e50f4f8cacc73f5b34b02542c2c8b5010cb1e620f7ddb7d2101ec6`. Seis testes sintéticos passaram. Estes tempos pertencem à verificação local de ficheiros.
