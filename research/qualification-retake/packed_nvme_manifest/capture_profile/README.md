# Pré-voo do cliente numérico C292 no NVMe

O loader e `ldd -r` verificam os fornecedores e as relocações do ELF histórico. A derivação e o respetivo construtor são um par selado; nesta campanha usa-se R02. O supervisor revalida o deployment e a presença dos aliases privados do C270. O manifesto indica os paths originais do índice e dos pesos na estação. Os recibos e logs podem ser arquivados depois do fecho. [Critério](protocol.md) · [Pares admitidos](metadata-pairs.md)

```sh
systemd-run --user --scope --unit="$UNIT" -p MemoryHigh=2G -p MemoryMax=2G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=130 \
  python3 -IB "$W/research/qualification-retake/packed_nvme_manifest/capture_profile/screen.py" \
  --commit "$FROZEN_COMMIT" --unit "$UNIT" --preflight-dir "$C270_STATIC_R01" \
  --bin-dir "$C7/results/c283-exact-expert-service-epoch-20261006T194311Z/build/expert-store/bin" \
  --derived-dir "$DERIVED_R02" --constructor-receipt "$CONSTRUCTOR_R02/receipt.json" \
  --derived-sha256 cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9 \
  --constructor-sha256 c81c15cb9614fd2780f35d5f3fc2b96ce280056f9da363ca74b42b112d1642f1 \
  --new-output-dir "$NEW"
```

As chamadas de listagem recebem só `PATH`, `LC_ALL` e o caminho de bibliotecas selado. Em ON recebem também o manifesto C291. O programa de ensaio não invoca o binário de captura, nvidia-smi ou CUDA. O código de arranque C127 confirma que a opção `--list-devices` pertence a outro cliente. [Próxima prova numérica](../../phase_fd/integrated/t1_full_pack_service/product-path.md)

A execução na revisão 755c14a4 terminou em PASS_C292_CAPTURE_STATIC_CLOSURE. O loader resolveu as relocações dos 18 fornecedores em OFF e ON e o controlo detetou a biblioteca errada. O recibo SHA-256 7b0ca3bcc778f527dfc4cdfab3aaa3f93687045cba5e12d5a74b8310aeb7b670 identifica os providers, o manifesto e o construtor. O ensaio durou 0,299 s, com zero forwards e leituras de payload. A prova VMA e dos FDs efetivamente usados entra na captura numérica nativa.
