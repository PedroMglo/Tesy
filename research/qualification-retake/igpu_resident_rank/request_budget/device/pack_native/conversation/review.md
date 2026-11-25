# Reabrir a conversa com o pack

Os quatro servidores completaram a mesma conversa C281 de dois turnos. Em cada T2 foram reutilizados 2044 IDs, processados 153 e gerados 47. BASE atingiu **18,159 s até ao primeiro conteúdo final e 5,326 tok/s**. Com escrita do journal, ON atingiu **18,326 s e 5,253 tok/s**. Os doze rácios T2 ficaram entre 0,995258 e 1,013198, dentro da banda pré-registada de 0,85 a 1,15. Cada modo tem uma única medição na ordem BASE, CONTROL, OFF, ON. [Recibo reproduzido](evidence/review.json)

| Braço | Turno | Primeiro final (s) | Fim do stream (s) | Validado (s) | Prefill (s) | Decode (s) | Outputs/s |
|---|---|---:|---:|---:|---:|---:|---:|
| BASE | T1 | 75,397 | 75,772 | 75,775 | 58,111 | 17,650 | 4,419 |
| CONTROL | T1 | 76,060 | 76,453 | 76,456 | 58,715 | 17,727 | 4,400 |
| OFF | T1 | 76,148 | 76,534 | 76,536 | 58,730 | 17,792 | 4,384 |
| ON | T1 | 75,813 | 76,186 | 76,189 | 58,489 | 17,688 | 4,410 |
| BASE | T2 | 18,159 | 18,401 | 18,403 | 9,564 | 8,825 | 5,326 |
| CONTROL | T2 | 18,179 | 18,429 | 18,432 | 9,521 | 8,898 | 5,282 |
| OFF | T2 | 18,270 | 18,512 | 18,515 | 9,646 | 8,856 | 5,307 |
| ON | T2 | 18,326 | 18,570 | 18,573 | 9,611 | 8,947 | 5,253 |

Os 78 e 47 IDs gerados e os 71 e 40 frames SSE, respetivamente em T1 e T2, reproduziram a referência em todos os braços. O journal ON cobriu os 7012 vetores ordenados de top-4 ao longo de 48 chamadas. A primeira tratou 5 posições, a segunda 148 em cinco tiles e seguiram-se 46 avaliações de uma posição. As 2354 reservas observadas chegaram a publicação, com 31 124 324 352 B pedidos e devolvidos e 7062 SET que copiaram 31 117 996 800 B. Houve zero novas tentativas, erros ou gerações pendentes no fim. [Identidades e contagens por fase](evidence/review.json)

As callbacks de remapeamento cobriram 5,899 s da parede de prefill e 6,668 s do decode de ON. Mantendo constante o trabalho exterior e concedendo antes do primeiro final toda a poupança de acelerar o decode a 6 outputs/s, faltariam **1,313 s** mesmo com as callbacks de prefill gratuitas. O ponto de equilíbrio desse cenário é **7,209 outputs/s**. A 8 e 10 outputs/s, as margens para retenção de trabalho dentro das callbacks de prefill ou nova coordenação são, respetivamente, **0,645 e 1,820 s**. A última utilização na CUDA e a exposição do trabalho numa agenda alterada continuam sem instante medido. [Uniões observadas e cenários condicionais](evidence/review.json)

| Braço | Janela C118 (s) | READY (s) | Envelope (s) | Pós-cliente até limpeza (s) | Pico cgroup (B) | GPU estimada (J) | Cobertura de potência (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| BASE | 60,182 | 4,098 | 160,958 | 1,069 | 15 780 089 856 | 1349,3 | 98,385 |
| CONTROL | 60,143 | 4,066 | 161,416 | 0,933 | 16 346 222 592 | 1373,9 | 99,197 |
| OFF | 60,164 | 4,071 | 161,932 | 1,239 | 15 832 444 928 | 1351,7 | 99,271 |
| ON | 60,144 | 4,066 | 161,433 | 1,053 | 16 022 245 376 | 1357,5 | 98,757 |

A família durou 817,038 s. As esperas pelo bind da porta duraram 63,607, 63,617 e 42,402 s. Os quatro servidores saíram com código zero, swap zero e pico de 6848 MiB de VRAM. A C55 precedente cobriu 60,010 s em 61 amostras, com capacidade admitida de 23 353 884 672 B; cada filho usou o envelope E20. A primeira reprodução usou a família original e a segunda reabriu a parte 97. Os dois recibos de 20 187 B coincidiram byte a byte. [Proveniência das reproduções](evidence/reproductions.json)

O revisor volta a ler os dois turnos de cada servidor. Confronta o log de amostragem, os ecos enviados à avaliação seguinte, os frames SSE, os resultados aceites e os tempos publicados com o C281 histórico. Valida em cada processo as bibliotecas mapeadas, os descritores de dados, os limites do cgroup, a C118 e a saída do servidor. Confere também os três intervalos de espera pela porta. No braço ON recalcula a geometria, os ranks, as reservas, as publicações, os serviços do pack e o instante de corte HTTP pelo mesmo auditor congelado para a aquisição. [Contrato da família](protocol.md) · [Auditor do journal](../natural_trace/analyse.py)

A linha abaixo usa a cópia integral da medição. `RESULT` deve designar um diretório novo. A execução exige Python 3 e os fontes da revisão de medição. Os dados do modelo ficam fora do caminho de leitura.

```bash
D=research/qualification-retake/igpu_resident_rank/request_budget/device/pack_native/conversation
ARCHIVE=/mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01
FAMILY_SHA256=e5012e559a2403145abc6f5317bddc8b83f95f1e09b592eb83a6baa2c18980a9
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
