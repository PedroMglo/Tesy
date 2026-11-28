# Uma mudança no backend CPU chega à conversa?

**GO como componente para o nominal desta conversa. NO_GO para financiar um backend novo com este mecanismo.** O executor atual serviu o modelo com a nova fusão e obteve primeiro conteúdo final e conclusão válida mais cedo em 4/4 contrastes. O melhor turno ON combinou **17,689 s** até ao primeiro final, **17,938 s** até à validação e **5,357 tok/s** no mesmo pedido. M3 continua PARTIAL e M4 NOT_MET. As unidades seguintes qualificaram o custo do trabalho fornecido e a função Python gerada numa conversa com histórico contra R0 independente. O comparador de código gerou 256 IDs e passou o validador nos seis processos. A sessão sustentada desta combinação ainda exige medição. [Comparação de custo e destino CPU](supplied/README.md) · [Conversa de código e teste de um executor independente](code_chat/README.md)

## O que correu no portátil

O servidor recebe duas mensagens em HTTP local. A segunda reutiliza 2 044 IDs da primeira interação, avalia mais 153 e produz 47. O router, os quatro ranks, os pesos MXFP4, o KV e a confirmação de cada saída pertencem ao 120B original. Os quatro workers lêem o pack C291 do NVMe interno. O processo usa 40 slots por camada, uma sequência, contexto 8192, ub32 e a colocação GPU12. Estes braços usam a mesma otimização anterior de empacotar as três matrizes. A alteração nova fica inteiramente no executor GGML da CPU.

Depois de o manager publicar os IDs físicos de uma wave, a CPU pode observar que os quatro ranks de **todas** as posições estão estacionados. Nesse caso as três multiplicações por matrizes escrevem zeros. O executor dispensa os resultados intermédios privados de dez nós, executa o callback original da máscara, conserva os IDs lógicos antes de reutilizar os buffers e aplica o bias, a máscara e a soma pela ordem F32 original. Uma wave ativa ou com resultados pedidos em outro ponto segue o despacho anterior. Uma única posição de decode usa também esse despacho. A posse dos pesos e do KV continua nos gestores originais. A coordenação acrescenta três barreiras entre threads e duas tabelas de até 128 entradas por thread. [Implementação](wave.inc) · [Geometrias, reativação e critérios congelados](protocol.md)

**Antecedente revisto em 27 de novembro de 2026.** O próprio executor já dispõe de um ponto de fusão. O PR upstream #22423 integrou RMSNorm e multiplicação e mediu o operador F32 num Apple M2 de 24 GB. No #20596, fundir trabalho de MoE no decode de Qwen3.5-35B-A3B Q4_K_M com experts na CPU, tg32, apresentou 1,04–1,08× no EPYC de 96 núcleos e 0,97–1,00× no Ryzen de 16 núcleos com RTX 5090 no ensaio citado. A intervenção Tesy usa os IDs físicos decididos a cada submissão, tem uma rota de fallback e mede o prefill do GPT-OSS no Ryzen com GPU discreta e pesos paginados. São antecedentes de engenharia e razões para medir cada perfil. [Implementação upstream de RMSNorm](https://github.com/ggml-org/llama.cpp/pull/22423) · [Método, comandos e resultados de MoE](https://github.com/ggml-org/llama.cpp/pull/20596)

## Exatidão e custo da camada

- **REPRODUZIDO sem modelo.** ORIGINAL/OFF/ON deram o mesmo SHA-256 em 2 850 816 B por braço e repetiram os callbacks das 144 submissões por braço. A DSO observável contou 0 fusões em OFF e 36 em ON. O teste incluiu reativação, máscara não nula, corte de grafo, consumidor secundário, strides, zeros com sinal, subnormais e um ou oito threads. Build e fixture demoraram 2,397 s com pico de 224 940 032 B e swap zero. [Fixture](fixture.cpp) · [Receita pinada](build.py)
- **MEDIDO na camada CPU0.** Usámos ativações e pesos reais e uma referência monolítica independente. A comparação incluiu logits de router, bias, top-4, máscara, FFN, cópias, gerações de slots e estado final. Houve 20 fusões observadas. Nos nove processos, o pack devolveu 18 206 539 776 B no total. O scope chegou a 683 393 024 B. A primeira identidade falhou ao tentar criar o inventário numa pasta ausente, antes do primeiro processo da camada. A tabela usa a segunda identidade. [Verificação e temporização](layer.py)

| Ordem | Mediana residente ORIGINAL / OFF / ON, ms | Sequência diversa ORIGINAL / OFF / ON, ms |
|---|---:|---:|
| ORIGINAL → OFF → ON | 17,512 / 18,294 / 14,754 | 686,620 / 679,676 / 670,782 |
| ON → OFF → ORIGINAL | 18,232 / 17,610 / 14,757 | 668,759 / 682,139 / 680,667 |

