# Modelos a instalar para o Tesy

Data de corte: 2026-09-23

Este ficheiro é deliberadamente conservador. Não descarregues todos os modelos da lista. O Tesy ainda está na fase de bring-up/trace e um download grande não constitui progresso científico.

## 1. Instalar agora — gpt-oss-20b MXFP4 GGUF

Este é o **único download obrigatório nesta fase**.

Razões:
- MoE real e relativamente pequeno para o primeiro bring-up;
- 20.91B parâmetros totais e ~3.61B ativos por token segundo a documentação da OpenAI;
- 24 layers, 32 experts, 4 experts ativos por token;
- checkpoint nativo usa MXFP4 nos módulos MoE;
- o GGUF selecionado tem cerca de 12.1 GB e cabe confortavelmente nos 32 GiB do host, deixando margem para validar tracing e baseline antes de introduzir NVMe crítico;
- licença Apache-2.0;
- existe artefacto GGUF no ecossistema ggml/llama.cpp.

**Importante:** caber em RAM significa que este modelo não demonstra ainda a hipótese de modelo > RAM. É um target de engenharia e tracing.

### Artefacto congelado

Repository:

`ggml-org/gpt-oss-20b-GGUF`

Revision:

`a7443ebb00ba299cbbbf7e9b69487670447ae8c0`

Ficheiro:

`gpt-oss-20b-mxfp4.gguf`

SHA-256 esperado:

`52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`

A página do artefacto congelado reporta 12,109,564,352 bytes (~12.1 GB). Esse byte-count está agora fixado no lock juntamente com o SHA-256.

### Download

Primeiro instala o cliente, se necessário:

```bash
python -m pip install -U huggingface_hub
```

Usa um diretório próprio do Tesy:

```bash
mkdir -p ~/.local/share/tesy/models/gpt-oss-20b
hf download ggml-org/gpt-oss-20b-GGUF \
  gpt-oss-20b-mxfp4.gguf \
  --revision a7443ebb00ba299cbbbf7e9b69487670447ae8c0 \
  --local-dir ~/.local/share/tesy/models/gpt-oss-20b
```

Não uses download do repositório inteiro.

### Verificação

```bash
sha256sum ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf
tesy models verify gpt-oss-20b-mxfp4-gguf \
  ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf
tesy plan --model gpt-oss-20b-mxfp4-gguf \
  --path ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf
```

Não inicies um benchmark longo até `tesy doctor`, a build stock do backend e o smoke terem sido verificados.

### Formato de conversa

gpt-oss requer o formato Harmony. Não o substituas por ChatML ou por uma template improvisada. O backend selecionado deve aplicar a template/tokenizer corretos.

Fontes:
- https://openai.com/index/introducing-gpt-oss/
- https://huggingface.co/openai/gpt-oss-20b/blob/main/config.json
- https://huggingface.co/ggml-org/gpt-oss-20b-GGUF/blob/a7443ebb00ba299cbbbf7e9b69487670447ae8c0/gpt-oss-20b-mxfp4.gguf

---

## 2. Segundo modelo — Qwen3-30B-A3B-Instruct-2507

**Não instalar ainda para a campanha Tesy.**

Este modelo é um excelente segundo target porque apresenta:
- 30.5B parâmetros totais;
- 3.3B ativos;
- 48 layers;
- 128 experts;
- 8 experts ativos por token;
- arquitetura `qwen3_moe`;
- Apache-2.0.

Esse número maior de experts torna-o especialmente útil para estudar locality, reuse distance e working-set union.

Uma quantização Q4_K_M da comunidade reporta ~18.557 GB. Contudo, nesta data ainda não foi congelada no Tesy uma revision + SHA do artefacto GGUF. Por isso o model lock marca-o `CANDIDATE_ARTIFACT_NOT_LOCKED`.

Não transformes `main` num lock implícito. Antes do download de campanha:
1. escolher o repositório GGUF;
2. congelar revision imutável;
3. obter/verificar o SHA-256;
4. confirmar o commit mínimo de llama.cpp;
5. atualizar `configs/models.lock.json`.

Upstream:
https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507

---

## 3. Escala futura — gpt-oss-120b

**NÃO DESCARREGAR NESTA FASE.**

A OpenAI documenta aproximadamente:
- 116.83B parâmetros totais;
- 5.13B ativos;
- 36 layers;
- 128 experts;
- 4 experts ativos por token;
- checkpoint ~60.8 GiB.

É precisamente o tipo de modelo em que o total excede claramente a RAM disponível do portátil. Isso torna-o interessante para o objetivo final, mas também significa que um loader/runtime errado pode fazer dezenas de GiB de I/O inútil por geração.

O Tesy só o admite depois de:
- trace/caching em modelos menores;
- loader que não materialize todos os experts em RAM;
- modelo de capacidade NVMe->RAM->VRAM;
- static roofline plausível;
- política de falha antes de OOM/swap storm;
- smoke de backend compatível numa campanha separada.

Fontes:
- https://openai.com/index/introducing-gpt-oss/
- https://deploymentsafety.openai.com/gpt-oss/a2

---

## Ordem atual

```text
1. gpt-oss-20b MXFP4 GGUF       -> instalar agora
2. Qwen3-30B-A3B Instruct       -> lock do artefacto antes de instalar
3. gpt-oss-120b                 -> metadata-only; não instalar
```

Se evidência futura mostrar que outro MoE é um melhor discriminador, esta ordem pode mudar prospetivamente. Não se preserva um target só por sunk cost.
