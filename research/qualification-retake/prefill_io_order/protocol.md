# O serviço muda ao ordenar as mesmas procuras já elegíveis no NVMe?

Pré-registo físico de 25/11/2026, antes de abrir o GGUF nesta unidade. A hipótese é que ordenar por offset do componente gate no ficheiro encurte o tempo de servir a última procura da wave **e** o tempo agregado dentro dos preads por expert. A explicação alternativa é que os quatro workers e o controlador NVMe já sobrepõem os mesmos pedidos suficientemente bem e qualquer mudança de despacho só move a cauda. Offset no GGUF, extents do Btrfs e endereços físicos do SSD são grandezas distintas. A ordenação não usa informação sobre tempos de serviço ou completions.

### Trabalho fornecido e autoridade

Usamos o C135 nominal original, call 2 de 148 após o retorno de 5, primeiro tile de 32. À saída do router, R0 percorre as demandas e, mantendo o mutex, emite também os preloads de wave 1 antes do WAIT. Critério previamente escolhido na exploração sem timing novo: primeira wave 0 de cada tier com pelo menos oito demandas novas, na qual a sua ordem difere da crescente. C135 seleciona CPU14 com nove demandas e doze preloads, e CUDA25 com oito demandas e três preloads. Embora se usem as identidades da camada CUDA, leem-se só os bytes no host.

O gerador valida o trace, a receção histórica, o inventário C7 e as duas fontes de C135. A sequência completa dos primeiros ENQUEUE coincide com a dos 21/11 DEQUEUE por camada/expert/slot/geração. O último ENQUEUE do lote antecede o primeiro dequeue. Até ao fim do último serviço destes jobs, o journal mostra que nenhum outro LOAD_BEGIN, LOAD_END ou DEQUEUE se mistura com o lote. C135 pôde entrar na wave seguinte enquanto terminavam os preloads já emitidos. A fixture observa separadamente a última demanda e o drain das 21/11 leituras. As camadas 14 e 25 são dois episódios independentes separados por outras camadas e por CPU/CUDA. O somatório das suas duas janelas é o comparador fixo da fixture. Não é o caminho contínuo do forward. [Agenda derivada](schedule.json) · [Custo que levou à seleção](../prefill_dispatch/README.md)

A mantém a ordem FIFO de todas as gerações. B só ordena o prefixo de demandas já elegíveis dentro do mesmo lote. O prefixo continua antes dos preloads e toda a cauda de preloads mantém a sua ordem original. Mesmas três chamadas por expert, gate/down/up na ordem do pin C135, sem agrupar, coalescer, adiantar outra wave, mudar vítima ou trocar bytes. As chamadas leem o original MXFP4 em offset, tamanho e alinhamento previstos pelo índice GGUF a partir da cópia NVMe integral já confirmada por SHA-256 e nova leitura direta. Verificar o recibo de colocação, stat depois da confirmação integral, FD, mount e O_DIRECT. O executor tem quatro threads persistentes, cada uma retira uma geração de uma fila comum e faz os três preads consecutivos. As quatro threads já estão a aguardar o mesmo sinal quando se inicia o relógio. B paga a ordenação e abertura da fila. Cada job possui buffers próprios para conferir fora dos intervalos medidos os 96 SHA-256 por braço, comparados por camada/expert/componente contra o primeiro braço. A hipótese de imutabilidade do ficheiro é verificada antes e depois dos braços. Uma leitura curta ou erro encerra a execução sem retry.

### Comparação e saída

Uma família ABBA no mesmo NVMe, sem flush ou aquecimento de dados escolhido. A1/B2 e A4/B3 dão os dois pares orientados. Em cada episódio, o relógio primário vai do início da formação da fila até ao retorno das três leituras da última demanda do prefixo. Medir também o drain, o serviço somado e união dos preads, cada duração por componente/identidade, ordem de dequeue, worker nativo, custo de liberação e deltas de setores de todo o dispositivo por episódio e braço. Os comparadores somam as janelas de CPU14 e CUDA25 separadamente na mesma condição, preservando a tabela individual. O tempo total do braço inclui hashes, guardas e amostragem.

Um par admite a etapa seguinte se a última demanda somada **e** o serviço somado dos 96 preads melhorarem ambos pelo menos **5,1150%**, cada camada individual melhorar o seu tempo até à última demanda e o drain somado regredir no máximo 5%. A escala de 5,1150% vem da sensibilidade uniforme sobre **1 177** cargas no replay C135 com despacho ideal. O limiar aqui é um critério de investimento da amostra de **32** cargas. Não permite extrapolar a redução medida em dois lotes aos restantes jobs. Dois pares elegíveis dão GO só para uma fixture de maior cobertura. Um par elegível dá INCONCLUSIVE; zero dá NO_GO para alargar esta ordem a partir destes lotes. Um resultado favorável precisa ainda de serviço por identidade no restante prefill, integração com cópias e publicação, logits completos, R0 contemporâneo, ablação e proteção do decode nos dois casos. O caso de código, pedidos reais e o tempo cliente ficam NOT_RUN.

### Recursos e reprodução

Uma janela C118 nova de 60 s, com amostragem ao segundo antes do primeiro braço, numa checkout limpa no commit de freeze. Exigir política C55 passada, recalculada, com idade máxima de uma hora, AC/performance, PSI inferior a 10 e ausência de carga de modelo, cópia ou build. Consultar CPU, GPU e NVMe, limites dinâmicos de reservatório de RAM e térmicas. Stop ao primeiro aviso de temperatura aplicável, recurso inválido, evento cgroup, swap, pressões, regressão de relógio, perda de recibo ou mismatch. O cgroup dedicado da família tem MemoryHigh=MemoryMax=384 MiB, MemorySwapMax=0, stop preventivo 352 MiB. Os 21×3 buffers alinhados pré-alocados permitem conferir os hashes depois do relógio. Amostrar entre os dois episódios e depois do segundo, com lacuna máxima de 2 s. Limites de 2 s por episódio, 15 s por braço, 125 s pela família e 135 s pelo scope, 2 MiB de resultados. Conservar saída exclusiva e FAILs. Pedido por braço 423 428 096 B alinhados para 423 014 400 B de payload. A família pede 1 693 712 384 B no único NVMe. Não há leituras de pesos no USB, reserva de GPU, execução de runtime ou geração de tokens. Energia física fica desconhecida.

Reproduzir o plano com os inputs congelados C135 e C7, sem pesos; `--new-plan` recusa substituição.

```sh
python3 -B research/qualification-retake/prefill_io_order/make_plan.py \
  --trace "$TESY_C135_TRACE" --historical "$TESY_C135_RECEIPT" \
  --inventory "$TESY_C7_INDEX" --backend "$TESY_C135_SOURCE" --new-plan "$NEW_PLAN"
cmp "$NEW_PLAN" research/qualification-retake/prefill_io_order/schedule.json
python3 -B research/qualification-retake/prefill_io_order/test_order.py
```

O comando de medição requer a política, o recibo de colocação autorizado e um diretório novo privado em disco persistente do projeto. Os logs de sistema e as amostras completas ficam no portátil.

```sh
systemd-run --user --wait --pipe --collect -p MemoryMax=384M -p MemoryHigh=384M \
  -p MemorySwapMax=0 -p RuntimeMaxSec=135s --working-directory="$FROZEN_CHECKOUT" \
  python3 -B research/qualification-retake/prefill_io_order/measure.py \
  --commit "$FROZEN_COMMIT" --policy "$C55_POLICY" --placement "$PLACEMENT_RECEIPT" \
  --new-output-dir "$NEW_PRIVATE_ROOT"
```
