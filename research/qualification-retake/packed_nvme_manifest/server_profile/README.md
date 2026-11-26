# Ligação do servidor C281 ao pack C291

**REPRODUZIDO — PASS_C281_C291_STATIC_CLOSURE.** O loader resolveu as relocações de dados e funções do servidor C281 com a biblioteca C269 de controlo e com a biblioteca C291 nos ambientes OFF e ON. A listagem integral abrangeu 24 fornecedores. Só mudou o fornecedor de `libllama.so.0`; OFF e ON produziram a mesma seleção em todas as vistas. O controlo negativo detetou a troca de biblioteca nos dois sentidos. [Critério pré-registado](protocol.md) · [Síntese com os hashes](evidence/static.json)

| Raiz com dependência direta de libllama | Fornecedores em cada um dos três ambientes |
|---|---:|
| Executável do servidor | 24 |
| libllama-server-impl.so | 23 |
| libllama-common.so.0 | 21 |
| libmtmd.so.0 | 18 |

O inventário `DT_NEEDED` cobriu o executável e os 24 objetos. As 53 consultas incluíram doze pares de listagens e verificações de relocações, três verificações do executável e uma nova listagem integral do controlo no fecho. O ensaio na revisão `d223b00f170466a94e0364bff3578b877c79e16f` durou 0,660 s; o pico do cgroup foi de 29 413 376 B, com limite de 2 GiB e swap desativado. Processos de servidor, consultas de dispositivos, forwards e bytes de payload lidos foram todos zero. [Código da consulta](screen.py)

A C55 de disponibilidade de 60 s registou um cap de 22 548 578 304 B. O seu recibo tem SHA-256 `eba3ff806f617775f902201d5d8f8206a454d708bd802e5f239425604d3c17be`. A próxima prova exige arranque real, verificação dos objetos mapeados e FDs abertos, e o par de conversas com validação dos dois turnos. A paridade numérica anterior cobre a captura C292. [Captura do 120B](../capture_numeric/README.md) · [Condições do endpoint](../../phase_fd/integrated/t1_full_pack_service/product-path.md)

## Reprodução offline

O arquivo privado da parte 55 contém 113 ficheiros e 275 602 B. O manifesto tem SHA-256 `8e4805abc5d30d7e35e73d778f9c8d2031fa56acf1d4e88de8124751f9e0af8d`. O revisor autentica o recibo terminal `9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116` e os 106 logs de stdout/stderr, confere os controlos e projeta o compacto. A cópia transferida reproduziu o mesmo ficheiro byte a byte, SHA-256 `3890cc76927d17845425550c5c36785297a0291969efb5433a62cea5bd0df716`. Na pasta deste README:

```sh
python3 -IB compact.py "$PART55/tesy-c281-pack-link-20261125-r01" | cmp - evidence/static.json
```

## Reprodução da consulta no portátil

Numa checkout limpa da revisão de medição, com a cadeia de metadados e o ambiente de bibliotecas preexistentes autenticados pelo protocolo, usar uma identidade de scope e um destino privado novos:

```sh
systemd-run --user --scope --unit="$UNIT" -p MemoryHigh=2G -p MemoryMax=2G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=130 \
  python3 -IB "$W/research/qualification-retake/packed_nvme_manifest/server_profile/screen.py" \
  --commit d223b00f170466a94e0364bff3578b877c79e16f --unit "$UNIT" \
  --preflight-dir "$C270_STATIC_R01" --c281-receipt "$C281_R0/receipt.json" \
  --c292-receipt "$C292_PAIR/receipt.json" --derived-dir "$DERIVED_R02" \
  --constructor-receipt "$CONSTRUCTOR_R02/receipt.json" \
  --bin-dir "$C7/results/c283-exact-expert-service-epoch-20261006T194311Z/build/expert-store/bin" \
  --new-output-dir "$NEW"
```
