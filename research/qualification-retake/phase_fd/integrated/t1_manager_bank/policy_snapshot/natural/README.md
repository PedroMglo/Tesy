# O que uma política de vítimas pode acrescentar à conversa

**GO para conservar a política e o banco como combinação em testes de serviço. NO_GO para os adotar como solução suficiente no regime testado.** Com 353 vítimas recuperáveis mantidas em RAM, a prioridade de expulsão evitou mais 50 leituras de disco no prefill e 122 no decode deste pedido do 120B. Sem servir a partir do banco, essa prioridade aumentou o número de leituras. A identificação usa uma captura real de R0 e dois replays que reproduziram 2 987 decisões do manager, incluindo as 2 354 reservas. O benefício medido em quatro waves com o layout do pack continua uma evidência independente. A latência da nova política na conversa é **INCONCLUSIVE**, M3 **PARTIAL**, M4 **NOT_MET**. [Reprodução das escolhas nativas](replay/README.md) · [Quatro braços físicos de transporte e política](../../../t1_full_pack_service/README.md)

| Tratamento dos pesos e da cache de T2 | Leituras de disco no prefill | Leituras de disco no decode |
|---|---:|---:|
| R0, servido do GGUF | 1 263 | 1 091 |
| R0, serviço com o mesmo banco | 1 108 | 919 |
| Expulsão prioritária, tags do banco, todas as faltas servidas de disco | 1 284 | 1 196 |
| Expulsão prioritária com as cópias do banco | **1 058** | **797** |
| Mesma combinação, com reposição do estado antes do primeiro decode | **1 058** | **799** |

A interação também se vê em números absolutos. No prefill, acrescentar o banco à política R0 poupou 155 leituras e dar prioridade às suas tags sem servir os pesos custou 21. Somar os efeitos isolados daria 134 leituras poupadas. A combinação evitou 205, mais 71. No decode, a soma daria 67 e a combinação evitou 294, mais 227. Cada contraste parte da mesma agenda de consumidores do target. A contagem de leituras e a contagem de bytes entregues ao primário divergem quando um miss de slot passa a hit no banco.

A primeira linha corresponde aos pedidos físicos verificados. As outras são **SIMULATED** nas rotas da execução ON. A reposição adiciona 19 entradas, todas cobertas pelo banco, e 428 movimentos dentro dos dispositivos. Cobrar a leitura das entradas ausentes deixa portanto a mesma contagem no disco. O custo de mover os pesos e tornar as gerações seguras precisa de execução. Durante o sufixo observado de T1, construir o banco a partir de vazio implica 20,225 GB de cópias de pesos CPU e 8,103 GB de cópias de pesos CUDA. A fixture que partilha páginas entre duas vistas na CPU passou os controlos de leitor e de reutilização das páginas. [Reposição por tier](replay/README.md) · [Experiência CPU e falhas induzidas](cpu_alias/README.md)

## O orçamento da conversa

| Braço físico R02, PFJ1 ativo nos dois | Prefill T2 | Decode T2 | Primeiro final | Conclusão válida | Débito |
|---|---:|---:|---:|---:|---:|
| OFF, sem fotografia do seletor | 10,871 s | 10,079 s | 20,754 s | 21,031 s | 4,663 tok/s |
| ON, captura de 48 800 B | 10,893 s | 10,118 s | 20,793 s | 21,083 s | 4,645 tok/s |

Cada execução confirmou a trajetória de 78 e 47 tokens nos dois turnos e ambos os validadores. No segundo turno, dos 2 197 IDs de entrada, o servidor reutilizou 2 044 e processou 153 em 5+148. Os quatro rácios ON/OFF de T2 ficaram entre 1,0019 e 1,0040. A prova de paridade e a banda de custo são descritivas deste par. O monitor contou 6 848 MiB de VRAM de pico em ambos, cgroup de 15 990 554 624 / 15 940 538 368 B e swap zero. Integração da potência GPU sobre 106,806 / 106,916 s cobertos deu 1 445 / 1 464 J para o intervalo monitorizado de cada servidor. A maior lacuna entre amostras foi 1,020 / 1,049 s. Energia do portátil e energia isolada de cada pedido permanecem desconhecidas. A saída física terminou normalmente nos dois braços. [Quatro turnos, limites, temperaturas, arranque e encerramento](acquisition-result.md) · [Contagens e clocks auditados](evidence/pair.json)

