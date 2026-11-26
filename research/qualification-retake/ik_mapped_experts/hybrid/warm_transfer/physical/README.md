# Três SET de páginas quentes para um slot CUDA

**O envio isolado de 13 219 200 B de shmem já residente demorou 1,072303 e 1,074177 ms nas medianas dos dois processos.** A taxa útil foi 12,328 e 12,306 GB/s. Ambas cobrem os quatro requisitos de transferência de ClassLRU 161/288 na rota Tesy. Para 288, mesmo a esta taxa, os envios em série ocupariam 7,591–7,604 s do orçamento de 10 s até à primeira peça final. A conversa do ik e a sobreposição com o seu compute continuam por medir. [Protocolo](../protocol.md) · [Resultado completo em ns](result.json)

## Medição e ordem

O relógio monotónico abre antes do primeiro SET e fecha depois de sincronizar a stream. Cada fill emite três pedidos assíncronos de 4 406 400 B. A coluna de submissão inclui o tempo que o chamador permanece nessas APIs, inclusive possível staging do driver. O drain mede o intervalo entre o retorno do terceiro SET e o retorno da sincronização. São relógios no anfitrião. As medianas de submissão e drain são calculadas separadamente. [Implementação do intervalo](../transfer.cpp)

| Processo | Fonte | n | Parede mediana (ms) | Submissão mediana (ms) | Drain mediano (ms) | GB/s na mediana | GB/s por soma de bytes/parede |
|---|---|---:|---:|---:|---:|---:|---:|
| FILE primeiro | FILE | 5 | 1,072303 | 0,982503 | 0,089800 | 12,328 | 12,352 |
| FILE primeiro | ANON | 5 | 1,067694 | 0,976792 | 0,090401 | 12,381 | 12,403 |
| ANON primeiro | FILE | 5 | 1,074177 | 0,984246 | 0,089819 | 12,306 | 12,314 |
| ANON primeiro | ANON | 5 | 1,076260 | 0,987022 | 0,089238 | 12,283 | 12,273 |

Cada par tem a mesma carga por fonte, e o primeiro modo alterna dentro de cada processo. A tabela dá a parede dos dois fills individuais e a diferença FILE menos ANON, em µs. Os dois fills iniciais de exatidão por processo ficam fora destas estatísticas.

| Par | 1.º processo, ordem | FILE | ANON | Diferença | 2.º processo, ordem | FILE | ANON | Diferença |
|---|---|---:|---:|---:|---|---:|---:|---:|
| 1 | F→A | 1 080,629 | 1 075,609 | +5,020 | A→F | 1 073,696 | 1 076,260 | −2,564 |
| 2 | A→F | 1 074,446 | 1 044,830 | +29,616 | F→A | 1 074,467 | 1 081,600 | −7,133 |
| 3 | F→A | 1 056,884 | 1 073,845 | −16,961 | A→F | 1 077,111 | 1 072,503 | +4,608 |
| 4 | A→F | 1 072,303 | 1 067,694 | +4,609 | F→A | 1 074,177 | 1 074,206 | −0,029 |
| 5 | F→A | 1 066,962 | 1 067,193 | −0,231 | A→F | 1 068,084 | 1 081,039 | −12,955 |

A diferença mediana emparelhada mudou de sinal, +4,609 e −2,564 µs. A ordem não sustenta uma vantagem consistente de uma fonte. Em dez fills por fonte, FILE levou 10,718759 ms (9,820623 ms de submissão e 0,898136 ms de drain), ANON 10,714779 ms (9,816507 e 0,898272 ms). Ambas enviaram 132 192 000 B, a 12,333 e 12,337 GB/s agregados. O recibo conserva também o tempo de CPU da thread e do processo por repetição.

## Quanto caberia nos dois orçamentos?

A conta multiplica os fills do replay pela mediana FILE de cada processo, por ordem de execução. Assume o mesmo custo para cada reposição serial, um drain por fill, todas as origens quentes e a rota do Tesy. A taxa e o teto de ms/fill usam 10 s para a primeira peça final e 47/6 s para as 47 saídas do decode. Os recortes partilham trabalho. Os saldos não se somam. [Contagens e semântica ClassLRU](../../natural_link/classlru/two_steps/README.md) · [Composição de runs na trajetória](../natural_runs/README.md)

