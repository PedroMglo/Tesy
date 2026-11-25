# Servir os pesos CPU diretamente no destino de leitura do operador

A comparação C293 qualifica o pack como fonte exata de bytes. Ficou aquém do critério de investimento. Cada falta CPU continuava a exigir três chamadas de cópia do staging para os tensores do GGML. A intervenção em avaliação muda o destino do único `pread` e a disposição dos mesmos 40 slots. O routing, a escolha da vítima e os bytes de cada matriz continuam a ser os do target. [Pré-registo](protocol.md) · [Pontos de integração e contraprovas](integration.md)

## Tempo que teria de sair do pedido

O verificador reproduziu os oito recibos nativos da C293, os pares, os contadores e o avaliador original. A coluna da direita responde a uma pergunta contrafactual: quantos segundos adicionais teriam de desaparecer de **cada** braço B para a mediana do ganho em prefill153+decode32 atingir 8%, se o outro caso conservasse as suas medições? O prefixo e a sua duração têm coluna própria no recibo. O avaliador volta a verificar os sinais dos pares e a proteção do outro caso aos dois lados do limiar. [Recibo por braço](distance-r1/receipt.json) · [Reprodução](gate_distance.py)

| Caso fornecido | Ganho do primeiro par A/B | Ganho do segundo par A/B | Redução adicional igual em cada B |
|---|---:|---:|---:|
| Nominal 153+32 | 7,0043% | 7,9408% | 0,101741 s |
| Código 153+32 | 5,2194% | 6,8769% | 0,524421 s |

Se a redução hipotética for proporcional à duração de cada B, os valores de equilíbrio são 0,57005% e 2,07753%. O ensaio C289 de 256 serviços CPU limita o tempo disponível na sua própria agenda. A fração das cópias que atrasava o pedido C293 permanece desconhecida. A resposta com texto livre e os seis tokens/s de M4 têm de ser medidos na receita qualificada. [Limite das cópias C289](../packed_service_bound/README.md) · [Contrato de produto](../protocol.md)

A reprodução das contas foi executada na árvore limpa do commit 1a9ff0d9d67603a78f8224b0b80c32b2de18e0f5. SHA-256 do recibo compacto cc57599e5e71e9e8958e6d1c7f2cf4c180985ab81bd79665af585cc801cbd4f4. O comando requer o raw autêntico C293 e um destino novo.

```sh
python3 -B research/qualification-retake/packed_cpu_views/gate_distance.py \
  --raw-dir "$TESY_C293_RAW" --new-output-dir "$TESY_C293_SAIDA_NOVA"
```

## Resultado do operador e da leitura direta

**GO para a próxima fixture de integração.** Duas execuções de cada gate confirmaram que o MUL_MAT_ID CPU consome as vistas com o stride proposto e que uma janela integral pode ser lida diretamente para o slot sintético no NVMe interno. Continua por demonstrar quanto tempo as cópias CPU acrescentam a prefill e decode com o 120B. Os relógios abaixo incluem a supervisão de cada fixture. [Protocolo](protocol.md) · [Precedências do teste de leitura curta](short_read.md)

| Ensaio | Resultado | Parede do supervisor | Pico do cgroup |
|---|---|---:|---:|
| GGML CPU R01 | 103 680 valores finitos, igualdade bit a bit | 1,082018 s | 211 243 008 B |
| GGML CPU R02 | Mesmo digest de saída e mesmas mutações | 0,872953 s | 158 814 208 B |
| I/O V1 build | PASS_BUILD | 0,973537 s | 191 565 824 B |
| I/O V1 R01 | FAIL_PRESERVED, `short_tail_guard` | 0,273061 s | 67 502 080 B |
| I/O V2 build | PASS_BUILD | 1,075217 s | 200 392 704 B |
| I/O V2 R01 | PASS_BTRFS_NVME_DIRECT_FIXTURE | 0,674358 s | 94 695 424 B |
| I/O V2 R02 | Mesmo SHA-256 do raw e do verificador | 0,671767 s | 93 892 608 B |

