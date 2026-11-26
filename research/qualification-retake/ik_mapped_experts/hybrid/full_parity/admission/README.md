# Admissão dos cortes privados C110 no ik

O preflight vincula o cliente numérico à mesma build CUDA e às mesmas fontes
da família minúscula R03 e da capacidade física do original. A capacidade
precisa de terminar com os 108 pesos mapeados, os 108 biases na GPU e o
contexto de 288 slots validado. O supervisor reabre a grade e o inventário
da família. Os controlos C110, stock e ik CPU D0/D1 entram pelos digests das
linhas completas; o executável incorpora também os 17 IDs de entrada.

A campanha física requer uma C55 dedicada `tesy-ik-full-parity-c55-*`, a
checkout limpa do preflight e um scope transitório `tesy-ik-e10-full-parity-*`
FILE_PAGING com 10 GiB de máximo e swap zero. Cada filho tem o seu C118 de
60 s, os mesmos limites de carga, contexto, prefill, teacher e cleanup e os
seus raws até 64 MiB. Durante P e T, o processo externo atesta a VMA do
modelo e os providers contra o snapshot guardado pelo cliente e relê a linha
completa de 804 352 B antes de devolver ACK. A posição 15 tem de ter máximo
único 3659; a posição 16, máximo único 3992. Em erro nativo antes de um
handoff, o supervisor preserva o código de saída, a última fronteira e os
bytes eventualmente existentes em `available_rows`.

O segundo processo exige os cortes e a grade completos do primeiro, saúde,
exit 0, recuperação da VRAM, scope liberto e raws ainda íntegros. A decisão
final compara a colocação, as rotas ordenadas e as duas linhas entre braços.
Os picos do cgroup são cumulativos no scope da família. Os picos de GPU são
amostrados. As comparações com outras implementações têm denominadores e
estatutos próprios. [Protocolo numérico](../protocol.md)

```sh
python3 -IB run.py --help
python3 -m pytest -q test_run.py
```

Para a preparação, passar os diretórios selados no arquivo ou em disco e os
SHA exteriores, incluindo `--capacity` (raiz da campanha de capacidade),
`--capacity-client` (ELF respetivo), `--client` (build numérica),
`--ids` (ficheiro de 68 B), `--c110-parent`, `--stock-file`,
`--cpu-d0`, `--cpu-d1`, os restantes inputs da capacidade e um
`--new-output-dir` exclusivo. O resultado válido da preparação é
`PREPARED_ONLY` com zero arranques. A execução usa outra raiz exclusiva
no NVMe, a mesma autoridade e acrescenta
`--execute --unit UNIT --prepared PREP --prepared-sha256 SHA`.
O operador consulta `receipt.json` na raiz e em cada subdiretório de braço.
