# Modelos a instalar para o Tesy

Data de corte: 2026-09-23

Não descarregues todos os modelos. O Tesy ainda está em bring-up/trace e um download grande não é evidência científica.

## 1. Instalar agora: gpt-oss-20b MXFP4 GGUF

Este é o único download obrigatório nesta fase.

Motivos:
- MoE real e suficientemente pequeno para o primeiro bring-up;
- 20.91B parâmetros totais e aproximadamente 3.61B ativos por token;
- 24 layers, 32 experts e 4 experts ativos por token;
- MXFP4;
- licença Apache-2.0;
- o artefacto congelado tem 12,109,564,352 bytes e cabe nos 32 GiB do host.

Caber em RAM significa que este modelo não prova a rota >RAM. É o target de instrumentação, baseline e routing.

### Artefacto congelado

Repository:
ggml-org/gpt-oss-20b-GGUF

Revision:
a7443ebb00ba299cbbbf7e9b69487670447ae8c0

Ficheiro:
gpt-oss-20b-mxfp4.gguf

Bytes:
12,109,564,352

SHA-256:
52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4

A identidade e o byte-count vêm do LFS pointer do upload congelado.

### Download

python -m pip install -U huggingface_hub

mkdir -p ~/.local/share/tesy/models/gpt-oss-20b

hf download ggml-org/gpt-oss-20b-GGUF \
  gpt-oss-20b-mxfp4.gguf \
  --revision a7443ebb00ba299cbbbf7e9b69487670447ae8c0 \
  --local-dir ~/.local/share/tesy/models/gpt-oss-20b

Não descarregues o repositório inteiro.

### Verificação

sha256sum ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf

tesy models verify gpt-oss-20b-mxfp4-gguf \
  ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf

tesy plan --model gpt-oss-20b-mxfp4-gguf \
  --path ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf

### Harmony

GPT-OSS foi treinado para o formato Harmony. O primeiro tracer nativo Tesy usa raw text apenas para diagnóstico de routing. Não uses esse raw trace como avaliação de qualidade conversacional.

Fontes:
- https://openai.com/index/introducing-gpt-oss/
- https://huggingface.co/openai/gpt-oss-20b/blob/main/config.json
- https://huggingface.co/ggml-org/gpt-oss-20b-GGUF/blob/a7443ebb00ba299cbbbf7e9b69487670447ae8c0/gpt-oss-20b-mxfp4.gguf
- https://huggingface.co/ggml-org/gpt-oss-20b-GGUF/commit/8153e856b2e87ef0f579525b57ea21205734cf9c

## 2. Segundo modelo: Qwen3-30B-A3B-Instruct-2507

Não instalar ainda para a campanha Tesy.

É um segundo target interessante porque tem:
- 30.5B parâmetros totais;
- 3.3B ativos;
- 48 layers;
- 128 experts;
- 8 experts ativos por token;
- arquitetura qwen3_moe;
- Apache-2.0.

O maior número de experts é útil para locality, reuse distance e working-set union.

Antes de um download de campanha, Tesy ainda precisa congelar:
1. repositório GGUF;
2. revision imutável;
3. SHA-256;
4. byte-count;
5. backend pin compatível.

Upstream:
https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507

## 3. Escala futura: gpt-oss-120b

NÃO DESCARREGAR NESTA FASE.

A OpenAI documenta aproximadamente:
- 116.83B parâmetros totais;
- 5.13B ativos;
- 36 layers;
- 128 experts;
- top-4;
- checkpoint na ordem de 60.8 GiB.

É o tipo de target que força a pergunta >RAM no portátil. Só é admitido depois de existir:
- routing evidence em modelos menores;
- loader que não materialize todos os experts em RAM;
- modelo de capacidade NVMe -> RAM -> VRAM;
- roofline plausível;
- proteção contra OOM/swap storm;
- baseline relevante;
- smoke compatível.

## Ordem atual

1. gpt-oss-20b MXFP4 GGUF — instalar agora.
2. Qwen3-30B-A3B-Instruct — congelar artefacto antes de instalar.
3. gpt-oss-120b — metadata-only; não instalar.

A ordem pode mudar prospetivamente se a evidência mostrar um discriminador melhor.