O ON poupou 2,758 e 3,475 ms contra ORIGINAL nas sete tiles residentes. Na sequência diversa a segunda ordem custou mais 11,909 ms contra ORIGINAL, dentro da proteção prévia de +5%. O teste de camada admitiu o teste numérico do modelo completo.

**MEDIDO no target misto.** Foram processados 189 IDs e cinco passos greedy por processo. ORIGINAL, OFF e as duas versões ON coincidiram nos seis vetores de 201 088 logits finitos, seis cortes completos de KV base/SWA e sete estados de pools, contra as referências independentes das partes 173 e 176. O target contou 3 441 cargas antes da primeira saída e 3 685 até ao fecho em cada execução. A DSO de auditoria contou 765 fusões ON e zero OFF. A DSO usada para timing reproduziu os mesmos 19 ficheiros sem contador. Os cortes só provam os estados e as saídas observados. O ensaio não exporta todos os IDs de router internos. ORIGINAL e OFF completaram em R01. O inventário C118 de ON nessa identidade perdeu cadência antes de arrancar o modelo. R02 revalidou os dois controlos e mediu ON com e sem contador numa janela C55 nova. [Protocolo do target](target.md) · [Falha e condição de retoma](retoma.md) · [Conferência dos artefactos](target.py)

## Duas ordens da conversa natural

**MEDIDO com a RTX 4060 Laptop.** Seis processos, doze pedidos, 750 tokens de saída incluindo uma terminação EOG por pedido e ambos os validadores em cada processo. O logger nativo confirmou cada ID. A medição usa a DSO PRICE sem contador, o mesmo cliente e o mesmo regime térmico de admissão em todos os braços. A cache do sistema evoluiu com as duas ordens. Duas repetições por braço não estimam p95 ou p99.

