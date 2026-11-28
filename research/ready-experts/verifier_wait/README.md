# O Tesy ganha mais com outro verificador ou com os experts prontos?

**GO para investigar a entrega de pesos ao executor serial. NO_GO para financiar uma reescrita completa com base no verificador N2/M2.** No 120B original, as 46 chamadas seriais que levam da âncora ao EOG demoraram **2,004–2,059 s** quando os quatro experts de cada camada já estavam residentes. As 34 chamadas da agenda com propostas levaram **2,110–2,175 s** nas mesmas condições. Na execução habitual, essa agenda pediu mais 105 cargas. O teste mede uma oportunidade de arquitetura. A preparação dos pesos para um token ainda desconhecido faz parte do custo da solução.

### Dois percursos físicos na mesma conversa

Cada processo reconstruiu T1 e reutilizou as 2 044 posições de histórico antes dos 153 tokens novos de T2. O primeiro forward de cada passo seguiu o routing real e pagou os misses. A fixture removeu apenas o sufixo acabado de gerar e repetiu os mesmos inputs duas vezes, com os experts desse passo nos slots. Os **160 forwards adicionais** passaram com zero faltas e zero espera na barreira. Cada linha de 201 088 logits finitos coincidiu bit a bit, incluindo propostas descartadas. O KV vivo antes e depois, os experts e gerações, os quatro cortes de estado e a trajetória até EOG coincidiram com os respetivos controlos independentes. A fixture repôs a frequência e recência após cada repetição, conservando a política do percurso ordinário. [Protocolo](hot-protocol.md) · [Tempos, contadores e recursos por braço](evidence-20261128-r01/resident.json)

| Medida ou projeção no nominal | Serial S | Verificação N2/M2 |
|---|---:|---:|
| Chamadas após a âncora / IDs confirmados incluindo âncora | 46 / 47 | 34 / 47 |
| Cargas no percurso normal / bytes alinhados calculados | 1 091 / 14,425 GB | 1 196 / 15,813 GB |
| Tempo sincronizado dos passos residentes até ao primeiro final | 1,919–1,971 s | 2,014–2,071 s |
| Tempo sincronizado de todos os passos residentes | 2,004–2,059 s | 2,110–2,175 s |
| Primeiro conteúdo com prefill W original e decode residente, projeção | 11,079–11,807 s | 11,177–11,911 s |
| Primeiro conteúdo com prefill treinado simulado e decode residente, projeção | 6,033–6,354 s | 6,130–6,458 s |
| Margem comum para obter os pesos e para as restantes despesas, projeção | 3,646–3,967 s | 3,542–3,870 s |

No serial, mesmo com decode residente, o prefill teria de terminar em **7,842 s** no braço mais exigente, usando o extremo conservador da emissão. Ao substituir o prefill por 4,104 ou 4,197 s da simulação anterior, há um caminho condicional para os dois objetivos. Para o percorrer, a parte exposta do custo ordinário acima do preço residente tem de baixar cerca de **44,5–46,3%** no cenário proporcional do serial. Preparar os experts repetindo o próprio forward antes de cada passo custaria **14,793–15,115 s** até ao primeiro conteúdo. Antecipação bem-sucedida, trabalho transferido para T1, compras de memória, erros de previsão e contenção têm de ser cobrados onde ocorrerem. O estudo conserva separadamente os extremos de emissão, o resíduo do decode W e os dois relógios do cliente. [Prefill e banco causal](../layer/prefix/wave/tier-result.md)

Se a intervenção só conseguir preparar os experts dos B3, mantendo os passos seriais ao preço W, os tempos residentes medidos dão **9,604–9,940 s** até à primeira peça. No pior braço ficam apenas **60 ms no total** para a preparação adicional dos dez blocos anteriores ou simultâneos a essa peça. Subtrair a espera contabilizada pelo backend dava 9,681–10,054 s. A repetição física distingue esses dois cenários. [Atribuição das barreiras, controlos e falha de admissão](barriers.md)

### Reproduzir

O ensaio de barreiras teve quatro processos com modelo e a fixture residente dois. A campanha inicial preserva uma recusa de admissão C118 antes de criar o quarto processo. B0b foi recolhido separadamente, 297,0 s após o arranque de B1, com nova C55. Os dois processos residentes demoraram 104,623 e 104,168 s cada. A CPU atingiu 95,375 °C, a GPU 64,57 °C e o NVMe 56,85 °C no conjunto. Pico de 16 391 073 792 B no cgroup E20, GPU até 6 854 MiB e zero swap nos seis processos. A energia de GPU amostrada nos dois processos residentes somou cerca de 3 100 J. A energia total do portátil é desconhecida. Os testemunhos locais, incluindo FAIL e compiladores/comandos, ficaram no arquivo privado de 192 ficheiros. [Comandos e commits](evidence-20261128-r01/commands.json) · [Manifesto do arquivo](evidence-20261128-r01/archive.json)

~~~sh
u=research/ready-experts/verifier_wait
e="$u/evidence-20261128-r01"
python3 -IB "$u/review.py" --check "$e/barriers.json"
python3 -IB "$u/hot_review.py" --check "$e/resident.json"
python3 -IB "$u/test_cuts.py"
python3 -IB research/qualification-retake/private_archive/verify.py "$TESY_VERIFIER_ARCHIVE" "$e/archive.json"
p="$TESY_VERIFIER_ARCHIVE/part-01"
python3 -IB "$u/review.py" --check "$e/barriers.json" --family "$p/tesy-verifier-wait-20261128-r01" --last "$p/tesy-verifier-wait-last-20261128-r01" --client "$p/tesy-verifier-wait-build-20261128-r02"
python3 -IB "$u/hot_review.py" --check "$e/resident.json" --previous "$p/tesy-verifier-wait-20261128-r01" --family "$p/tesy-verifier-hot-20261128-r01" --client "$p/tesy-verifier-hot-build-20261128-r01"
~~~
