# As leituras por intervalo anteciparam a entrega do gate à RTX

**GO para medir gate, up e down na mesma camada.** No prefill fornecido C110, os 215 913 600 B selecionados do gate chegaram à GPU 52,053 e 59,247 ms mais cedo nas duas ordens, com menos 302 473 216 B de leituras do NVMe por braço. A intervenção lê diretamente do GGUF para scratch paginável com `pread` e `POSIX_FADV_RANDOM` no fd. A margem para custos adicionais antes de perder o ganho é de 52,053 ms no par mais apertado. A experiência anterior observou um NO_GO quando o scratch era preenchido a partir do mmap por memcpy. [Pré-registo](read-protocol.md) · [Primeira comparação](README.md) · [Dados em ns e bytes](read-result.json)

| Ordem | Braço | Serviço até à barreira, ms | Preparar origem, ms | Submeter H2D, ms | Drain, ms | Leituras PID e cgroup, MB | Namespace na barreira → corte tardio, MB |
|---|---|---:|---:|---:|---:|---:|---:|
| Direto primeiro | DIRECT | 187,063 | 0,057 | 186,842 | 0,036 | 518,525 | 512,627 → 518,525 |
| Direto primeiro | PREAD_SEQ | 147,557 | 131,016 | 16,379 | 0,085 | 342,278 | 342,278 → 342,327 |
| Direto primeiro | PREAD_RANDOM | 135,010 | 119,475 | 15,394 | 0,090 | 216,052 | 216,052 → 216,052 |
| Random primeiro | PREAD_RANDOM | 133,354 | 117,572 | 15,644 | 0,080 | 216,052 | 216,052 → 216,052 |
| Random primeiro | PREAD_SEQ | 153,647 | 137,287 | 16,214 | 0,086 | 342,278 | 342,278 → 342,278 |
| Random primeiro | DIRECT | 192,600 | 0,042 | 192,380 | 0,045 | 518,525 | 512,102 → 518,525 |

MEDIDO. Mantendo o conselho SEQUENTIAL, trocar a origem CUDA do mmap por `pread` para scratch poupou 39,506 e 38,953 ms. Mantendo a leitura explícita e alterando só o conselho, pouparam-se mais 12,547 e 20,293 ms. A soma de cada par de contrastes adjacentes é o ganho do candidato nesse processo. PREAD_SEQ ocupou a posição intermédia em ambos. Os seis braços começaram com zero páginas residentes na matriz. PREAD_RANDOM terminou com 52 747 páginas, o equivalente a 216 051 712 B. Os 33 destinos e as guardas coincidiram em cada braço. O denominador foi uma matriz e 49 experts numa seleção fornecida. O efeito no primeiro conteúdo final e no decode permanece DESCONHECIDO.

No portátil, a fonte física foi `a2b80549824eb14252cbf83785ffc008f56d058b`, o pré-registo `71324f20` e a referência CPU a do lote 145. Os dois C118 recolheram 61 amostras cada em 60,164 e 60,172 s. Os processos duraram 2,228 e 2,254 s e atingiram 308 MiB de VRAM. O scope atingiu 862 842 880 B, sem swap, e fechou com a RTX em 2 MiB. Zero forwards, pedidos de conversa e downloads. Energia integrada DESCONHECIDA. Os originais e o lote 146 produziram o mesmo relatório. [Recibo de 23 ficheiros e 234 340 B](../../../private_archive/part-146.json)

```sh
d=research/qualification-retake/ik_mapped_experts/hybrid/cold_gate
family="$ARCHIVE/part-146/tesy-ik-cold-gate-ranges-20261126-r01"
reference="$ARCHIVE/part-145/tesy-ik-cold-gate-reference-20261126-r01/receipt.json"
python3 -IB "$d/grade.py" --family "$family" --reference "$reference" \
  --family-sha256 5e352cfbcc56e1e7978e798384e9a8f1c7d18a366ab81e787540e3d2937d27a3 \
  --new-output-dir "$NEW"
```
