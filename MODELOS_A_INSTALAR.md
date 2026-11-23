# Modelos e artefactos do Tesy

A instalação no portátil requer uma verificação local. Uma entrada no inventário regista a identidade histórica do artefacto e o âmbito para que foi qualificado. A próxima tarefa de análise de C317 requer apenas os journals.

| Uso | Artefacto | Revisão e SHA-256 |
|---|---|---|
| Controlo operacional R0, opt-in | GPT-OSS-120B MXFP4 GGUF, 63 387 346 208 B | `238abdd290bb874b90a5da1b4549881b7d05c091` · `582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d` |
| Bring-up 20B, tracer e baselines da fundação | GPT-OSS-20B MXFP4 GGUF, 12 109 564 352 B | `a7443ebb00ba299cbbbf7e9b69487670447ae8c0` · `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4` |

O [lock do laboratório](models.lock.json) alimenta o runtime experimental e inclui os candidatos auxiliares com o seu estado. O [lock do CLI da fundação](configs/models.lock.json) mantém o seu schema e os consumidores do 20B. Qualquer modelo novo exige artefacto, revisão e SHA congelados e admissão de capacidade. Os pesos e os builds ficam fora do Git. A obtenção de modelos grandes requer autorização explícita.

As instruções originais, incluindo caminhos históricos e as condições aplicáveis à época, estão no [guia de bring-up 20B](https://github.com/PedroMglo/Tesy/blob/7a7d3dcbd1ff8e594ac57459c3db06306083c3ca/MODELOS_A_INSTALAR.md) e no [guia do laboratório 120B](https://github.com/PedroMglo/Tesy/blob/623a5b97b6e14a39bc671f6d81e7a993a3efe7cb/MODELOS_A_INSTALAR.md).
