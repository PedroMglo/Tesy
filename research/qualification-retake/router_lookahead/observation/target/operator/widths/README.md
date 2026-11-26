# Router CPU com 5 e 20 linhas

O router GGML que o C291 carrega reproduziu bit a bit os logits, os quatro IDs ordenados e a mistura de **1 600 linhas de controlo** nas duas tiles de largura 32 da C270. Reexecutar o grafo nas janelas de 5 e 20 linhas também conservou todos esses bits, incluindo os scores após bias, em relação às mesmas posições no grafo de 32. O controlo incluiu as 25 camadas CPU. [Protocolo](protocol.md) · [Grafo reutilizado](../../../../../history_lookup/b3_numeric/first_boundary/router_row/fixture.cpp)

| Largura | Linhas +0, quartetos exatos nos dois produtores | Recall +1 por expert | Escalar +1, ms/sítio | BLAS +1, ms/sítio (p10–p90) |
|---|---:|---:|---:|---:|
| 5 | 250/250 | 757/960 (78,85%) | 1,0801 | 0,1047 (0,1041–0,1053) |
| 20 | 1 000/1 000 | 3 030/3 840 (78,91%) | 4,3169 | 0,2150 (0,2140–0,2159) |

Os dois produtores também devolveram, em ordem, os mesmos quatro IDs +1 que a previsão autoconsistente de largura 32 e as mesmas ofertas após o filtro de ocupação. O recall mede quantos desses IDs pertencem aos quatro experts efetivamente escolhidos pela camada seguinte. A geometria +1 cobre 24 destinos por tile e largura. As duas tiles fornecem **48 sítios e 384 pares por largura**. Os tempos são medianas entre sítios, após a mediana de oito repetições por modo, e incluem a normalização, projeção, top-4 e seleção de ofertas. [Operador cronometrado](../operator.cpp) · [Recibo](receipt.json)

**Precisão dos valores.** A igualdade dos IDs convive com diferenças de acumulação. Para 5 e 20 linhas, os máximos absolutos dos scores BLAS com bias foram 2,86×10⁻⁶ e 1,91×10⁻⁶, com 28 440/32 000 e 112 905/128 000 palavras F32 diferentes do nativo. Os máximos da mistura reconstruída foram 3,58×10⁻⁷ e 2,98×10⁻⁷. No escalar, o maior erro de score foi 1,38×10⁻⁵ e o de mistura foi 2,24×10⁻⁶. Os limites prévios eram 10⁻⁴ e 10⁻⁵. O comparador detetou a troca deliberada de duas posições do controlo. [Verificador](run.py)

**Âmbito.** Os dados são ativações C270 nas posições 0–31 e 128–159. Em cada tile, o grafo de 5 consumiu as primeiras cinco linhas; o de 20 consumiu as últimas vinte. Isto qualifica o projetor residente CPU para essas formas e esses dados. As rotas, a chegada da ativação e o tempo de entrega na conversa natural de dois turnos continuam por observar na implementação candidata. O oráculo usou oito threads e os dois providers GGML do servidor C291; a projeção cronometrada usou uma única thread, CPU lógica 0, com o mesmo ELF da [medição de 29/32](../README.md). O scope fechou sem swap, pico de 240 132 096 B, 7,68 s para o processo. Zero bytes de GGUF e zero forwards do modelo.

## Reprodução

Protocolo `6b716f7b`, execução na checkout limpa `879ca1d1510c9bee0e91e70a362058b65996ab8f`. Usar o comando e os mesmos recursos da [fixture residente](../README.md#reprodução), trocar o programa por `widths/run.py`, indicar `--closure /tmp/tesy-c281-pack-link-20261125-r01/receipt.json` e escolher uma nova identidade e diretório. A reabertura independente das 768 duplas conferiu as distribuições de ambas as implementações. SHA-256 do recibo privado `bf436d337ff3beed3c235c13d4abea55ed96f1d83b65df06217d7a0e86244c57`, em `/tmp/tesy-router-widths-20261125-r01/receipt.json`.
