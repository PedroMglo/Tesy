# Reabrir um bloco C281 com o histórico original

O bloco físico de 25 de novembro usou o protocolo de `522c5696`, a guarda C55 de `2439fe5c` e o fecho entre braços de `7aae40d2`. O controlo R é C269. O e P partilham o fornecedor C291, com o pack integral só em P. O binário C281, a GPU, o contexto de 8192, ub32, quatro workers e as entradas C281 são comuns. Os servidores arrancam com prefixo vazio; a segunda entrada de cada processo incorpora a saída efetiva do primeiro pedido. [Protocolo](protocol.md) · [Transição TCP qualificada](interarm.md) · [Origem e identidade do pack](../../README.md)

## Revisão offline

A partir da raiz do repositório, `ARCHIVE` é a raiz local de `qualification-20261124-nvme-01`. O diretório indicado por `NEW` deve ser novo. O revisor confere hashes dos três braços, cap e amostras por PID, início e fim, descritores dos pesos, projeções SSE, todos os IDs e o histórico oficial. Reabre a referência da parte 23. Pode usar as cópias arquivadas dos braços inteiros.

```sh
u=research/qualification-retake/packed_nvme_manifest/server_profile/conversation
python3 -IB "$u/compact.py" \
  --raw "$ARCHIVE/part-78/tesy-c281-rop-natural-20261125-r02" \
  --history-dir "$ARCHIVE/part-23/tesy-c281-driver-20261125-r01" \
  --new-output-dir "$NEW"
```

## Parâmetros da medição

O manifesto da parte 76 arquiva as três janelas de recursos, os inventários de memória e a preparação R01. A parte 77 contém a tentativa física R01 e a preparação R02. O recibo `family.json` da preparação contém caminhos, commit, árvore, prefixo de unidade, hashes da política, dos programas, de C270 e do preflight do runtime. A opção `--execute` exige uma preparação compatível. Para executar uma experiência futura, a identidade, os destinos, a janela C55 e a admissão dos processos têm de corresponder à nova campanha do portátil.

```sh
python3 -IB "$u/family.py" --repo "$FROZEN" \
  --placement "$PLACEMENT/receipt.json" \
  --c270 "$C270/receipt.json" --c270-sha256 1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6 \
  --preflight-dir "$PREFLIGHT" --preflight-sha256 2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16 \
  --history-dir "$HISTORY" --closure-dir "$CLOSURE" --derived-dir "$VERIFIED_PACK" \
  --constructor-receipt "$CONSTRUCTOR/receipt.json" --c292-receipt "$C292/receipt.json" \
  --commit 7aae40d22a2fe466a7ab5e25a717cfb65dcf60e5 \
  --unit-prefix tesy-c281-nvme-rop-20261125-r02 --window "$C55" \
  --window-sha256 fd6def9a80f1756dd4616c3463a359ee5558012978dbeb8fe2eaf2ae12a10d9a \
  --new-output-dir "$PREPARED"
```

Na segunda invocação foi conservada a mesma lista de argumentos até `--window-sha256` e foram passados `--prepared "$PREPARED/family.json" --execute --new-output-dir "$RAW"`. O cliente, os binários e os dados privados permanecem no portátil. O verificador e os testes de rejeição funcionam sem modelo.
