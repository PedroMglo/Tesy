# Primeiro teste do Tesy no portátil

Data: 2026-09-23

Este guia executa apenas o primeiro bring-up diagnóstico. Não é ainda um
benchmark de Tesy nem um teste do gpt-oss-120b.

## 1. Checkout

```bash
git clone https://github.com/PedroMglo/Tesy.git
cd Tesy
git switch research/novelty-runtime-foundation-20260923
git status --short --branch
```

O worktree deve estar limpo.

## 2. Ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
ruff check .
pytest -q
```

Não instales vLLM nesta venv nesta fase. O vLLM é o baseline B4 e terá ambiente
isolado caso seja admitido após B0/B1/B2.

## 3. Verificar o host

```bash
tesy doctor --reference-profile configs/reference-host.json
```

Tem de terminar com `reference_check.status = PASS`.

O snapshot também guarda:
- RAM/swap;
- GPU/driver/temperatura;
- processos CUDA visíveis;
- CUDA toolkit;
- capacidade do filesystem;
- `lsblk` e `findmnt` para o path observado.

Um PASS de identidade não significa que a máquina esteja livre para timing.

## 4. Instalar apenas o primeiro modelo

Segue `MODELOS_A_INSTALAR.md`.

Resumo do artefacto congelado:

```text
repo:     ggml-org/gpt-oss-20b-GGUF
revision: a7443ebb00ba299cbbbf7e9b69487670447ae8c0
file:     gpt-oss-20b-mxfp4.gguf
bytes:    12,109,564,352
sha256:   52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4
```

Não descarregues ainda Qwen3-30B-A3B nem gpt-oss-120b.

## 5. Executar o bring-up

Escolhe um output novo. Exemplo:

```bash
campaign="results/bringup-$(date -u +%Y%m%dT%H%M%SZ)"

bash scripts/run_reference_bringup.sh \
  ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  "$campaign"
```

O runner é no-replace: se o directório existir, termina.

Ordem:
1. confirma HEAD/worktree;
2. confirma hardware de referência;
3. verifica filename/bytes/SHA do modelo;
4. produz capacity preflight;
5. faz checkout/build do llama.cpp pinado;
6. compila o tracer passivo;
7. instala o `gguf-py` do mesmo pin na venv;
8. executa stock smoke;
9. executa trace OFF/ON e compara token IDs;
10. valida a estrutura dos graph-seqs;
11. produz count-space LRU/Belady;
12. deriva o inventário GGUF de payload por expert.

O paired tracer começa com `TESY_TRACE_NGL=0` para testar a instrumentação sem
arriscar full-GPU OOM. Isto não é o trace representativo final do target
híbrido.

## 6. Não alterar a campanha depois do resultado

Se falhar:
- não apagues o output;
- não executes novamente com o mesmo campaign id;
- não alteres modelo/flags e chames ao resultado uma repetição;
- preserva o directório e cria uma campanha de debugging nova.

## 7. Resultado que procuro primeiro

Um bring-up diagnóstico saudável termina com:

```text
PASS_DIAGNOSTIC_STOCK_SMOKE
PASS_DIAGNOSTIC_TRACE_TOKEN_EQUALITY
PASS_DIAGNOSTIC_REFERENCE_BRINGUP_PIPELINE
```

Isto **não** significa que o Tesy é mais rápido.

Depois do bring-up, a primeira decisão científica usa:
- routing trace;
- consistência dos graph-seqs;
- LRU vs Belady count-space;
- bytes codificados por expert;
- capacidade real restante da máquina.

Só depois congelamos capacidades para a simulação byte-weighted e decidimos
se vale a pena escrever uma cache nativa, estudar CPU-resident experts ou
mudar de backend.

## 8. vLLM

Não é ignorado.

Está pinado como B4 comparator porque tem um runtime de serving/offload forte,
mas ainda não foi demonstrado que é a melhor boundary para 8 GiB VRAM,
32 GiB RAM e eventual modelo >RAM.

Será testado num ambiente isolado se:
- o target/quantização comparável for suportado;
- couber no envelope real;
- o overhead da stack não o tornar inelegível;
- a comparação conseguir manter target/workload suficientemente equivalentes.

Não se muda para vLLM por reputação; muda-se se os dados o justificarem.
