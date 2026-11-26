# Três vistas de atenção recuperaram todos os F32 seriais da camada 25

**GO para a integração em L25.** Na RTX 4060, um único grafo com as três queries, o KV de 192 posições já atualizado e três operações de atenção de largura um reproduziu as 12 288 palavras F32 da execução serial do 120B. O bloco não dividido reproduziu as 12 288 palavras diferentes observadas no percurso B3 do modelo completo. Ficou isolado um efeito causal da geometria da atenção neste operador e nestes dados. O ganho de tempo no pedido e a exatidão do resto do grafo continuam em aberto. [Resultado por posição](result.json) · [Pré-registo](protocol.md)

| Braço da fixture | Comparador do modelo completo | F32 diferentes em 189 / 190 / 191 |
|---|---|---:|
| Três grafos seriais com KV progressivo | AR | 0 / 0 / 0 |
| Grafo de três posições, KV partilhado | B3 | 0 / 0 / 0 |
| Mesmo bloco com três vistas de atenção e CONCAT | AR | 0 / 0 / 0 |
| Cauda mascarada preenchida com outros valores, B e S | B3 e AR respetivamente | 0 / 0 / 0 |
| Todas as células mascaradas, sinks preservados | B3 | 4 096 / 4 096 / 4 096 |

O último braço produziu 12 288 zeros finitos. Os 192 pares K/V de L25, com 512 F16 por componente, coincidiram integralmente nos dois snapshots. As 189 posições antigas conservaram os bytes. As seis linhas novas coincidiram com a conversão dos K/V F32 observados ao F16 do KV. A fixture recebeu a Q pós-RoPE, a máscara causal e os sinks reais. A preparação leu 256 B do GGUF no NVMe em cada identidade. O operador usou dados já extraídos. Nenhum forward do 120B nem pedido HTTP. [Reconstrução](operands.py) · [Grafo CUDA](fixture.cpp)

A primeira identidade parou antes do cálculo ao comparar o dispositivo de `stat` com o do mapeamento Btrfs. A segunda autenticou as bibliotecas pela técnica de mapeamento passivo já usada no Tesy. Os dois builds produziram o mesmo ELF e operandos. O scope Python da segunda execução mediu 1,475 s e 208 633 856 B de pico de cgroup, com swap zero. A ocupação total da GPU observada nos dois pontos foi 102 e 112 MiB. A janela curta e a amostragem não identificam energia por operação. Os originais e a cópia privada deram o mesmo recibo de revisão `bb6e6311420c3eae649cc6dcb8a86f39972994135f98b33dc4b02d939155a639`. [Arquivo dos dois builds e das duas execuções](../../../../../../../../../private_archive/part-166.json) · [Revisor sem GPU e sem modelo](review.py)

A literatura de atenção invariante ao batch descreve a necessidade de preservar a ordem de redução quando muda a largura. O resultado específico do Tesy é a reprodução nas duas direções com os operandos e as saídas da máquina alvo. Uma intervenção no grafo deverá pagar as três chamadas e a recomposição, conservar o estado e comparar todos os logits. M3 PARTIAL e M4 NOT_MET. [Antecedente dos autores](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) · [Referências obtidas no modelo](../README.md)
