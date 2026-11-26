# A atenção da camada 25 diverge antes da projeção

**MEDIDO e REPRODUZIDO no portátil.** Usámos o mesmo driver 620.73.04, executável, backend, opção de router e GGUF original nos dois braços. Na execução serial (AR) e no bloco de três posições (B3), os bytes das três máscaras efetivas de atenção são iguais. Todas as 12 288 palavras F32 já diferem à saída de `FLASH_ATTN_EXT`, antes de aplicar o peso de projeção. As 8 640 palavras observadas após a projeção e o bias também diferem. Uma correção limitada à projeção deixaria a saída anterior divergente. [Resultados e SHA por linha](result.json) · [Protocolo](protocol.md)

| Posição | Células visíveis / físicas | Diferenças na máscara F16 | F32 diferentes antes da projeção | F32 diferentes depois |
|---:|---:|---:|---:|---:|
| 189 | 190 / 256 | 0 | 4 096 / 4 096 | 2 880 / 2 880 |
| 190 | 191 / 256 | 0 | 4 096 / 4 096 | 2 880 / 2 880 |
| 191 | 192 / 256 | 0 | 4 096 / 4 096 | 2 880 / 2 880 |

Cada geometria preservou os seus 1 182 payloads anteriores, 2 248 ficheiros de prefill, estados de KV e cinco vetores completos e finitos de 201 088 logits. O KV e o pool iniciais também coincidem entre geometrias. Os Q pós-RoPE, K e V atuais já coincidiam nas três posições. Falta identificar causalmente a operação que produz esta diferença com os mesmos operandos efetivamente lidos. A máscara e o snapshot lógico delimitam a reconstrução do KV. O log físico atribui L25 à CUDA0 e regista KV F16. O seletor CUDA no pin C269 contém caminhos distintos para largura um e três nesta geometria. Essa seleção é uma inferência do código. [Controlos anteriores](../README.md)

| Braço | Processo com captura | Scope incluindo C118 | VRAM pico | Cgroup pico | Swap | Energia GPU estimada / intervalo coberto |
|---|---:|---:|---:|---:|---:|---:|
| AR | 28,152 s | 88,945 s | 6 880 MiB | 15 854 141 440 B | 0 | 325,8 J / 27,458 s |
| B3 | 28,234 s | 88,981 s | 6 868 MiB | 16 012 464 128 B | 0 | 326,5 J / 27,525 s |

Houve dois arranques do 120B, zero pedidos HTTP, 61 amostras C118 e 109 verificações de mapeamentos por braço. Os dois scopes terminaram. Máximos de 72,0 °C CPU, 52,15 °C GPU e 46,85 °C NVMe. A energia do portátil permanece desconhecida. Estes relógios incluem observação síncrona e trabalho fornecido. A melhor conversa emparelhada mantém 18,313 s até ao primeiro final e 5,361 tok/s. M3 PARTIAL, M4 NOT_MET.

**Decisão de engenharia.** GO para reconstituir esta atenção com o KV e Q capturados, comparar cada geometria com as suas saídas reais e testar a divisão local da query em três vistas. A decisão sobre B3 no produto permanece INCONCLUSIVE. A família física em `96a8fa0e` e o protocolo em `63c67374` são anteriores ao resultado. As revisões independentes dos originais e da parte 165 deram SHA-256 `b8678e61154755cb2f95d2de74bfa34d1260b39d50cfa52fcd9dff66cd6bde97`. [Manifesto privado](../../../../../../../../private_archive/part-165.json) · [Revisor sem GPU](review.py)

```sh
python3 -IB review.py --archive "$ARCHIVE" --reference "$C270_ATUAL" --serial "$AR_ANTERIOR" \
  --family "$PAR" --build "$BUILD" --window "$C55" \
  --receipt-sha256 72819fc1e0f5c31b688c81d554e22693b04ba29feb26d8303253bdc1ec9af777 --new-output-dir "$NEW"
```
