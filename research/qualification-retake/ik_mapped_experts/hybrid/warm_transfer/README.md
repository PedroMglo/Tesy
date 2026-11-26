# Preço isolado do envio de um expert para a RTX 4060

**PREPARADO.** O programa mede o intervalo entre o primeiro SET do gate e a
conclusão da stream após os SET do up e do down. Envia 13 219 200 B por
repetição. A fonte principal é um ficheiro shmem selado, mapeado em modo de
leitura, com as páginas residentes. O controlo usa um mapeamento anónimo com
os mesmos bytes e alinhamento. O lote alterna as ordens nos dois processos.
A comparação inclui a submissão, a eventual cópia de staging feita pelo driver
e a espera pela conclusão. [Contrato congelado](protocol.md)

O cliente usa o pin ik 7a5d9000 e a mesma DSO que passar na fixture de
residência e cache. Por papel, o offset módulo página é 2 080, 2 592 e
2 080 B, a partir dos metadados do GGUF já autenticados. As chamadas vão
para um slot interior em três tensores MXFP4 e o auditor CUDART partilhado
conta três cópias H2D assíncronas com os endereços exatos de origem e
destino. A qualificação verifica todas as posições de cada matriz. Durante
a medição, as janelas de 64 B do começo, meio e fim de cada papel recebem
o complemento dos bytes esperados antes do relógio. A leitura de volta
depois do drain verifica as nove janelas. O tempo de CPU cobre uma janela
ligeiramente maior que o relógio de parede dos SETs, pois a sua leitura é
exterior aos carimbos de parede. Os contadores por processo registam faltas
e operações de leitura em blocos. [Geometria C283](../../result.json) · [Auditor CUDART](../client/copy.cpp)

A unidade anterior não conserva o preço do mmap quente nas dimensões reais.
O ensaio 20B de setembro usou buffers prontos contendo também os biases,
com proveniência de execução incompleta. Uma medição aqui serviria para
confrontar os requisitos de 10,483 e 7,942 GB/s de ClassLRU 161 em T2.
O resultado dependeria da residência quente e repetida desta pequena amostra.
O mmap do GGUF sob pressão em Btrfs, os fills contíguos que o hook consegue
fundir, o serviço de outros tensores e o tempo de cliente requerem observações
próprias. [Antecedente](../../../../EXPERT-CROSSOVER-RESULT-20260924.md) · [Limiares causais e denominadores](../natural_link/classlru/README.md)

O teste local dos dez cenários cobre as ordens, reciprocidade de taxas,
comparação emparelhada e recusas por falta de página, registo, falha de
I/O, contagens, escopo do relógio e readback. A compilação requer o recibo
efetivo de link SM89. O preflight físico exige o recibo de PASS da família
GPU minúscula, a C55 e um destino novo. O operador usa a mesma política e
três handoffs de PID/UUID por processo do ensaio anterior. Nenhum forward
ou leitura do GGUF original integra este procedimento. [Supervisor utilizado](../device/run.py)

```sh
python3 -m pytest -q test_grade.py
python3 -IB build.py --help
python3 -IB run.py --help
```

Para a futura compilação admitida, a partir da checkout congelada, os
parâmetros são o pin do ik, a build SM89 e o seu SHA exterior, o mapa
estático ENV49 e um diretório exclusivo. A preparação da família usa um
novo diretório. A execução física acrescenta o diretório de saída exclusivo
do ensaio, o nome do scope, o recibo PREPARED_ONLY e o seu SHA exterior.

```sh
python3 -IB build.py --source "$IK" --dso "$SM89" --dso-sha256 "$SM89_SHA" \
  --commit "$FROZEN" --env49-map "$ENV49" --new-output-dir "$BUILD"
python3 -IB run.py --commit "$FROZEN" --dso "$SM89" --dso-sha256 "$SM89_SHA" \
  --build "$BUILD" --build-sha256 "$BUILD_SHA" \
  --tiny-family "$TINY_RECEIPT" --tiny-sha256 "$TINY_SHA" --env49 "$ENV49" \
  --c55 "$WINDOW" --c55-sha256 "$WINDOW_SHA" --new-output-dir "$PREP"
```
