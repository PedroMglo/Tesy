# O que custa trazer as leituras em falta pelo PCIe

**NO_GO para a composição U1262 × C287 nesta agenda de procura.** Mesmo que
todos os experts tenham o tamanho do melhor da amostra, e que a descompressão
e as lacunas custem zero, atingir o primeiro conteúdo final em 10 s exigiria
na melhor ordem pelo menos **42,964 GB/s** para as leituras CPU antes sem
preço. A ligação do NVMe a esta máquina permite conceder no máximo **8 GB/s**
por sentido, já ignorando toda a codificação e overhead. No melhor cruzamento
faltam **182,861 ms** no relógio do pedido. O piso de decode ainda é compatível
com 6 tok/s; a qualificação de produto conserva M3 PARTIAL e M4 NOT_MET.

| Ordem prefill / decode | Margem anterior G=0 ms | Novo piso adicional ms | Margem conjunta ms | Margem de decode a 6 tok/s ms | Banda necessária para os dois alvos |
|---|---:|---:|---:|---:|---|
| RP / RP | −147,490 | 224,531 | −372,022 | +1 920,747 | Inviável mesmo com custo adicional zero |
| RP / PR | −172,349 | 224,393 | −396,742 | +1 896,026 | Inviável mesmo com custo adicional zero |
| PR / RP | +41,670 | 224,531 | −182,861 | +1 920,747 | ≥42,964 GB/s |
| PR / PR | +16,811 | 224,393 | −207,581 | +1 896,026 | ≥106,494 GB/s |

**FORMAL, nas condições publicadas.** Os 254 jobs com READ desconhecido
pedem 2 860 015 616 B em 222 callbacks. Em 193 existe uma leitura sem preço,
em 26 existem duas e em três existem três. Só as 142 callbacks sem qualquer
cadeia conhecida exigem 1 790 324 736 B, equivalentes a 159 registos.
Mesmo ao topo de 8 GB/s esses bytes exigem **223,790592 ms**. Os restantes
READs podem decorrer dentro da cadeia já cobrada até à duração dessa cadeia.
Somar somente a parte descoberta produz os dois pisos da tabela. Os quatro
workers concorrem pela mesma ligação. [Crivo original](../protocol.md) ·
[Fórmula e contraprovas](protocol.md) · [Recibo completo](receipt.json)

Para reabrir por colocação dos bytes dentro da melhor ordem, no máximo
**1 397 126 657 B de 2 860 015 616 B (48,8503%)** poderiam atravessar o link
durante as callbacks; pelo menos **1 462 888 959 B** teriam de estar
disponíveis por outra via nesses instantes. A segunda ordem admite,
no máximo, **1 199 364 297 B (41,9355%)**. Estes limites deixam escolher
gratuitamente que partes de cada registo são locais. A requisição física
ainda tem de compor cada expert inteiro e provar paridade bit a bit.

**MEDIDO na origem e na ligação.** A colocação `adc58125…54a000` identifica o
pack integral de 61 096 329 216 B, relido no destino NVMe com o mesmo SHA do
source. Os dois recibos do decode nas partes 66 autenticam esse pack, o mesmo
inode no Btrfs do dispositivo `nvme0n1` e os respetivos READs. Em 25 de
novembro de 2026, a leitura de sysfs identificou o NVMe Micron
`MTFDKBK1T0QFM-1BD1AABGB`, PCI `1344:5413`. Tanto o endpoint como a ponte
reportaram 16 GT/s ×4 para a ligação atual e máxima. A PCI-SIG especifica
16,0 GT/s por lane em Gen4. Quatro lanes dão no máximo 64 Gbit/s antes de
retirar quaisquer símbolos ou pacotes. [Observação da estação](link.json) ·
[PCI-SIG, FAQ PCI Express 4.0](https://pcisig.com/faq?field_category_value%5B%5D=pci_express_4.0)

O ficheiro da composição comprimida é hipotético. Para cobrar o piso
assume-se que cada READ sem preço requer os 11 259 904 B do registo naquele
instante, a partir do NVMe e dentro da própria callback. Um prefetch cuja
conclusão preceda a callback, residência em RAM, reutilização de uma leitura
em voo ou armazenamento físico mais compacto podem mudar o volume ou o
relógio. A autoridade para essa alternativa seria um censo por callback dos
bytes já locais, bytes efetivamente transportados e momento da sua publicação.
Os contadores do pack raw e o tamanho do melhor expert comprimido observado
não constituem tal medição. A poupança marginal dos componentes anteriores
mantém os seus próprios recibos.

Pré-registo `a0a7d976` e código `77e5ec6d`. Duas execuções em checkout
limpa, limites de 120 s e 512 MiB. Demoraram 0,85 e 0,86 s com RSS de
81 740/81 556 KiB. Ambas produziram SHA-256
`1d3f182f57736edcac51b8c008e19f2cb57693546ff2861ddb5a9d0b5eab1bb0`.
Zero leituras de pesos, processos de inferência e execuções GPU.

```sh
python3 -IB "$STUDY/test_floor.py"
timeout 120 prlimit --as=536870912 --cpu=118:120 --fsize=1048576 -- \
  python3 -IB "$STUDY/screen.py" --archive "$ARCHIVE" --combined "$U1262_C287_RECEIPT" \
  --placement "$PACK_PLACEMENT_RECEIPT" --new-output-dir "$NEW_OUTPUT"
```
