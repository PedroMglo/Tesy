# L2 de bytes de experts à entrada dos workers

**NO_GO_POLICY** nas duas capacidades. A política de admissão por frequência evita entre 6,35% e 10,09% das leituras lógicas de decode dos quatro braços C294. Ganha à LRU e reduz as leituras da janela inteira em todos os braços. O critério prospetivo exigia 20% do decode nos dois casos. O ótimo com conhecimento do futuro ultrapassa esse limiar em ambos, mesmo com 243 entradas. A decisão fecha esta política no regime observado e conserva aberta a hipótese de uma política causal diferente. M3 continua PARTIAL e M4 NOT_MET. [Protocolo](protocol.md) · [Recibo completo](evidence/receipt.json)

## Leituras por braço

TRACE_DERIVED, com agenda primária R0 fixa. A L2 arranca vazia em P, depois do prefixo. O incremento fornecido de 153 tokens termina em I. Seguem-se 32 passos de decode. Cada leitura serve três componentes por geração. A tabela apresenta os valores **por braço**. Os dois braços trace-ON indicados em cada linha deram os mesmos totais e têm identidades de origem próprias no recibo.

| C294, repetições | Entradas L2 | Leituras R0 incremento/decode | Hits da política incremento/decode | Hits LRU incremento/decode | Decode poupado | Hits em falta para 20% | Leituras na janela política/LRU |
|---|---:|---:|---:|---:|---:|---:|---:|
| nominal153, 2 e 3 | 243 | 1043 / 1081 | 10 / 83 | 0 / 2 | 7,68% | 134 | 2031 / 2122 |
| nominal153, 2 e 3 | 378 | 1043 / 1081 | 14 / 106 | 2 / 10 | 9,81% | 111 | 2004 / 2112 |
| code153, 2 e 3 | 243 | 2106 / 1308 | 122 / 83 | 0 / 0 | 6,35% | 179 | 3209 / 3414 |
| code153, 2 e 3 | 378 | 2106 / 1308 | 161 / 132 | 0 / 1 | 10,09% | 130 | 3121 / 3413 |

Os 1081 lookups nominais de decode distribuem-se por 762 CPU e 319 CUDA. Com 243 e 378 entradas a política acerta, respetivamente, 72/11 e 80/26 em CPU/CUDA. No caso de código há 927 lookups CPU e 381 CUDA, com 83/0 e 132/0 hits. No incremento nominal há 724/319 lookups, com 7/3 e 8/6 hits. No incremento de código há 1668/438, com 122/0 e 161/0 hits.

## Margem e custo das cópias

O ótimo offline escolhe intervalos entre a publicação anterior da mesma chave em P10 e o próximo lookup em P5, respeitando K entradas. Concede o payload do serviço até P10 sem cobrar staging adicional. O ótimo da janela e o ótimo exclusivo do decode são objetivos distintos. Cada hit poupa uma leitura lógica de 13 219 200 B e exige uma cópia integral da L2 para o staging privado. Cada admissão copia o mesmo número de bytes para RAM. O recibo separa os destinos CPU e CUDA, os bypasses e as admissões usadas até F. [Oráculo](oracle.py) · [Avaliador](screen.py)

| C294, repetições | K | Máx. hits na janela | Máx. hits no decode | Decode máximo | Admissões da política, incremento/decode | Admissões sem uso até F | Cópias de admissão / de hits na janela (GiB) |
|---|---:|---:|---:|---:|---:|---:|---:|
| nominal153, 2 e 3 | 243 | 291 | 275 | 25,44% | 243 / 14 | 173 | 3,164 / 1,145 |
| nominal153, 2 e 3 | 378 | 309 | 292 | 27,01% | 378 / 13 | 281 | 4,814 / 1,477 |
| code153, 2 e 3 | 243 | 460 | 266 | 20,34% | 243 / 45 | 130 | 3,546 / 2,524 |
| code153, 2 e 3 | 378 | 595 | 401 | 30,66% | 378 / 28 | 178 | 4,998 / 3,607 |

Em 243 entradas, o código só admite quatro hits de folga entre os 262 necessários e o máximo de 266. A transferência para o primário totaliza 26,149 GiB no nominal (7,855 GiB RAM→GPU) e 42,031 GiB em código (10,083 GiB RAM→GPU) por braço. A cópia na primeira leitura dispensa trazer uma vítima CUDA de volta. O custo de entrega ao destino primário continua integral. Estes são payloads lógicos. A execução digital não mediu duração, setores efetivamente lidos nem pico de uma implementação.

No código C294, o worker reutiliza os seus 16 MiB de staging para os três componentes consecutivos. Para copiar o triplo ao completar seria necessário preservar os três intervalos. Com alinhamento de 4096 B e desvio de até 4095 B, cada componente de 4 406 400 B cabe num subbuffer alinhado de 4 411 392 B. Os três ocupam 13 234 176 B, dentro dos 16 777 216 B existentes por worker. A viabilidade depende de validar o alinhamento real, os bytes nas extremidades e a vida dos subbuffers até à cópia. O saldo histórico de E20 era de 5 004 288 000 B. As 378 entradas gastam 4 996 857 600 B, deixando 7 430 400 B para metadados, alinhamento e variação. Esta capacidade é otimista. [Contabilidade e fonte C294 autenticada](screen.py) · [Envelope de memória](../warm_residency/README.md)

**Condição de reabertura.** Uma nova regra definida antes do replay tem de identificar as chaves a reter com informação causal e passar os três critérios no mesmo K, contra os mesmos controlos. Seguir-se-ia a prova de exatidão dos bytes, duração das cópias e residência sob o cap. O teto de hits dá a margem disponível para essa regra. A transferência para a conversa natural e o tempo até ao primeiro conteúdo exigiriam medições próprias.

## Reprodução e falha preservada

Usar uma checkout limpa do candidato confirmado e os raws C294 originais. O diretório de saída deve ser novo.

```sh
python3 -B research/qualification-retake/l2_read_admission/screen.py \
  --raw-dir "$TESY_C294_RAW" --new-output-dir "$DESTINO_NOVO"
```

A tentativa r01 terminou no preflight de Git antes de ler os raws. O Git falhou a criação de uma thread para lstat sob o limite do processo. A execução seguinte preservou o limite e consultou Git sem preload paralelo do índice, com uma só thread. O recibo inclui o commit, a árvore e a verificação de checkout limpa. [Falha r01](evidence/controller-failure.json)

As reproduções r02 e r03 partiram do commit `c13204f7230753c8100a1bad631611320617aaac`, árvore `6448970b3a843d3b7dead7d263ae07c0ef791a45`. Os recibos completos coincidem byte a byte, SHA-256 `9aaa85ad2507d3f67803b51876271ecbc2de33fbab44f26f98afbd54aea40956`. A r02 consumiu 1,17 s e 47 956 KiB de RSS máxima. A r03 consumiu 1,15 s e 47 712 KiB. Ambas correram em CPU, sem pesos, GPU ou pedidos ao modelo. [Recibo r02](evidence/receipt.json)
