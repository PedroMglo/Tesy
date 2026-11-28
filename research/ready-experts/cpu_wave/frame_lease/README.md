# Quando é seguro reutilizar os pesos de uma camada CPU?

**MEDIDO no portátil. GO para libertar o frame depois de terminar a projeção `down`. INCONCLUSIVE para o ganho de tempo da camada.** O GGML existente executou duas tiles reais de CPU0 do GPT-OSS-120B. Nas quatro formas seguras de entregar o mesmo expert, os 84 resultados intermédios por tile e os 92 160 valores F32 da saída coincidiram bit a bit. O router completo e a saída FFN também coincidiram com uma execução monolítica independente. Um produtor que terminou a substituição depois da ativação e antes de `down` alterou os 92 160 valores da primeira tile e 2 880 da segunda. A primeira divergência em ambas apareceu na leitura prevista dos pesos. [Protocolo anterior à medição](protocol.md) · [Comparação numérica e todos os pares](evidence-20261128-r01/decision.json)

Usámos as mesmas oito waves do target, top-4, IDs de parking, biases, máscaras, SwiGLU e ordem de redução. A primeira entrada calcula o router das 153 posições e usa as posições 32–63 no FFN, com cinco experts distintos e uma wave ativa. A segunda tem 32 posições, 66 experts distintos e quatro waves ativas. Quatro produtores têm substituições prontas em RAM. Um precisa do frame da primeira wave e três usam frames independentes. Os três publicaram antes da última leitura forçada em todos os ensaios numéricos. Os dois testes de preço desligaram a recolha de tensores e a espera artificial. [Ensaio de cinco experts](evidence-20261128-r01/exact-five.json) · [Ensaio de 66 experts](evidence-20261128-r01/exact-many.json)

| Tempo da submissão até drenar grafo e produtores, mediana em ms | Cinco, ordem direta | Cinco, inversa | 66, direta | 66, inversa |
|---|---:|---:|---:|---:|
| COPY40 · três cópias, 40 IDs de matriz | 18,290 | 18,208 | 62,076 | 61,710 |
| COPY1252 · mesmas cópias, 1 252 IDs | 18,280 | 18,428 | 61,871 | 61,198 |
| DRAIN · ID físico até ao fim do grafo | 19,473 | 18,683 | 61,104 | 61,239 |
| LAST · ID físico até ao fim de down | 18,456 | 18,470 | 61,220 | 60,863 |
| Poupança emparelhada de LAST sobre COPY40 | +0,051 | −0,262 | +0,857 | +0,751 |
| Pares favoráveis a LAST sobre COPY40, de sete | 4 | 3 | 5 | 4 |
| Poupança emparelhada de LAST sobre COPY1252 | +0,350 | −0,193 | +0,328 | +0,394 |
| Poupança emparelhada de LAST sobre DRAIN | +0,763 | +0,631 | −0,115 | +0,418 |

As últimas linhas usam a mediana das diferenças dentro do mesmo bloco. Foram 112 submissões de preço graduadas e oito aquecimentos. O candidato evitou três cópias, 13 219 200 B de um hit, em cada submissão. Os quatro produtores escreveram os mesmos 52 887 552 B de frames com padding. O buffer do escalonador GGML foi de 6 268 416 B nos quatro braços. Os 1 252 frames virtualmente endereçáveis têm a mesma capacidade em todos os braços. Só o subconjunto inicializado ocupa memória física nesta fixture.

Com 66 experts, manter o frame até ao fim do grafo reteve o produtor durante 60,275 e 60,512 ms nas duas ordens. Libertá-lo depois de down reduziu a espera para 8,107 e 7,767 ms. Com cinco experts, passou de 18,825 e 17,936 ms para 15,077 e 14,700 ms. Apenas um dos quatro produtores teve de esperar. A diferença entre tempo do produtor e fim da camada impede multiplicar a espera pelo número de hits de uma conversa. A margem de 97,448 ms em P106 exige ainda os créditos do observador e da contenção no NVMe. [Tempos individuais com cinco experts](evidence-20261128-r01/price-five.json) · [Tempos com 66](evidence-20261128-r01/price-many.json) · [Orçamento para o pedido](../../verifier_wait/forecast/retention/eviction/late_owner/contention/sampling/tiers-result.md)

**Recursos.** O scope físico, incluindo a janela de admissão C118, demorou 71,170 s. O pico foi 2 850 643 968 B, com zero swap. As máximas amostradas foram 74,875 °C na CPU, 47,28 °C na RTX e 37,85 °C no NVMe. As leituras pedidas ao pack original totalizaram 4 112 007 168 B incluindo os controlos. A GPU forneceu telemetria. Houve zero forwards completos e zero pedidos HTTP. Energia desconhecida. O arquivo privado tem 56 ficheiros, 3 067 480 B. [Comandos, commits e hashes](evidence-20261128-r01/provenance.json) · [Cgroup e sensores](evidence-20261128-r01/physical.json) · [Manifesto do arquivo](evidence-20261128-r01/archive.json)

A experiência demonstrou uma fronteira segura no backend existente. Para decidir sobre um executor novo, é preciso identificar no pedido real que consumidor ainda usa o frame quando chega uma substituição, e se esse conflito atrasa o primeiro conteúdo final. A melhor conversa nominal medida continua em 17,689 s e 5,357 tok/s. R0 slots40-persistent, M3 PARTIAL e M4 NOT_MET.

```sh
D=research/ready-experts/cpu_wave/frame_lease
python3 -IB "$D/run.py" check "$D/evidence-20261128-r01"
```
