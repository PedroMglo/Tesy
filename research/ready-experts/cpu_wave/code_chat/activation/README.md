# Basta corrigir a ordem dos pesos no executor independente?

**NO_GO como substituto bit a bit do produto escalar CPU do R0.** O teste usa a matriz gate inteira da camada 0, expert 0, do GPT-OSS-120B original. São 2 880 linhas e 2 880 colunas. Na biblioteca de CPU do R0 autenticámos, em tempo de execução, que o tipo MXFP4 seleciona o produto com ativações Q8_0. O GEMV do motor C avaliado consome ativações F32. A primeira experiência já tinha corrigido a permutação das coordenadas dos pesos. [Teste anterior](../executor.md) · [Fonte do motor independente](https://github.com/FiveTechSoft/gpt-oss-120b/blob/9570410cab7e34bf7ac044559fc56dcdf4c7c195/engine/src/dequant.c)

Construímos duas ativações que diferem apenas numa coordenada, +1/256 e −1/256. O R0 converteu as duas para **os mesmos bytes Q8_0** e produziu os mesmos 2 880 resultados. Com a ordem dos pesos já corrigida, o executor independente distinguiu as ativações em **2 170 saídas**. Uma referência separada que descodifica os dois pesos de cada linha confirmou os produtos F32. O contraexemplo reproduziu-se nas bibliotecas escalar e AVX2, em dois processos independentes.

| Entrada | Diferenças em 2 880 saídas com a ordem corrigida | Diferenças depois de aplicar também Q8_0 à ativação |
|---|---:|---:|
| Controlo representável | 0 | 0 |
| Perturbação positiva | 2 170 | 0 |
| Perturbação negativa | 2 170 | 0 |
| Vetor denso fixado antes do ensaio | 2 880 | 2 456 |

No vetor denso, o maior erro absoluto desceu de 0,00998819 para 0,000003338. O contrato congelado exige igualdade bit a bit. O ensaio deixa por identificar a causa única das diferenças residuais, a frequência destas ativações numa conversa e o efeito em logits, texto ou qualidade. A variante pode ser reaberta com uma implementação que reproduza o operador de referência ou com um novo contrato de paridade numérica justificado antes de medir. A alternativa de reutilizar o kernel numérico atual continua disponível num scheduler novo. [Protocolo](protocol.md) · [Resultados por entrada e por ELF](result.json)

Cada processo pediu 4 406 400 B ao ficheiro GGUF no NVMe interno e demorou 0,200 / 0,199 s. O maior pico do cgroup foi 40 144 896 B, com cap de 512 MiB e zero swap. Não houve forward de modelo nem utilização de GPU nesta prova. Os dois recibos científicos, incluindo os hashes das projeções, são idênticos. [Comandos](commands.json) · [Arquivo privado](archive.json)