| Ordem | Braço | Turno | Prefill (s) | Decode (s) | tok/s | Primeiro final (s) | Transporte (s) | Válido (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | ORIGINAL | T1 | 58,172 | 18,419 | 4,235 | 76,221 | 76,603 | 76,606 |
| 1 | ORIGINAL | T2 | 9,908 | 9,121 | 5,153 | 18,782 | 19,040 | 19,043 |
| 1 | OFF | T1 | 61,067 | 18,188 | 4,289 | 78,876 | 79,266 | 79,269 |
| 1 | OFF | T2 | 9,905 | 9,076 | 5,179 | 18,735 | 18,992 | 18,996 |
| 1 | ON | T1 | 55,378 | 18,249 | 4,274 | 73,249 | 73,638 | 73,640 |
| 1 | ON | T2 | 9,650 | 9,133 | 5,146 | 18,533 | 18,793 | 18,796 |
| 2 | ON | T1 | 54,955 | 17,661 | 4,416 | 72,251 | 72,626 | 72,629 |
| 2 | ON | T2 | 9,151 | 8,774 | 5,357 | 17,689 | 17,935 | 17,938 |
| 2 | OFF | T1 | 57,281 | 17,580 | 4,437 | 74,495 | 74,872 | 74,875 |
| 2 | OFF | T2 | 9,523 | 8,783 | 5,351 | 18,074 | 18,318 | 18,322 |
| 2 | ORIGINAL | T1 | 57,166 | 17,617 | 4,427 | 74,424 | 74,795 | 74,797 |
| 2 | ORIGINAL | T2 | 9,527 | 8,847 | 5,313 | 18,140 | 18,387 | 18,390 |

| Ordem | Controlo | Ganho no primeiro final (s) | Ganho no válido (s) | Ganho de prefill (s) | Ganho de decode (s) | Proteção de decode T2 / válido T1 |
|---|---|---:|---:|---:|---:|---|
| 1 | ORIGINAL | 0,249 | 0,247 | 0,258 | -0,012 | PASS / PASS |
| 1 | OFF | 0,202 | 0,200 | 0,255 | -0,057 | PASS / PASS |
| 2 | ORIGINAL | 0,451 | 0,452 | 0,376 | 0,073 | PASS / PASS |
| 2 | OFF | 0,385 | 0,384 | 0,372 | 0,009 | PASS / PASS |

Os ganhos positivos são segundos poupados pelo ON. O tempo de decode varia com as condições do processo apesar de a nova fusão exigir pelo menos duas posições. O relógio de validação inclui o fim aceite pelo cliente. A limpeza começa no último corte do cliente e termina depois de verificar processo, scope e porta. Os tempos READY, limpeza, C118, swap, energia e cobertura por braço constam do recibo.

Família HTTP em 1 271,303 s com CPU até 95,5 °C, RTX até 65,43 °C e NVMe até 56,85 °C. Pico de 14,86 GiB no cgroup e 6 848 MiB de VRAM. Swap 0 B. A integração das amostras da placa estima 8 571,9 J em 589,3 s cobertos. A energia do portátil permanece desconhecida.

**DIAGNÓSTICO do caminho até ao conteúdo.** Nos dois processos ON, o primeiro texto final correspondeu à amostra 45 dos 47 IDs. No relógio do produtor, desde o registo da primeira amostra ao despacho do ID 44 decorreram 8,697 / 8,361 s. Este despacho precede necessariamente a obtenção da amostra 45. O log dessa amostra pode chegar depois de o servidor enfileirar a resposta parcial, pelo que o cálculo usa o despacho anterior. Com esse trecho fixo, o orçamento dos 10 s deixa **1,303 / 1,639 s** para todo o resto, incluindo prefill e a última avaliação necessária. Fixando em alternativa o trecho do arranque da tarefa à amostra 1, ficam **0,350 / 0,849 s** para o resto. Estes são limites condicionais na mesma sequência de tokens. Usam durações no mesmo relógio, com o exterior oferecido, e deixam explícito o tamanho da mudança que uma arquitetura de uma só fase teria de demonstrar.

**Próxima comparação de custo fornecido.** Reabrimos os oito braços C293 e avaliámos a combinação sob a hipótese de remover a mesma fração só do prefill de cada candidato com pack. Nos casos nominal/código seriam precisos **1,1109% / 3,5385%** dos respetivos prefills para passar a via de +8% no total, protegendo o outro caso observado. O avaliador original distingue o ponto admissível do milionésimo anterior. Os tempos da tabela HTTP têm outro trabalho e outro relógio. A confirmação pede medir o despacho com o pack e a opção OFF nos mesmos oito braços e conferir as 33 linhas de logits. [Hipótese e critérios](composition.md) · [Segundos por par e gates de fase](composition.json)

## Proveniência e reprodução

A extensão começou na branch do PR #52 em `69f19ddd`, com o #51 como base imediata e main em `293f5b18`. O controlo operacional integrado é R0 slots40-persistent. A comparação desta unidade isola o despacho CPU sobre a biblioteca de produto C291 e o mesmo layout nos três braços. O pré-registo da camada foi `3f588d4f`, o do target `20eb0f7b` e o do HTTP `79730027`. O build correu em `13c58b60`, a camada completa em `859ea7d9`, o target em `703f6dab` e `7b105a2c` e o cliente em `28bcdbde`. O recibo compacto liga cada braço aos seus hashes integrais, árvores, DSO, janelas de recursos e FAILs. O cliente usa o mesmo nível de log nativo nos três braços e trace de routing desligado. [Pré-registo do cliente](http.md) · [Execução por braço](client.py) · [Comandos e revisões dos ensaios físicos](commands.json) · [Recibo comparativo](decision.json)

O arquivo privado exclusivo `ready-cpu-wave-20261127-01/part-01` guarda 642 ficheiros e 348 644 738 B contabilizados antes do manifesto, incluindo FAILs. Os 30 links de providers são registados pelo destino literal sem seguir ligações externas. SHA-256 do manifesto `c96f1b05a144cdee63b87d8e8c7471169fc928894d93411eaa06ee2ef2da0c18`. Pesos, prompts e ativações permanecem no portátil. As variantes e entradas autenticadas de campanhas anteriores continuam identificadas nos protocolos. [Selo da cópia](archive.json)

A reanálise C293 foi congelada em `06270526`. A tentativa com o Python do sistema parou porque o avaliador histórico importa NumPy. O verificador conserva esse erro como FAIL. Com o Python do ambiente Tesy (`TESY_PYTHON`, NumPy 2.5.3), as duas execuções reabriram os 24 ficheiros dos oito braços e produziram o mesmo recibo. A repetição demorou 0,21 s, com pico de 44 964 KiB. O C293 tem uma chamada externa de 153 com última tile de 25 posições. O cliente HTTP tem 5+148 com última tile de 20. [Falha de preparação reproduzida](composition-setup.json)

```sh
unit=research/ready-experts/cpu_wave
python3 -IB "$unit/review.py" --check "$unit/decision.json"
python3 -m pytest -q tests/test_ready_cpu_wave.py
python3 -IB research/qualification-retake/private_archive/verify.py "$TESY_CPU_WAVE_ARCHIVE" "$unit/archive.json"
raw="$TESY_CPU_WAVE_ARCHIVE/part-01"
out=$(mktemp -d)
python3 -IB "$unit/review.py" --raw-root "$raw" --http "$raw/tesy-native-wave-http-20261127-r01" --new-output-dir "$out/review"
cmp "$unit/decision.json" "$out/review/decision.json"
python3 -IB "$unit/composition.py" --new-output-dir "$out/c293-publico"
"$TESY_PYTHON" -IB "$unit/composition.py" --raw-dir "$TESY_C293_RAW" --new-output-dir "$out/c293-raw"
cmp "$unit/composition.json" "$out/c293-raw/composition.json"
```
