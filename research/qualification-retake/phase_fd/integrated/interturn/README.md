# Aquecimento da L2 entre os pedidos reais

**NO_GO para reler do NVMe apenas depois da resposta T1 e antes de T2 no par C281.** Mesmo concedendo toda a janela a 4,5 GB/s constantes, sem atrasar o utilizador, seria possível preparar no máximo seis experts inteiros em cada braço. A agenda primária registada no braço ON exige uma entrada de pelo menos 224 experts úteis no critério M4 ou 167 no cenário AR otimista. A captura OFF documenta a sua própria janela de cliente. Para aplicá-la ao mesmo requisito de volume é preciso admitir a população de ON, pois OFF não contém um journal dos experts. [Protocolo](protocol.md) · [Contas por braço e denominador](evidence/receipt.json) · [Origem dos requisitos de volume](../host_cache/README.md)

| Janela do cliente | Observada | Com margem exterior de 2 ms | Bytes máximos | Chaves completas |
|---|---:|---:|---:|---:|
| OFF R01 | 16,609741 ms | 18,609741 ms | 83 743 834 | 6 |
| ON R02 | 17,474894 ms | 19,474894 ms | 87 637 023 | 6 |

Cada chave ocupa 13 219 200 B. Reler 224 chaves integralmente exigiria **658,0224 ms** neste cenário de banda. Reler 167 exigiria **490,5792 ms**. Os relógios provêm individualmente do cliente que fez os dois POSTs em cada braço, desde o fim do streaming de T1 até ao início do relógio do pedido T2. Validar T1, montar a conversa real, renderizar o template e tokenizar T2 já ocupavam parte desse intervalo. O cálculo concede-o todo ao candidato. [Cliente e fronteiras do relógio](../../../../../tools/optin_integration_client.py) · [Cliente medido OFF/ON](../conversation/profile.py)

**Concessão dos residentes do primário.** Das 1 051 chaves que R0 carregou no prefill de ON, 199 estavam residentes à entrada e foram expulsas antes da respetiva recarga. Mesmo que as 199 estivessem de imediato disponíveis gratuitamente numa L2, o critério M4 exigiria mais **25 chaves** úteis de outra origem, ou 330 480 000 B. No mínimo seriam 73,44 ms de releitura. Depois de gastar a janela ainda faltariam pelo menos 19 chaves inteiras. No cenário AR de 46 avaliações, 199 cobre aritmeticamente 167 e a condição de volume dá apenas **HEADROOM_ONLY**. A utilidade temporal individual, o custo de copiar de RAM ou VRAM e a retenção dessas chaves continuam por demonstrar.

Uma intervenção que capture os bytes durante o serviço de T1 pode dispor de um intervalo diferente. Para a avaliar seriam necessárias as admissões causais de T1, as vítimas, os custos e a disponibilidade na fronteira de T2. O crivo aplica-se às duas janelas observadas, com primeiro conteúdo e decode ainda fora do objetivo. A banda de 4,5 GB/s é um cenário. [Auditoria no par natural](../conversation/README.md)

```sh
python3 -IB research/qualification-retake/phase_fd/integrated/interturn/test_screen.py
python3 -IB research/qualification-retake/phase_fd/integrated/interturn/screen.py \
  --archive-root "$TESY_PRIVATE_NVME_ARCHIVE" --new-output-dir "$NEW_OUTPUT"
```

O pré-registo é `e4d95fdc`; o método reproduzido é `34a1f825`. As duas saídas exclusivas produziram o mesmo SHA-256 `c8de31238e5fbd416b63c277de464fd8dbb27120fb3e7bf5efc9dbf303b2e9d6` em 0,03/0,04 s e 19 984/20 412 KiB de RSS. As fontes privadas são os quatro resultados e os dois recibos autenticados nos manifestos das partes 36 e 37. O crivo leu zero bytes de pesos e executou zero forwards.
