# Trinta e cinco recargas cabem nos próprios slots do controlo

Uma agenda offline consegue evitar **35 das 230 leituras repetidas** mantendo as 40 posições por camada. São 21 em CPU e 14 em CUDA. O controlo voltou a fazer as 1 212 leituras da chamada de 148; a intervenção requer 1 177. O retorno de 5 tokens conserva as suas 51 leituras. Os dados vêm dos dois journals nativos P97/P106. [Testemunho e certificado por posição](slot-result.json) · [Protocolo](slots-protocol.md)

Na entrada da wave que expulsaria o expert, a agenda guarda as três matrizes noutro slot da mesma camada. A geração que empresta o espaço já teve o último leitor, incluindo todos os destinos possíveis de parking. O novo pedido recupera as matrizes no slot reservado pelo controlo. Uma escrita integral da agenda original repõe o slot emprestado antes do retorno externo. A ablação e a intervenção verificaram as mesmas **7 497 posições de consumo** em 1 296 callbacks, e o mesmo conteúdo lógico e geração em cada um dos 1 440 slots no primeiro decode. A assinatura do estado de entrada coincide com a reconstrução independente do journal. O intérprete representa os bytes pela identidade dos pesos; o backend ainda precisa de verificar as transferências e a igualdade numérica. [Implementação](slots.py) · [Reconstrução dos destinos de parking no pin](../../../../../../../../../../../phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/replay/manager.py)

Das 230 recargas, 42 tinham pelo menos uma geração auxiliar elegível. As 157 alternativas deram um emparelhamento de 35, com uma cobertura de vértices de 35 que toca todas as alternativas. Assim, 35 é o máximo da regra que empresta cada geração uma vez e protege todas as potenciais origens. A terceira tile recupera 6 CPU e 7 CUDA. A quarta recupera 15 CPU e 7 CUDA. O método exige conhecer os usos futuros e a sobrescrita antes do retorno. Uma política com outros movimentos ou uma cache adicional tem outro espaço de soluções.

| Conta no pedido nominal | Valor |
|---|---:|
| Janelas alinhadas evitadas | 462 766 080 B |
| Cópias dos três payloads dentro de cada tier | 555 206 400 B CPU e 370 137 600 B CUDA |
| Saldo para cópia, coordenação e propostas com o preço da primeira / segunda observação | +53,138 / +22,791 ms |
| Défice com a proposta a gastar todo o seu orçamento de 6 tok/s | 3 622 147 398 B |

As duas cópias por acerto transferem 925 344 000 B de payload no total. A restauração substitui a entrega original ao slot. A comparação de custo deve medir quanto muda o tempo exposto incluindo a captura, a entrega, as esperas pelos leitores e a concorrência com o serviço de disco. A 4,5 GB/s, a combinação é **NO_GO** quando as novas verificações consomem a verba que as deixa exatamente a 6 tok/s e **INCONCLUSIVE** com o preço de decode mais favorável. A agenda pode contribuir para um ganho parcial. O preço observado no portátil e uma regra causal distinguem essa possibilidade de uma vantagem do oráculo. [Orçamento do pedido e pressupostos](reloads.md)

Protocolo `77e7c3ad`, código `3078f25198d215559d96a40395216253b9c08db4`. A fixture inclui um caminho aumentante obrigatório, uma cobertura mínima, uma cópia com conservação e um leitor de parking que invalida a cópia. Os dois replays demoraram 1,67 e 1,70 s, com picos de cgroup de 74,4 e 75,9 MiB, zero swap e zero forwards. Ambos produziram SHA-256 `7d3e20f41f8e1c92add2e7bad358a1c61026950f2c145567f496c179d97c8063`. Parte 189 com 41 376 B em quatro ficheiros. [Manifesto](../../../../../../../../../../../private_archive/part-189.json)

```sh
python3 -IB "$HTTP/slots.py" --archive "$AR" --previous "$RELOAD_REVIEW" \
  --capture "$CAPTURE" --verified "$VERIFIED" --plan "$PLAN" \
  --commit "$MEASUREMENT_COMMIT" --new-output-dir "$NEW"
```
