# A DSO aplicou sete fusões na tile CPU0 genuína

**GO_TIMING_FIXTURE.** Os quatro processos reproduziram os 92 160 F32 de C266, bit a bit. No original, a DSO não exporta o contador. Nos modos candidatos OFF, MMID e FUSION os contadores registaram respetivamente **0, 0 e 7**. Em cada processo candidato o valor foi o mesmo após a sincronização do FFN e após o join dos quatro workers. A métrica conta regiões por processo. O grafo tem uma wave ativa e sete estacionadas. [Recibo reproduzido](physical-r01/receipt.json) · [Pré-registo](protocol.md)

**MEDIDO no portátil.** O scheduler e o manager originais serviram os cinco experts a partir do pack. Os quatro braços somam 264 437 760 B pedidos em leituras alinhadas e 1 474 560 B de saída, SHA-256 da tile bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24. A família levou 61,295 s incluindo 60,191 s de C118, pico de 196 685 824 B no cgroup e zero swap. Cada restituição do contador verificou o PID e a DSO, e o supervisor examinou todos os valores da saída quanto a finitude. A atribuição temporal desta intervenção exige uma DSO sem contador e uma comparação emparelhada. [Gate de custo](../timing/protocol.md)

A revisão física é 313448d631964f0067ea5ddf410c8b095b7a6526. O recibo do cliente compilado tem SHA-256 ae7aa437b883672f404e5bd4d679b7c4929f8d6447b877dccdc4bedfa5ff9285 e o terminal 7b7f543d76d4c3a7f13200fa962a07d8ab31595ea821392f7c6982362b8a3b54. O arquivo privado qualification-20261124-nvme-01/part-27 contém 63 ficheiros e 8 121 416 B, manifesto 6a70f169026020ea60a1003e2dcdcb9f8eaf4f1e8be2e9b3a431e4ac5149f4d0. A reabertura dos dois diretórios desse arquivo reproduziu a decisão sem executar um novo operador.

```sh
python3 -IB research/qualification-retake/parked_fusion/real_tile/compact.py \
  --repo "$TESY_CHECKOUT" --raw-root "$TESY_PART27/tesy-real-fusion-20261125-r01" \
  --build-dir "$TESY_PART27/tesy-real-fusion-client-20261125-r01" --input-dir "$CPU0_INPUT" \
  --c55-dir "$TESY_PART25/tesy-parked-mmid-c55-20261125-r02" \
  --receipt-sha256 7b7f543d76d4c3a7f13200fa962a07d8ab31595ea821392f7c6982362b8a3b54 \
  --new-output-dir "$NOVO_COMPACTO"
```
