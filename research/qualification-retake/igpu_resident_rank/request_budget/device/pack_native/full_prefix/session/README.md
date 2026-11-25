# Dois pedidos naturais com seleção selada entre turnos

O operador conserva o cliente P, o servidor, os FDs e os recursos qualificados. O novo dado disponível para a política é a sequência completa das vítimas e dos ranks desde o início do primeiro pedido. O seletor só recebe um iterador dos registos publicados de T1, a lista das suas nove chamadas de prefill e a capacidade de 353. Cada execução da política parte de um banco vazio. [Protocolo](protocol.md) · [Seletor](../../natural_trace/prefill_retention/policy.py)

O processo OFF arquivado na parte 97 foi reaberto com a sua DSO e o revisor original. A reprodução confirmou 78 e 47 IDs e as duas respostas naturais. Os cinco testes locais cobrem o arquivo e permissões do cabeçalho, criação exclusiva e releitura do selo, espaço para T2, recusa de um corte inválido antes de emitir o POST, prazo próprio do selo e identidade do recibo passado ao revisor. A preparação herdada verifica o gate C292 para o ELF exato, a listagem dos providers do servidor, o manifesto e a C55 posterior às qualificações. Os resultados físicos futuros ficam nos diretórios privados de cada braço. [Runner](family.py) · [Admissão e captura](capture.py) · [Testes](test_session.py)

### Comando

Usar Bash, o worktree congelado `W` e o seu `COMMIT`. Fornecer os objetos acabados desta campanha, com os seus SHA externos, em `BUILD`, `FIXTURE`, `BRIDGE` e `C55`. Os dois diretórios de saída devem ser novos. Preparar antes de pedir a janela física e passar o SHA do recibo da preparação ao lançamento autorizado.

```bash
D="$W/research/qualification-retake/igpu_resident_rank/request_budget/device/pack_native/full_prefix/session"
ARC=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01
args=(--repo "$W" --commit "$COMMIT" --unit-prefix "$UNIT_PREFIX"
  --preflight-dir /tmp/tesy-env49-static-r01
  --preflight-sha256 2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16
  --placement /tmp/tesy-nvme-placement-20261124-01/receipt.json
  --c270 /tmp/tesy-c270-driver-20261125-r01/receipt.json
  --c270-sha256 1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6
  --closure-dir /tmp/tesy-c281-pack-link-20261125-r01
  --derived-dir /home/pmglo/models/tesy-gpt-oss-120b-nvme/tesy-c291-manifest-20261125-r02
  --constructor-receipt /tmp/tesy-pack-manifest-constructor-20261125-r02/receipt.json
  --c292-receipt "$ARC/part-54/c292-nvme-numeric-pair-20261125-r01/receipt.json"
  --history-dir "$ARC/part-23/tesy-c281-driver-20261125-r01"
  --prior-family "$ARC/part-97/tesy-c281-pack-observer-natural-20261125-r01"
  --build-dir "$BUILD" --build-sha256 "$BUILD_SHA"
  --fixture-dir "$FIXTURE" --fixture-sha256 "$FIXTURE_SHA"
  --bridge-dir "$BRIDGE" --bridge-sha256 "$BRIDGE_SHA"
  --window "$C55" --window-sha256 "$C55_SHA")
python3 -IB "$D/test_session.py"
python3 -IB "$D/family.py" "${args[@]}" --new-output-dir "$PREPARED"
python3 -IB "$D/family.py" "${args[@]}" --prepared "$PREPARED/family.json" \
  --prepared-sha256 "$PREPARED_SHA" --execute --new-output-dir "$FAMILY"
```

O prefixo de unidade `tesy-c281-nvme-` é obrigatório. O journal escreve-se em `ON/observer/events.pfj`. Os dois selos `ON/before-t2-candidates.json` e `ON/before-t2.json` ficam fechados antes de T2. O relatório `ON/journal-audit.json` verifica a drenagem e a conservação do próprio processo. O recibo da família sela cada `arm.json`, que sela o `receipt.json` do respetivo cliente. Tempos de seleção, CPU do cliente e máximos de RSS do processo antes e depois da seleção constam do selo. Um máximo de RSS pode incluir trabalho anterior do mesmo processo.
