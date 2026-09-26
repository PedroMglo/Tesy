# Artefactos da campanha scale lab

O 20B MXFP4 GGUF está instalado e teve SHA-256 verificado. O 120B nativo MXFP4 em sete shards safetensors também está no NVMe local, mas o backend de expert streaming escolhido carrega GGUF e não foi validado com esse formato nativo. Nenhum peso foi descarregado ou convertido nesta campanha.

Para o próximo gate M4, os metadados públicos consultados em 2026-09-26 via `hf models info/list` identificam:

- Repositório: `ggml-org/gpt-oss-120b-GGUF`
- Revisão imutável: `238abdd290bb874b90a5da1b4549881b7d05c091`
- Ficheiro: `gpt-oss-120b-MXFP4.gguf`
- Tamanho publicado: 63,387,346,208 bytes (59.04 GiB)
- SHA-256 LFS publicado: `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`
- Estado local: **ausente**; compatibilidade em execução com o candidato ainda não demonstrada.

Quando o utilizador decidir instalar este artefacto, o comando de obtenção identificado pelos metadados é:

```bash
hf download ggml-org/gpt-oss-120b-GGUF gpt-oss-120b-MXFP4.gguf \
  --revision 238abdd290bb874b90a5da1b4549881b7d05c091 \
  --local-dir /home/pmglo/models/gpt-oss-120b-gguf
sha256sum /home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf
```

O comando não foi executado. O download tem de ser seguido de verificação de SHA-256 contra o valor acima antes de qualquer run. Metadados da origem estão em `results/hf-gpt-oss-120b-gguf-*.json`.
