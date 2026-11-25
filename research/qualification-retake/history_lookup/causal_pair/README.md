# Cópia de dois tokens da história nominal

**Triagem de investimento: manter fechados os verificadores B2/K1 e a cópia B8 com a economia histórica; adiar B3/K2 até haver dados do turno natural.** Em C281, 47 saídas constam do usage do target e a chamada terminou naturalmente. A gravação SSE (81 fragmentos) forneceu um só campo `tokens`, vazio. O resultado reutilizável do cliente indica `NOT_EXPOSED_EMPTY_OR_ABSENT`. O controlo C242 executou greedy nativo C75/P12 e terminou em EOG após 39 IDs. Dos 2 197 IDs de entrada, as posições 33 e 35, de base zero, diferem de C281. Ambas as contagens provêm dos ficheiros originais autenticados. A aceitação de cópia nos 47 de C281 é desconhecida.

No C269, `common/ngram-map.cpp:49` procura para trás a ocorrência anterior mais recente do sufixo de N IDs; ignora a posição zero e limita a cópia aos M IDs disponíveis antes do último token já sorteado. Está congelado N=2/M=2 para propor dois tokens. N=1/M=1 é a outra interpretação habitual de um batch de duas posições, constituído pela âncora e uma proposta. Sem afinação nem escolha do resultado mais favorável. A função de proposta recebe só o histórico anterior. O avaliador confronta cada proposta com os IDs posteriormente confirmados, conserva só o prefixo exato e permite um corretivo/bonus do target. Uma chamada que encontra o limite/EOG pode não emitir esse bonus. No C242, o primeiro ID já sai do prefill; a geração de referência guarda o ID EOG antes de terminar, em `tools/block_native_run.cpp:195–198`. O denominador até à conclusão contém 38 IDs pós-âncora, incluindo EOG; os primeiros 32 constituem uma segunda janela, idêntica à usada por C247.

| C242 nominal diagnóstico | Janela | AR / verificações com proposta | IDs propostos aceites / apresentados | Propostas completas | Chamadas poupadas |
|---|---:|---:|---:|---:|---:|
| N2/M2 | 32 | 21 / 6 | 6 / 12 | 2 / 6 | 5 / 32 |
| N2/M2 | 38 até EOG | 21 / 8 | 9 / 16 | 4 / 8 | 9 / 38 |
| N1/M1 | 32 | 14 / 12 | 7 / 12 | 7 / 12 | 6 / 32 |
| N1/M1 | 38 até EOG | 14 / 15 | 9 / 15 | 9 / 15 | 9 / 38 |

A razão de custos que seria necessária para ganhar 15% nos 32 do par N2/M2 é `(0,85×32−21)/6 = 1,03333` chamadas AR por verificação B3. Usa 21 chamadas AR ordinárias e seis verificações pela mesma média unitária; é favorável ao conceder pesquisa, rejeição, cópia de logits, rollback e coordenação gratuitos. Nos 38 até EOG, o mesmo cálculo dá `(0,85×38−21)/8 = 1,4125`. O custo real das três posições nunca foi observado aqui. As chamadas poupadas são uma contagem, não um ganho de parede. O C245 fechou B2/K1 mesmo com proposta perfeita em código/rota (ganhos medianos de 6,11% e 4,55%); C246 de quatro posições falhou o mesmo gate em ambos. C247 e a unidade `history_lookup` fechada em B8 mediram outra geometria. As diferenças de aritmética entre B2 e AR incluíram uma divergência de argmax no código.

O C281 natural precisaria de reduzir o decode em 24,61% para 6 tok/s; a subtração de todo esse decode deixaria 11,052 s até ao primeiro final, com o restante fixo. O próximo dado económico vem de uma próxima conversa R0 já admitida que grave a sequência exata dos IDs emitidos no sampler no mesmo turno, ligue o evento de EOG à convenção do usage, preserve timing e valide o split 2044+153. Uma eventual margem ainda exigiria exatidão de B3, preços emparelhados de AR e B3 com rejeição, KV e materialização, e uma intervenção no prefill para o alvo de 10 s. Esta análise não efetuou novo forward nem alterou o launcher.

```sh
python3 -B screen.py --repo "$TESY_CHECKOUT" --lab "$C7" \
  --natural-root "$C281_E20" --new-output-dir "$NEW"
```

Os compactos publicáveis contêm contagens, estatísticas e nomes de classes. O pack/a biblioteca e qualquer informação textual do utilizador não são necessários para a execução. A leitura do source `common/ngram-map.cpp` verifica a identidade do algoritmo. Os originais C242/C281 são lidos no projeto sem os copiar.
