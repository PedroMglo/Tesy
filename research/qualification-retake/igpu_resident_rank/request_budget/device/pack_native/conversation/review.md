# Reabrir a conversa com o pack

O revisor volta a ler os dois turnos de cada servidor. Confronta o log de amostragem, os ecos enviados à avaliação seguinte, os frames SSE, os resultados aceites e os tempos publicados com o C281 histórico. Valida em cada processo as bibliotecas mapeadas, os descritores de dados, os limites do cgroup, a C118 e a saída do servidor. Confere também os três intervalos de espera pela porta. No braço ON recalcula a geometria, os ranks, as reservas, as publicações, os serviços do pack e o instante de corte HTTP pelo mesmo auditor congelado para a aquisição. [Contrato da família](protocol.md) · [Auditor do journal](../natural_trace/analyse.py)

A linha abaixo usa a cópia integral da medição. `FAMILY_SHA256` é o SHA do ficheiro `family.json` validado pelo manifesto da parte 97. `RESULT` deve designar um diretório novo. A execução exige Python 3 e os fontes da revisão de medição. Os dados do modelo ficam fora do caminho de leitura.

```bash
D=research/qualification-retake/igpu_resident_rank/request_budget/device/pack_native/conversation
ARCHIVE=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01
python3 -IB "$D/review.py" \
  --family "$ARCHIVE/part-97/tesy-c281-pack-observer-natural-20261125-r01" \
  --family-sha256 "$FAMILY_SHA256" \
  --prepared "$ARCHIVE/part-96/tesy-c281-pack-observer-prepared-20261125-r01" \
  --window "$ARCHIVE/part-96/tesy-c281-pack-observer-c55-20261125-r01" \
  --build "$ARCHIVE/part-93/tesy-c291-pack-pfj-dso-20261125-r02" \
  --history "$ARCHIVE/part-23/tesy-c281-driver-20261125-r01" \
  --new-output-dir "$RESULT"
```

`first_final_s` mede do início do pedido até ao primeiro fragmento de conteúdo final do cliente. `transport_complete_s` termina no fecho do stream, e `validated_terminal_s` inclui o trabalho até à validação registada pelo cliente. `prefill_s` e `decode_s` vêm dos dois temporizadores do servidor. A taxa contratual de T2 usa os 47 outputs e o tempo nativo de decode; a reconstrução do grafo também identifica as 46 avaliações posteriores ao primeiro output. A soma dos relógios do servidor e do cliente contaria parte do trabalho duas vezes. [Definições do cliente](../../../../../packed_nvme_manifest/server_profile/conversation/review.py)

`ready_s` começa no Popen. O envelope de cada braço inclui a C118 de 60 s e a verificação final de limpeza. `energy.estimated_gpu_j` integra por trapézios as amostras de potência da GPU obtidas entre a primeira e a última observação do monitor. O recibo inclui cobertura, intervalo máximo sem amostra, máximos de VRAM, RAM e temperatura por braço. A energia de todo o portátil permanece desconhecida. Os relógios do PFJ usam os limites das callbacks do host e os serviços de cada worker. A duração observada no regresso de um SET CUDA só localiza a conclusão no host. [Gates de recurso e relógios](../../../../../packed_nvme_manifest/server_profile/conversation/protocol.md)
