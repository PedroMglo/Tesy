# Que parte do serviço merece uma fronteira diferente?

**NO_GO para financiar um backend integral neste perfil. A extensão a testar primeiro é a entrega direta dos hits CPU dentro do backend atual.** A composição com os SET atuais excede o prazo em P106 por pelo menos 22,135 ms, mesmo depois de conceder todo o observador e de oferecer a captura dos pesos. A entrega ideal só à CPU deixa mais margem que a entrega ideal só à RTX. Todos os modos excedem os 10 s integrais em P106. O melhor pedido HTTP medido continua em **17,689 s e 5,357 tok/s**. M3 PARTIAL e M4 NOT_MET. [Protocolo das ablações](tiers-protocol.md) · [Cortes inteiros e relógios por cenário](evidence-tiers-20261128-r01/tiers.json)

| SET dispensados nos hits | Piso de primeiro final integral P97 / P106, s | Piso de P106 com crédito máximo, s | Margem de P106 com crédito, ms | Decode P97 / P106 para 47 IDs, s |
|---|---:|---:|---:|---:|
| Nenhum | 9,670 / 10,669 | **10,022** | **−22,135** | 6,279 / 6,544 |
| Só CPU | 9,561 / 10,549 | 9,903 | **+97,448** | 6,204 / 6,460 |
| Só CUDA | 9,603 / 10,600 | 9,954 | +46,450 | 6,229 / 6,493 |
| CPU e CUDA | 9,494 / 10,480 | 9,834 | +166,034 | 6,154 / 6,409 |

Estes pisos assumem as taxas mais favoráveis medidas, latência gratuita nas adjacências treinadas, 674 hits causais, custo zero para 26,055 GB de capturas e a geometria original em duas tiles simultâneas. A coluna de crédito remove mais 646,428 ms em P106. Retirar ambos os SET muda o limite creditado de P106 em 188,169 ms; as duas melhorias isoladas somam 188,854 ms. A diferença de 0,685 ms resulta da recomposição do caminho crítico. Os valores exatos da tabela permitem comparar a composição no mesmo relógio. A medição física de uma conversa permanece anterior.

A camada decide a rota original. Das promoções, 469 terminam na CPU e 205 na RTX. Os três SET dos acertos CPU consumiram 382,882 / 410,436 ms em tempo somado dos workers. Os SET CUDA consumiram 282,064 / 295,719 ms. No perfil CPU direto, a margem creditada de **97,448 ms** é o máximo para toda a espera adicional no caminho crítico, incluindo posse, capturas, coordenação, interferência e cleanup. Sem o crédito ainda faltam **548,980 ms** no mesmo processo. A ordem não preemptível testada atrasa 345 gerações CPU/CUDA no prazo creditado de P106, mesmo oferecendo os SET dos hits CPU. O fluxo fracionário admite outra ordem, cuja existência e paridade continuam por demonstrar.

**Fronteira de engenharia.** O operador CPU existente já leu três matrizes MXFP4 em posições regulares de um pool usando `ggml_mul_mat_id`. O ensaio anterior do 120B promoveu pesos de um banco RAM mantendo as três cópias. Uma ligação por frame físico pode estender a primeira interface para a segunda situação. Antes de qualquer novo pedido, importa saber se a promoção e a captura da vítima conservam chaves, gerações e capacidade ao trocar o proprietário do frame. A RTX conserva o caminho habitual. [Operador original no GGML](../../../../../../../cpu_wave/supplied/slot_layout.cpp) · [Oito braços físicos com capturas e cópias](../../README.md)

A ablação correu em 24,87 s com 285 064 KiB de pico de RSS, sem GPU nem forwards. A aquisição física das taxas usou 4 032 ensaios do pack 120B no NVMe interno, 126 930 124 800 B pedidos e 36 360 verificações de matrizes. Um dos oito grupos de pesos falhou uma das suas quatro calibrações. A avaliação conservou o intervalo desconhecido dessa população. [Medições com duas e quatro leituras](README.md) · [Medições com três](three-result.md) · [Comandos e material reproduzível](evidence-tiers-20261128-r01/provenance.json)

```sh
S=research/ready-experts/verifier_wait/forecast/retention/eviction/late_owner/contention/sampling
python3 -IB "$S/tiers.py" --check "$S/evidence-tiers-20261128-r01/tiers.json"
```