O operador usou GGML C269 `d0ebfbcc`, três posições, três projeções, top-k quatro e slots 0, 7, 23 e 39. Cada execução conferiu os 103 680 resultados contra a referência externa. O stride errado alterou 77 756 valores e a componente errada alterou 103 394. O executável e o vetor de saída tiveram o mesmo SHA-256 nas duas execuções. Os recibos nativos diferem apenas no máximo de RSS dos filhos. Os manifestos incluem tamanho e digest de cada recibo original e do respetivo supervisor. [MMID R01](receipts/mmid-r01.json) · [MMID R02](receipts/mmid-r02.json) · [Manifesto do operador, V1 e diagnóstico](receipts/manifest-v1.json)

Na V1, a leitura em EOF devolveu 13 217 792 B para um pedido de 13 221 888 B. A fixture exigia que a sentinela dos últimos 4096 B sobrevivesse dentro desse destino. O diagnóstico independente reabriu o mesmo inode para leitura O_DIRECT. Os 13 217 792 B devolvidos coincidiram integralmente com a referência. Os 4096 B seguintes passaram de `0xd3` a zero. As duas guardas exteriores conservaram todos os bytes. Uma leitura positiva no mesmo ficheiro, para um segundo destino ainda vivo, devolveu a janela integral e conservou os dados e as guardas durante a leitura curta. O diagnóstico também confirmou a conservação do inode, flags e tempos de acesso e modificação. [FAIL nativo preservado](receipts/dio-v1-r01.json) · [Diagnóstico no mesmo inode](receipts/diagnostic.json)

O kernel observado foi `7.3.4-200.fc44.x86_64`. Como antecedente verificável em fonte upstream, em Linux v6.12 o Btrfs entrega leituras diretas a iomap. Na conclusão, iomap limita o número de bytes comunicado ao espaço restante até EOF. Isso explica como distinguir o contador devolvido da extensão do destino reservado. A origem exata das escritas dos zeros no kernel Fedora permanece sem instrumentação. O diagnóstico durou 0,148694 s no processo. O cgroup registou 64 909 312 B de pico sob o teto de 268 435 456 B, swap zero e zero OOM. O `getrusage(RUSAGE_SELF)` registou 650 912 KiB, um máximo da vida do processo que pode atravessar `exec`. O limite foi aplicado e medido no cgroup da execução. [Btrfs v6.12](https://github.com/torvalds/linux/blob/v6.12/fs/btrfs/direct-io.c#L712-L719) · [Conclusão da leitura em iomap](https://github.com/torvalds/linux/blob/v6.12/fs/iomap/direct-io.c#L90-L99) · [RSS em exec](https://github.com/torvalds/linux/blob/v6.12/fs/exec.c#L949-L957) · [Linux getrusage](https://github.com/torvalds/linux/blob/v6.12/kernel/sys.c#L1733-L1741)

A V2, congelada em `8e8dbfd2`, recusou nova reivindicação do slot 4 imediatamente antes do syscall e após o retorno antes de o worker devolver a posse. A geração 1 ficou inválida. No mesmo endereço, a geração 2 publicou o expert 0 somente depois de ler os 13 221 888 B e confirmar de novo os três payloads e o padding. Em seis momentos conferiram-se todos os bytes dos vizinhos 3 e 5 e dos controlos vivos 0 e 39. O verificador detetou separadamente a mutação deliberada de uma guarda e a do último byte do vizinho 3. As duas execuções tiveram cinco publicações, seis rejeições e swap zero. A distribuição dos últimos 4096 B da geração falhada fica registada por observação. A integridade exigida é a dos vizinhos e da nova geração integralmente publicada. [Manifesto V2 e testemunho comum](receipts/manifest-v2.json) · [Resultado do verificador independente](receipts/dio-v2-verify.json)