**ESTIMADO sob hipóteses explícitas.** À banda útil de 4,5 GB/s, os 1 058 experts no prefill exigem 3,108 s apenas para o payload. Conservar os 1,151 s de intervalos entre camadas sem sobreposição de I/O deixa a combinação 1,874 s acima do orçamento a exatamente 6 tok/s no braço ON. Ao distribuir o ganho pelas fases, o cruzamento exige pelo menos **7,887 tok/s de decode** se os preços do prefill e a cauda do cliente se mantiverem. Mesmo nesse ponto a preparação e entrega da RAM, o trabalho adicional do grafo e o cleanup precisam de caber nos respetivos relógios. [Cruzamentos das seis configurações nas duas convenções](evidence/cost.json)

**Limite para qualquer escolha inicial de 353 experts.** Os dois pedidos precisaram de 852 experts distintos ausentes do primário inicial, 558 de camadas CPU e 294 de camadas CUDA. Mesmo concedendo que cada uma das 353 cópias acerta num expert diferente e que cada leitura posterior é paga uma única vez, restam 499 experts. Com o restante pico de memória fixo e zero overhead caberiam até 374 / 378 experts crus fora do primário. No mesmo regime de 4,5 GB/s, 6 tok/s e todos os intervalos preservados, seriam necessários pelo menos **434 / 432** já preparados no ramo nominal de 47. Na sensibilidade de 46 avaliações o mínimo cai para 378 / 376. Repor o primário antes do primeiro decode não introduz novas *chaves distintas* nestes braços. As releituras ou permutas da implementação podem custar tempo adicional. O limite deixa aberta uma combinação que ganhe também no decode, na sobreposição, na banda ou na memória usada por outros buffers. [Hipóteses e contagem por braço](capacity-floor.md) · [Recibo reproduzido](evidence/capacity-floor.json)

Com as últimas publicações de T1 na parte 40, aumentar o banco de 353 para 386 acrescentou só cinco chaves que eram obrigatórias e estavam ausentes. Os 66 096 000 B de melhoria no piso conservam-se. O novo piso de 834 continua acima das 808 leituras do cenário nominal naquela captura. A compressão que permitiria guardar essas entradas merece comparação com o espaço livre necessário para as guardar em cru. [Capacidade e overhead](bank_capacity/README.md) · [Interseção real e limite em K390](bank_capacity/intersection/README.md)

No portátil, o alvo processou uma conversa de dois turnos com o GPT-OSS-120B MXFP4 original. A observação adicional de 48 800 B guarda as frequências de utilização dos experts e a antiguidade dos 40 slots de cada camada no instante em que começa o segundo pedido. Estes dados permitem testar a prioridade dada à expulsão de uma cópia já recuperável em RAM. O transporte, os pesos e a escolha dos experts continuam a cargo do target. [Desenho da comparação física](protocol.md) · [ABI e teste de origem da biblioteca](build-result.md) · [Estado ausente nos traces anteriores](../README.md)

## Proveniência e falhas preservadas

Base integrada `293f5b184da9439771cce361cd33fc4068d749f4`, reunião de resultados na branch do PR 49. Em ambos os modos do novo binário o PFJ1 está ativo desde T1. OFF e ON referem-se apenas ao ficheiro adicional de política. O R0 independente com o observador inteiramente desligado confirmou 20,385 s de primeiro conteúdo final e 4,767 tok/s no nominal. A paridade do novo binário cobre os 78/47 IDs de saída e as rotas observadas, com os mesmos inputs e escolhas do cliente. A comparação de logits completos do C270 pertence ao binário que a executou. [Referência de produto](../../../../../nvme_conversation/postupdate/physical-result.md) · [Relógios e unidades](accounting.md)

