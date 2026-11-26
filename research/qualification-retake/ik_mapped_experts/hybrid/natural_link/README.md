# Payload do banco LRU do ik para o pedido natural de 153 tokens

**As 33 linhas adicionais do banco eliminam 1 767 transferências de experts
durante o decode, equivalentes a 23,358 GB de pesos.** A conta aplica o planner
LRU do pin ik às rotas reais do Tesy com todas as 36 camadas no mesmo grupo
GPU, sem antecipação e com share CPU zero. O custo adicional de payload
residente é de 436 233 600 B. O alvo de dez segundos até à primeira peça final
continua a exigir pelo menos **11,013 GB/s** com 161 slots. O teto bruto de
16 GB/s admite esse valor. A decisão é **INCONCLUSIVE para a latência do
produto**. A próxima comparação requer a taxa útil com a fonte mapeada, os
bytes enviados pelo hook e os custos reais de cálculo e sincronização do ik.
[Recibo compacto](result.json) · [Protocolo](protocol.md)

| Recorte do pedido T2 | Fills com 128 slots | Fills com 161 slots |
|---|---:|---:|
| Primeira chamada, 5 posições | 331–459 | 298–459 |
| Segunda chamada, 32+32+32+32+20 | 674+350+567+594+1182 | 674+350+567+594+1182 |
| Prefill 5+148 | 3 698–3 826 | 3 665–3 826 |
| Primeiro decode, 144 procuras únicas | 144 | 139 |
| Decode até à primeira peça final, 44 avaliações | 6 336 | 4 666 |
| Desde a entrada até gerar essa peça | 10 034–10 162 | 8 331–8 492 |
| Decode completo, 46 avaliações | 6 624 | 4 857 |

Cada fill envia três matrizes de 4 406 400 B. Na chamada de 148 posições,
as 3 367 procuras únicas por camada/tile produzem zero hits nos dois bancos.
No decode, 161 slots obtêm 1 767 hits em 6 624 procuras; o banco de 128 obtém
zero. O melhor solver com substituição offline e entrada livre no próprio
recorte do decode precisaria, respetivamente, de pelo menos 3 446 e 3 733
fills. A diferença em relação ao LRU mostra o custo de usar esta política em
vez da escolha com conhecimento do futuro. A análise anterior de 161 slots
usou 32 passos fornecidos na C294, enquanto a conta de páginas da sessão natural
estudou a cobertura do GGUF em host. [Piso C294](../../../stock_link/README.md) · [Páginas por tile](../../natural_pages/README.md)

| Slots reais | Pesos até à peça final | Taxa útil necessária em 10 s | Mínimo só no link a 16 GB/s | Pesos de decode | Taxa útil para 47 saídas a 6 tok/s | Mínimo só no link |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 132,641–134,334 GB | 13,264–13,433 GB/s | 8,290–8,396 s | 87,564 GB | 11,178 GB/s | 5,473 s |
| 161 | 110,129–112,257 GB | 11,013–11,226 GB/s | 6,883–7,016 s | 64,206 GB | 8,196 GB/s | 4,013 s |

GB é decimal. No cenário mais favorável de 161 slots, a folga para trabalho
serial adicional é no máximo 3,117 s antes da peça e 3,820 s no decode. Parte
dos dois recortes é comum. A primeira peça chega ao cliente depois da call 46,
que produz a amostra 45. A última amostra (47) vem da call 48; o terminal HTTP
tem carimbo do cliente, e o instante interno de sampling continua sem carimbo
de cliente individual. O limite até à primeira peça cobra apenas o percurso
causal até à amostra 45. O objetivo de 6 tok/s admite 47/6 s de decode. A
taxa máxima de 16 GB/s vem da capacidade 16 GT/s × 8 do endpoint e da ponte
PCIe, antes de encoding, protocolo e contenção. Estes são bytes solicitados
a H2D; o estado da cache de páginas, os bytes lidos do SSD, o custo de
transferências extra e a capacidade para todos os buffers permanecem por
medir no modelo híbrido.

## Como se elimina a incógnita do estado inicial

A entrada pode conter até K quaisquer chaves (camada, expert). Os 1 440
bindings no primário R0 serviram para autenticar a captura e não inicializam
esse banco. Cada lookup preserva todos os ranks na ordem por posição. O ik
toca os hits únicos pela ordem da primeira ocorrência e só depois insere as
faltas em ordem crescente de ID. O verificador confrontou a lista lógica
completa de recência e os hits, fills e expulsões do header nativo com uma
implementação independente em todas as 1 867 procuras por grupo. As cinco
podas da camada final mantêm os 7 012 quartetos e 28 048 ranks das partes
97 e 106. [Planner ik pinado](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache-policy.h#L221-L268) · [Hook dos três SET](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/llama-moe-cache.cpp#L766-L790)

Uma chave que não foi tocada desde K outras chaves distintas é forçosamente
ausente. A partir de K inserções seguidas e obrigatórias, fica determinada
a lista completa de chaves ordenadas por recência mesmo que os números dos
slots físicos difiram. A prova já fecha na primeira chamada de cinco posições,
ao fim da camada 19 para 128 slots e da camada 24 para 161 (camadas desde
zero). Antes desse ponto cada hit incerto só pode provir de uma chave inicial
ainda inédita. O limite é K. O banco vazio atinge o máximo de fills e um
banco hipotético com as primeiras K procuras distintas atinge o mínimo.
Esse último estado usa o futuro para construir a testemunha do limite. O
estado de uma sessão ik real tem de vir da sua própria história.

O contrato e o código foram congelados em `fe25d0fe` e `d9fdf4ae`. Duas
reaberturas, uma pelos originais e outra pelos arquivos das partes 97 e 106,
produziram o mesmo recibo de SHA
`327727018b62f5dfb0f347c6b2d9bfe76ef06e853e53997d48c84d20a56cb1c0`.
O recibo completo tem uma linha por tile e capacidade; o compacto contém as
seis tiles e os 46 fills de decode em ordem por capacidade. Três testes
conferem a ordem da política e a prova de convergência em todas as permutações
possíveis de até três slots para uma fixture de sete chaves. A execução
abriu apenas journals e metadados. A fixture ligou apenas a biblioteca GGML
do build CPU anterior. [Teste de controlo](test_score.py) · [Verificador](score.py)

A partir desta pasta, com o Python do projeto (NumPy já presente para
cache_bound), usar diretórios de saída novos para build e reanálise. Os
argumentos P97/P106 apontam às famílias naturais e C283 ao
`model-tensor-metadata.jsonl` original. O recibo do build desta execução tem
SHA `59a7f3fac39ed7fa400d0dd400798651de0d4851c330d644ff7225d441939c64`.

```sh
python3 -IB -m unittest discover -s .
python3 -IB score.py build --ik "$IK" --lib "$CPU_GGML" --new-output "$BUILD"
python3 -IB score.py study --p97 "$P97" --p106 "$P106" --inventory "$C283" \
  --build-dir "$BUILD" --build-sha256 "$BUILD_SHA" --new-output "$NEW_DIR"
```
