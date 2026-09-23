# Modelos a instalar — Tesy

Data: 2026-09-23. **Instala apenas o primeiro modelo nesta fase.**
Não é necessário instalar dense 32B/72B nem artefactos de outro projeto.
Não foi descarregado, aberto ou testado nenhum LLM nesta sessão.

## 1. Primeiro candidato: Qwen3-30B-A3B-Instruct-2507 Q4_K_M

Modelo MoE não-thinking. A documentação do autor indica 30,5B parâmetros totais,
3,3B ativos, 48 layers, 128 experts e 8 experts selecionados. Estas contagens
não são bytes transferidos, nem comprovam um working set pequeno por sessão.

- Upstream: https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507
- Artefacto quantizado: https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF
- Quantizador: Unsloth, não o autor original Qwen.
- Revisão do commit que publica o ficheiro:
  `3e33891b69c55d54a284d3e3e3d1abca5499f5f6`.
- Um único ficheiro: `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf`.
- Bytes exatos do pointer publicado: **18 556 686 752** (~17,28 GiB).
- SHA-256 publicado: `6c997b8af17debdfb01d890214400ccbab00db6acc0ba8da5de1cc906c4774d0`.
- Quantização: Q4_K_M; não descarregar todas as quantizações nem BF16.
- Arquitetura GGUF esperada: `qwen3moe`.
- Licença declarada nas páginas upstream e quantizada: Apache-2.0;
  conserva os termos/avisos associados ao download.
- Tokenizer e chat template: usar os incluídos no GGUF, sem os substituir por
  ficheiros de outra variante. O backend stock aplica o template.
- Estado Tesy: METADATA_VERIFIED_REAL_MODEL_NOT_RUN. Não há throughput prometido.

Fontes do identificador/bytes/hash:
https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/commit/3e33891b69c55d54a284d3e3e3d1abca5499f5f6
https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/raw/main/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf

A revisão e o SHA do artefacto estão fixados em `configs/models.lock.json`.
O pointer publicado em `main` foi observado nesta data; o download usa a revisão
fixa e a verificação do hash falha se os bytes dessa revisão não corresponderem.
Não se trata de um hash local já reproduzido pelo Tesy.

### Disco e memória

Planeamento, NÃO medição: reserva pelo menos 40 GiB livres no disco de download
para ficheiro, cache/temporários e margem. Algumas configurações da cache de
Hugging Face podem exigir mais; verifica os paths e utilização efetivos.
A compilação do backend usa espaço adicional e não está incluída nos bytes GGUF.

O ficheiro tem ~17,28 GiB, mas o processo pode usar mais RAM por reformatting,
page cache e buffers. VRAM depende de placement, KV, scratch e ambiente gráfico.
Não assumes que 3,3B ativos correspondem à RAM necessária. `tesy chat --execute`
faz preflight de memória e amostragem de guards; isso não é reserva de memória
nem garantia contra OOM. Contexto inicial: **4096**, uma sessão, até 128 tokens
por resposta, sem speculation. Fecha workloads pesados antes do smoke.

### Preparação

Na raiz do checkout, ativa o ambiente conforme README. Instala o cliente Hugging
Face pelo procedimento oficial adequado ao teu ambiente; o executável `hf` deve
estar disponível. Não passes tokens de autenticação ao Tesy nem os graves no repo.
O artefacto observado é público; o script não gere credenciais.

```bash
MODEL_DIR="$HOME/.local/share/tesy/models"
mkdir -p "$MODEL_DIR"
df -h "$MODEL_DIR"
tesy doctor
tesy models download-plan --id qwen3-30b-a3b-2507-q4km "$MODEL_DIR"
```

O último comando apenas mostra o plano. Para descarregar exclusivamente o GGUF:

```bash
hf download unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF \
  Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf \
  --revision 3e33891b69c55d54a284d3e3e3d1abca5499f5f6 \
  --local-dir "$MODEL_DIR"
MODEL="$MODEL_DIR/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"
tesy models inspect "$MODEL"
tesy models verify --id qwen3-30b-a3b-2507-q4km "$MODEL"
```

A verificação faz SHA completo em streaming, não carrega o modelo. Paths com
symlinks são rejeitados: usa o ficheiro regular produzido por `--local-dir`.
Erro de tamanho/hash/arquitetura termina a admissão; não contornes o erro.

### Backend e primeira conversa

Pin independente do Tesy: llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`.
Foi observado no GitHub; o build externo não foi executado aqui por ausência de
fonte acessível no container, nvcc e GPU. Este pin ainda não é um build qualificado.
O teu ambiente precisa de CMake, compilador C++ e CUDA/nvcc compatível com driver.
Não alteres o driver automaticamente só para cumprir este guia.

```bash
bash scripts/build_stock.sh
BIN="third_party/llama.cpp/build-tesy/bin/llama-cli"
ldd "$BIN"
"$BIN" --version
tesy chat --model "$MODEL" --llama-cli "$BIN"
# Confirmado o plano, inicia explicitamente uma sessão stock supervisionada:
tesy chat --model "$MODEL" --llama-cli "$BIN" --execute --seconds 600
```

O script recusa sobrescrever um checkout anterior. Se falhar, preserva o checkout
parcial e o erro para diagnóstico; não há retries automáticos ou mudança de pin.
O CLI usa o modelo por FD em Linux, mantendo o mesmo inode durante a execução.
A via foi testada com contratos/mocks, NÃO com este GGUF real.

**Esta conversa é stock llama.cpp, não aceleração Tesy.** A cache C++ desenvolvida
nesta fase ainda não intervém no caminho quantizado. Para um baseline CPU explícito,
adiciona `--cpu-only`. Não compares timings de perfis diferentes como se fossem
uma campanha controlada. O comando `tesy bench` ainda não existe.

## 2. Modelos posteriores: não instalar ainda

`gpt-oss-20b`, outras variantes Qwen MoE e modelos 100B+ podem ser avaliados depois.
Não existe nesta fase um profile lock testado para eles. Não forneço filenames,
revisões ou hashes por adivinhação. Não descarregues um 120B para descobrir que a
integração nativa ainda não existe. O suporte inicial é uma família, não todas.

O próximo guia de escala terá de confirmar suporte/quantização, total de shards,
licença, footprint real e custos NVMe/RAM/VRAM antes de admitir mais downloads.
Sucesso numa fixture F32 ou num modelo pequeno não qualifica os maiores.