A primeira família física ficou **FAIL_PRESERVED** em `1c5219d8`. OFF terminou normalmente. No turno nominal mediu 20,434 s até ao primeiro final, 20,724 s até à conclusão válida e 4,718 tok/s. O pré-voo ON encontrou a porta 18442 em TIME_WAIT, sem listener e com o serviço anterior inativo. Encerrou antes de iniciar um servidor ou fazer um POST. O manifesto privado da parte 62 conserva a aquisição, os oito ensaios do build, as duas revisões, a C55 e o diagnóstico da porta em 121 ficheiros e 22 268 930 B, SHA-256 `2b36d9be1c715686d1d2435905aab16cd491af79ebdc99415ee855120c55295f`. Os SHA-256 do recibo da família e do diagnóstico são `1e4895c83852a9cb0c4c754254bc03e085c9b98b8203712533c24fe85263898d` e `4b7fa0ee3bf505d8967e9318697907ca59540da455619c9a2648c0d5917f1c6d`. A família R02 usa dois novos processos e o mesmo bind original. Toda a espera entre processos ocorre antes da admissão C118 de ON e fora dos pedidos. [Condição de retoma](interarm.md)

## Reprodução

A parte 63 de `qualification-20261124-nvme-01` guarda os braços R02 e a revisão dupla em 88 ficheiros e 23 191 689 B. O manifesto tem SHA-256 `f46876468215957504f27d593081142a99d46220cf9ab42782965833eab1da7f`. As duas revisões do par deram `bb6e2b508bf35af6001ccbb5bec655ae3235bf69d1a8d74af84b4382b640b889` em 0,89 / 0,86 s, com RSS até 82 604 KiB. O crivo de capacidade deu `d331d4069d172246588f2f5ad86bcd7d317082eeb11204252dbcb7fb6349f6ef` em 0,24 / 0,23 s, até 84 036 KiB. O crivo de custo deu `19e326bc467aa5c6403a29cb3fc05357706f7d23f33bf598928352b02b00592e` em 0,03 s por processo. As revisões leem traces e recibos em CPU. A experiência física fechada utilizou o modelo três vezes no total, incluindo o controlo da primeira família. [Aquisição no portátil](acquisition-result.md)

```sh
u=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural
F="$PART63/tesy-policy-natural-physical-20261125-r02"
P="$PART63/tesy-policy-natural-account-20261125-r01/receipt.json"
R="$PART63/tesy-policy-natural-replay-20261125-r01/receipt.json"
pair_sha=bb6e2b508bf35af6001ccbb5bec655ae3235bf69d1a8d74af84b4382b640b889
python3 -IB "$u/pair.py" --family "$F" --history "$C281_R0" \
  --off-sha256 838f80b80341df3571e92257a2b45f24d81473696dc7892eeaafdd331f0bad11 \
  --on-sha256 8428c5ee301281ddeb1a7b1e2ed6883073e53578027139a67c2daef5b4eaaaf5 \
  --new-output-dir "$NEW_PAIR"
python3 -IB "$u/capacity_floor.py" --family "$F" --pair "$P" --pair-sha256 "$pair_sha" \
  --new-output-dir "$NEW_FLOOR"
python3 -IB "$u/cost.py" --pair "$P" --pair-sha256 "$pair_sha" --replay "$R" \
  --replay-sha256 494bb5d2e73b4e129b020118e1bcf2110f253b1c2b565b5d110023129516aa54 \
  --new-output-dir "$NEW_COST"
cmp "$NEW_PAIR/receipt.json" "$u/evidence/pair.json"
cmp "$NEW_FLOOR/receipt.json" "$u/evidence/capacity-floor.json"
cmp "$NEW_COST/receipt.json" "$u/evidence/cost.json"
```