| Slots / fase | Fills | GB/s exigidos | Teto ms/fill | Serviço em série nos dois processos (s) | Saldo para o restante trabalho em série (s) |
|---|---:|---:|---:|---:|---:|
| 161 / primeira peça final | 7 930 | 10,483 | 1,261034 | 8,503 / 8,518 | 1,497 / 1,482 |
| 161 / decode | 4 706 | 7,942 | 1,664542 | 5,046 / 5,055 | 2,787 / 2,778 |
| 288 / primeira peça final | 7 079 | 9,358 | 1,412629 | 7,591 / 7,604 | 2,409 / 2,396 |
| 288 / decode | 3 987 | 6,728 | 1,964719 | 4,275 / 4,283 | 3,558 / 3,551 |

O resultado cobre o preço local em páginas reutilizadas com ritmo de submissão isolado. A execução natural pode agrupar fills por sítio, confirmar IDs, publicar mapas, competir pela GPU e encontrar páginas de Btrfs ausentes. O saldo da tabela é condicional e não estima a latência do cliente ou a energia.

## Exatidão, recursos e reprodução

Cada processo validou todo o payload de ambas as fontes com readback independente antes dos cinco pares. Os 24 fills somaram 317 260 800 B úteis e 72 cópias de pesos, incluindo os quatro fills de exatidão. As três fontes por fill tinham 1 077 páginas residentes cada uma antes e depois. Cada repetição cronometrada envenenou e releu nove janelas de 64 B fora do relógio. Dentro da janela de uso de recursos houve zero faltas maiores e zero blocos lidos nos 24 fills. As 20 repetições cronometradas também registaram zero faltas menores.

Os dois inventários C118 tiveram 61 amostras em 60,144 e 60,170 s. Cada processo confirmou três handoffs e terminou com código zero e sem PID compute observado à saída. O pico de memória do scope foi 231 165 952 B, com swap zero. Durante os braços, o máximo observado foi 140 MiB de VRAM, 47,625 °C na CPU, 41,45 °C na GPU e 31,85 °C no NVMe. As oito amostras de processo não resolvem picos por SET. A energia ficou por medir.

O recibo da família tem SHA-256 `7f293f12c61bcc82822c60ddc7c2ad743e72ef9fe03c0081d0a2fbdea65e3740` e o preflight `7440238fc277b4788240b18aa23053d4d2e93624ee2dbdf3274281a49229ce36`. As duas reaberturas, sobre os originais e sobre as cópias preservadas, produziram o mesmo ficheiro de resultado (`98e3a4f013d89e09dd312fad31117ad1e2a8526f33593eef9213abcbe7716c46`). O revisor confere o inventário inicial por processo, os mapas de providers, os handoffs e os dados nativos antes de recalcular as taxas. Doze testes cobrem o contrato de transferência e a comparação dos quatro cortes, incluindo igualdade exata ao limite e mediana favorável com agregado insuficiente. [Manifesto da família na parte 138](../../../../private_archive/part-138.json) · [C55 na parte 136](../../../../private_archive/part-136.json)

A partir deste diretório, a reprodução usa `ARCHIVE` para a raiz privada da qualificação e `NEW` para um destino novo.

```sh
python3 -IB review.py \
  --family "$ARCHIVE/part-138/tesy-ik-warm-transfer-20261126-r01" \
  --family-sha256 7f293f12c61bcc82822c60ddc7c2ad743e72ef9fe03c0081d0a2fbdea65e3740 \
  --build "$ARCHIVE/part-138/tesy-ik-warm-transfer-build-20261126-r01" \
  --prepared "$ARCHIVE/part-138/tesy-ik-warm-transfer-prepared-20261126-r01" \
  --prepared-sha256 7440238fc277b4788240b18aa23053d4d2e93624ee2dbdf3274281a49229ce36 \
  --c55 "$ARCHIVE/part-136/tesy-ik-hybrid-tiny-admission-20261126-r01" \
  --new-output-dir "$NEW"
pytest -q ../test_grade.py test_review.py
```
