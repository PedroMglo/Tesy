# Artefactos da campanha scale lab

O 20B MXFP4 GGUF e o 120B MXFP4 GGUF estão instalados e tiveram SHA-256 completo verificado. O 120B nativo MXFP4 em sete shards safetensors também está no NVMe local, mas o backend de expert streaming escolhido carrega GGUF. Nenhum peso foi descarregado ou convertido por esta sessão do laboratório.

Os metadados públicos consultados em 2026-09-26 via `hf models info/list` identificam:

- Repositório: `ggml-org/gpt-oss-120b-GGUF`
- Revisão imutável: `238abdd290bb874b90a5da1b4549881b7d05c091`
- Ficheiro: `gpt-oss-120b-MXFP4.gguf`
- Tamanho publicado: 63,387,346,208 bytes (59.04 GiB)
- SHA-256 LFS publicado: `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`
- Estado local em 2026-09-26: **instalado** em `/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf`; tamanho e SHA-256 completo coincidem com os valores acima. O candidato executou o modelo sob 18 GiB/zero swap, dois pedidos distintos, três pares A/B de cache e dez tarefas num servidor contínuo de 22m22s. O decode agregado nesse servidor foi 2.733 tok/s, com cobertura numérica limitada à igualdade bitwise dos logits de um prefixo de quatro tokens e a uma comparação de 16/24 slots no mesmo prefixo. A tentativa posterior de referência para o prefixo Harmony completo parou no limite do cgroup antes de produzir logits; não alarga essa cobertura. As dez tarefas terminaram com 8/10, igual ao 20B stock. Ver `research/M4-RESULT-20260926.md`, `research/M5-SERVER-RESULT-20260926.md`, `research/M6-RESULT-20260926.md` e `research/M4-EXTENDED-PREFIX-RESULT-20260926.md`.

Comando de obtenção identificado pelos metadados, preservado apenas para reprodução futura; **não é necessário executar neste host**:

```bash
hf download ggml-org/gpt-oss-120b-GGUF gpt-oss-120b-MXFP4.gguf \
  --revision 238abdd290bb874b90a5da1b4549881b7d05c091 \
  --local-dir /home/pmglo/models/gpt-oss-120b-gguf
sha256sum /home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf
```

O comando acima não foi executado por esta sessão. Metadados da origem estão em `results/hf-gpt-oss-120b-gguf-*.json`.
