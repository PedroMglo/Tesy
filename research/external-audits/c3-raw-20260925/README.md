# Auditoria externa C3: publicação e reprodução

## O que está publicado

- `TESY-EXTERNAL-RAW-AUDIT-20260925.md`: relatório integral original, byte-idêntico ao entregue na conversa. A ausência de atribuição causal refere-se ao âmbito do bundle C3, não ao resultado N2 posterior.
- `audit-summary.json`: resultados estruturados por âmbito, agregados stock, FAIL de logits, recursos e limitações. Não duplica os snapshots de host de cada run.
- `audit_bundle.part1.txt`, `audit_bundle.part2.txt`, `audit_bundle.part3.txt`: concatenação byte-idêntica do auditor independente original `audit_bundle.py`.
- `test_audit_bundle.py.txt`: source exacto dos 12 testes adversariais do auditor.
- `execution-record.json`: hashes, ambiente original, repetição da auditoria na sessão de publicação, resultados e falha/reparação inicial do harness.

O source é arquivado como texto para preservar o instrumento de auditoria sem o instalar como código do Tesy, acrescentar NumPy às dependências do projecto ou alterar a sua CI. Não se trata de uma implementação nova do modelo nem de uma campanha física.

O JSON detalhado por run é reproduzível executando o auditor. O seu digest original está registado; os resultados não dependem de acesso a este chat. A lista de integridade completa repete as 211 entradas do manifesto que já acompanha o bundle público e não é duplicada no Git.

## Fonte pública congelada

- [Release de evidência](https://github.com/PedroMglo/Tesy/releases/tag/evidence/full-model-vertical-20260924-v1)
- [Bundle](https://github.com/PedroMglo/Tesy/releases/download/evidence/full-model-vertical-20260924-v1/tesy-vertical-raw-evidence-20260924.tar.gz)
- asset ID: `587026454`
- tamanho: `1646346` bytes
- SHA-256: `83b88fe09da4b1e038aec810537c7a30d702a7811dc78d4ebc29189f184a7bf6`
- manifesto de publicação auditado: `ca532aaa765ad551dcb8be4424f0abe6778eec96:research/coordination/C3-RAW-EVIDENCE-RELEASE.json`

O release consultado não estava marcado immutable. Usar o digest, não apenas o URL, como identidade da evidência.

## Reprodução sem modelo, GPU ou internet

Requisitos do instrumento externo: Python 3.10+ e NumPy. Não instalar automaticamente dependências nem descarregar modelos. Usar uma cópia já obtida do bundle, verificada pelo próprio script. O caminho do bundle é explícito: não procurar a campanha mais recente por glob.

A partir da raiz de um checkout que contenha esta publicação, executar, substituindo o caminho absoluto do bundle:

```bash
bash -s -- /CAMINHO/EXACTO/tesy-vertical-raw-evidence-20260924.tar.gz <<'BASH'
set -euo pipefail
BUNDLE="$1"
AUDIT_DIR="$PWD/research/external-audits/c3-raw-20260925"
PYTHON="${AUDIT_PYTHON:-python3}"
WORK="$(mktemp -d /tmp/tesy-external-audit.XXXXXX)"

"$PYTHON" -c 'import numpy'
cat "$AUDIT_DIR/audit_bundle.part1.txt" \
    "$AUDIT_DIR/audit_bundle.part2.txt" \
    "$AUDIT_DIR/audit_bundle.part3.txt" > "$WORK/audit_bundle.py"
cp "$AUDIT_DIR/test_audit_bundle.py.txt" "$WORK/test_audit_bundle.py"

"$PYTHON" - "$WORK" <<'PY'
import hashlib
import sys
from pathlib import Path
root = Path(sys.argv[1])
expected = {
    'audit_bundle.py': 'dbcc3c5ef16c41b0c9433006c817e59b9ce2227fbd2e00fe4dfc1978a36f34d3',
    'test_audit_bundle.py': 'bd106f19aaaa841a48a8bcbf3403e01e86720370cc232bb6e1c733d268b6526e',
}
for name, digest in expected.items():
    actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f'audit source hash mismatch: {name}')
PY

OPENBLAS_NUM_THREADS=1 "$PYTHON" "$WORK/audit_bundle.py" \
    "$BUNDLE" "$WORK/audit-results.json"
TESY_EVIDENCE_BUNDLE="$BUNDLE" OPENBLAS_NUM_THREADS=1 \
    "$PYTHON" "$WORK/test_audit_bundle.py"
printf 'AUDIT_OUTPUT=%s\n' "$WORK/audit-results.json"
BASH
```

Os cálculos são refeitos em float64. Últimos bits de reduções NumPy podem depender da implementação BLAS; preservar o ambiente e reportar diferenças, em vez de alterar thresholds. Na sessão de publicação o JSON completo recomputado foi igual ao original como objecto e os 12 testes passaram novamente.

## Âmbito e coordenação

Não mudar `research/coordination/CURRENT.json` do Codex nem a flag global de auditoria na branch em desenvolvimento. Esta revisão fecha apenas os âmbitos declarados no relatório; não é aprovação integral do runtime nem certificação dos binários não distribuídos.

A branch desta publicação é isolada: `audit/c3-raw-evidence-external-20260925`, baseada em `ca532aaa765ad551dcb8be4424f0abe6778eec96`. Não houve merge, force-push, alteração de base de PR ou escrita nas branches do Codex. A ligação formal desta unidade à governação/PR stack não foi executada nesta sessão: a ferramenta oficial de stacks não está exposta no conector e não existe CLI autenticada no ambiente. Não criar automaticamente uma PR acima da #34 com esta branch antiga: isso requer transportar apenas o delta de auditoria para a base adequada.

A revisão do N2 posterior é separada em `../N2-EXTERNAL-REVIEW-20260925.md`. Não reescreve o âmbito histórico da auditoria C3.
