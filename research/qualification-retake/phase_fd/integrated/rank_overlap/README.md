# Quanto ganha iniciar um rank enquanto os restantes esperam pelos pesos?

**NO_GO com os tempos de serviço de R0 nos dois pedidos nominais.** Mesmo permitindo que cada rank comece assim que as três componentes da sua geração ficam prontas, o primeiro conteúdo final demoraria pelo menos **17,553 s e 17,615 s** no modelo condicional. Nos 47 tokens de saída, o melhor decode admitido é aproximadamente **5,40 tok/s** em ambos. Medir este mecanismo no 120B como intervenção isolada não se justifica neste regime. [Critério prospetivo](protocol.md) · [Resultados por fase e dispositivo](evidence/receipt.json)

| Relógio do próprio T2 | Parte 37 | Parte 40 |
|---|---:|---:|
| Primeiro conteúdo final observado | 20,486 s | 20,540 s |
| Máximo recuperável até ao primeiro final, só ranks residentes à entrada da wave | 2,913 s | 2,908 s |
| Máximo recuperável, incluindo a chegada progressiva das gerações | 2,931 s | 2,924 s |
| Parcela deste máximo em camadas com experts CPU / CUDA | 2,548 / 0,383 s | 2,543 / 0,381 s |
| Máximo recuperável no prefill 5 / 148 | 0,128 / 1,531 s | 0,131 / 1,533 s |
| Máximo recuperável nas 46 avaliações AR | 1,305 s | 1,295 s |
| Decode restante para as 47 saídas do contador de produto | 8,699 s | 8,699 s |
| Redução adicional ainda necessária para 10 s / 6 tok/s | 7,553 s / 865,5 ms | 7,615 s / 865,2 ms |

Em 1 006 e 1 005 waves até ao primeiro final havia trabalho de um rank potencialmente antecipável. A diferença entre a primeira e a última disponibilidade dos pesos somava 14,268 e 14,305 s. Em grande parte dessa espera, o cálculo da própria wave já tinha um limite posterior muito curto. Na mesma tile, o próximo remap precisa da acumulação anterior ou do router da camada seguinte. Concedemos como cálculo adiantável **todo o período entre o regresso do remap e essa próxima dependência**, incluindo outros operadores, transferências e coordenação. A poupança é limitada pelo menor entre esse período e a janela de disponibilidade. Sem dependência comprovada dentro da tile, concedemos toda a janela dos pesos. Cada callback aparece uma vez em cada denominador. Prefill, decode completo e janela do primeiro final interceptam-se e as suas poupanças não se somam.

O trabalho real foi 5+148 novos IDs e 46 avaliações AR após o ID inicial do prefill. O conteúdo final chega antes do termo da geração; a margem de 1 ms no corte favorece a alternativa. Na call de 148, 1 022 das 1 296 waves tinham somente parking e 213 tinham pelo menos um rank pronto e outro atrasado nas duas sessões. No decode há 1 656 waves, das quais 775 mistas à entrada, sete com todas as gerações em falta e 874 já completas. Os ranks estacionados não recebem crédito de cálculo útil. A parte 40 conserva o FAIL da comparação integral de ordem de eventos com a parte 37; cada cálculo utilizou os próprios relógios e bindings. [Conversa e qualificação do observador](../conversation/README.md) · [Âmbito da comparação entre sessões](../t1_local/README.md)

**Condição de reabertura.** A coordenação adicional admissível para chegar a qualquer das duas metas é zero com estes preços, mesmo com preparação e sincronização gratuitas. Outra distribuição de trabalho entre CPU e GPU, uma redução do tempo efetivo de entrega com o pack ou uma mudança nas fontes de bytes altera as premissas. Os dois ensaios isolados no NVMe mediram as leituras; falta-lhes a publicação após os SET de cada geração de todas estas waves. A medição do pack em quatro waves também não cobre a conversa. A ablação natural do pack pode alterar o tempo na própria sessão; medi-la e validar o seu histórico responde a uma pergunta independente. [Libertação ao router](../router_release/README.md) · [Quatro grupos do pack integral](../t1_full_pack_service/README.md)

## Reprodução

Revisão `2f01daee5ee8b2f66a59fa275ed692fe50393431`, protocolo em `b0216e97`. As duas execuções no portátil reproduziram o mesmo SHA-256 `c8b833f709659c2d89ef3cce18c9c980b57c8b9932de064f2f2846f4f18571d8`. Duraram 0,63 e 0,61 s, com RSS máximos de 89 708 e 89 452 KiB. O verificador autentica os dois manifestos, recibos, journals e limites de cliente, e revalida a conservação das 1 440 posições, das waves e das gerações. O dispendido foi leitura de recibos e cálculo offline em CPU.

```sh
u=research/qualification-retake/phase_fd/integrated/rank_overlap
python3 -IB "$u/test_screen.py"
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120s \
  prlimit --as=805306368 --cpu=120 --fsize=8388608 -- \
  python3 -IB "$u/screen.py" --archive-root "$ARCHIVE" --new-output-dir "$NOVO"
cmp "$NOVO/receipt.json" "$u/evidence/receipt.json"
```
