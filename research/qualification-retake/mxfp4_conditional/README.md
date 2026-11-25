# Quanto informa a escala sobre os nibbles do mesmo bloco MXFP4?

**NO_GO para o rANS de dois estados condicionado à escala do próprio bloco na amostra C287.** O teto de poupança é **9,765%** nos 846 028 800 bytes de pesos e **14,545%** na matriz mais favorável. Mesmo atribuindo a todos os experts frios o resultado da melhor matriz, o mecanismo fica aquém do corte de investimento de 20%. Em 192 matrizes, **zero** passam esse corte. [Pré-registo](protocol.md) · [Recibo](evidence/receipt.json) · [Resultados por matriz](evidence/components.json)

## Ganho de informação e bytes

**MEDIDO** nos bytes originais de 64 experts do GPT-OSS-120B. O contador identifica cada escala E8M0 e os 32 nibbles E2M1 do mesmo bloco. Os totais por escala e por nibble reproduzem separadamente as duas margens de C319 em cada matriz. A informação mútua empírica, somada pelas 192 matrizes e expressa com arredondamento dirigido, fica entre **78 547 454 e 78 547 648 bits**, cerca de **0,049323 bit por nibble**. O valor zero representaria independência. Para elevar o teto marginal de 8,605% a 20% no conjunto, a dependência teria de fornecer cerca de 0,484 bit adicional por nibble. [Contador nativo](hist.cpp) · [Controlo marginal](../mxfp4_entropy/README.md)

**FORMAL** para a família de dois estados rANS pré-registada. Um estado usa a distribuição das escalas. O segundo escolhe uma tabela de nibbles por escala, mantendo o estado entre símbolos. Na prova, cada tabela recebe gratuitamente as melhores frequências para a sua matriz. O limite soma a informação condicional por contexto, aplica a folga finita por símbolo e cobra uma única vez cada par de extremos do estado. O piso da amostra é de **6 107 300 962 bits emitidos**, contra 6 185 848 520 no piso marginal e 6 768 230 400 bits crus. A diferença entre os tetos de poupança é de **1,161 pontos percentuais**. O ganho efetivo de um encoder com tabelas, padding, descompressão e cópia ficou por medir. [Prova das transições e dos arredondamentos](../mxfp4_entropy/prova.md) · [Verificador condicional](screen.py)

Cada camada inclui 24 matrizes, provenientes de oito experts com três componentes. As percentagens de cada conjunto usam os respetivos bytes crus como denominador. A informação mútua usa o número de nibbles do mesmo conjunto.

| Tier ou camada | Teto marginal | Teto condicionado | Acréscimo (p.p.) | Melhor matriz condicionada | Informação mútua (bit/nibble) |
|---|---:|---:|---:|---:|---:|
| **Todos** | 8,605% | **9,765%** | 1,161 | 14,545% | 0,04932 |
| **CPU** | 8,714% | **9,793%** | 1,079 | 14,545% | 0,04587 |
| CPU 0 | 9,872% | 10,993% | 1,122 | 14,545% | 0,04767 |
| CPU 8 | 8,304% | 9,277% | 0,973 | 10,056% | 0,04135 |
| CPU 16 | 8,287% | 9,493% | 1,206 | 10,661% | 0,05124 |
| CPU 24 | 8,391% | 9,408% | 1,017 | 9,844% | 0,04323 |
| **CUDA** | 8,496% | **9,737%** | 1,242 | 12,292% | 0,05277 |
| CUDA 25 | 8,386% | 9,573% | 1,188 | 10,640% | 0,05047 |
| CUDA 29 | 8,411% | 9,672% | 1,261 | 10,876% | 0,05361 |
| CUDA 32 | 8,457% | 9,664% | 1,207 | 10,909% | 0,05130 |
| CUDA 35 | 8,730% | 10,040% | 1,311 | 12,292% | 0,05571 |

A melhor matriz é `blk.0.ffn_up_exps.weight` do expert 102. O teto de 14,545% ainda está 5,455 pontos percentuais abaixo do corte. A passagem de 4,52326 a 6 tok/s no pedido nominal medido exigiria cortar 24,612% do tempo por passo. A comparação com esses 24,612% pressupõe que todo o tempo varie proporcionalmente aos bytes. A latência real do decode e os 10 s até ao primeiro conteúdo final exigem relógios integrados da conversa. [Medição natural no NVMe](../nvme_conversation/README.md)

## Âmbito e condição de reabertura

Os limites cobrem esta população e este contexto estatístico específico. O mix de experts de outro pedido pode incluir matrizes fora da amostra. Codificadores que explorem a sequência dos nibbles, a estrutura entre linhas ou outra informação lateral têm distribuições diferentes a medir. Uma reabertura exige identificar essa informação, congelar o codec e testar se há margem com os mesmos denominadores. Um resultado favorável abriria uma fixture de serviço com reconstrução bitwise, encaminhamento autoritativo, acessos aleatórios, custo das tabelas e cópias e o tempo até à última publicação. [Antecedentes e diferenças testáveis](literatura.md)

## Reprodução

O protocolo ficou congelado em `9060622b`. As duas confirmações usaram a revisão limpa `09333588bceb61dcab3d9425569784f515abc01d`, árvore `c220ad5d9fe77a15a3c2355d4d3cc4428288ee86`. Cada processo leu o pack sequencialmente uma vez, 848 560 128 B. Verificou o SHA-256 integral e os 384 componentes, incluindo os 192 biases residentes excluídos da conta de pesos. R01 consumiu 5,24 s e 78 216 KiB de RSS máxima. R02 consumiu 3,41 s e 78 580 KiB. Esses relógios incluem a auditoria. Houve zero forwards e zero uso de GPU. Os sete testes sintéticos e o Ruff passaram. [Fixtures e controlos negativos](test_screen.py)

Na checkout limpa, usar o arquivo local C7 e escolher um diretório de saída novo por execução.

```sh
python3 -B research/qualification-retake/mxfp4_conditional/screen.py \
  --results-root "$C7/results" \
  --sample-pack "$C7/results/c283-exact-expert-service-epoch-20261006T194311Z/pack/sample64-v1.bin" \
  --new-output-dir "$NEW_OUTPUT"
```

Os dois processos produziram ficheiros idênticos. O recibo de 8 480 B tem SHA-256 `a7d0a1fc4c2bcf60af568457f8f10be7c71780fa8d2d61bd006c61b3abfba76b`. Os resultados por componente de 119 205 B têm SHA-256 `cc8b5a516c6d0db6f82729699746f81dbbc9669dd8e5b3caf233f9565031555d`. Pesos e histogramas conjuntos ficam privados. [Recibo e identidades das fontes](evidence/receipt.json) · [Componentes, tetos e digests](evidence/components.json)
