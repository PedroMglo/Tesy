# Uma admissão E10 para a capacidade real do ik

**Pronto em fonte, condicionado ao gate de duas camadas.** O supervisor reutiliza a política FILE_PAGING do canário C110, a admissão C118, o controlo de temperatura, o monitor NVML e a validação dos providers do ensaio CUDA minúsculo. A comparação BANK9 com o residente e a sua revisão independente têm de passar antes da preparação. À data desta entrega a R02 conservou uma falha no observador BANK9. Essa família termina antes de produzir o par de logits necessário. O número de execuções deste teste com o modelo real é zero. [Contrato físico](protocol.md) · [Receita e grade do processo](../protocol.md)

O supervisor aceita um único carregamento do GGUF original e um único contexto. Nos cortes L e C exige o mesmo inode efetivo no filho e no snapshot nativo e o PID autorizado como proprietário CUDA. O corte F já ocorre depois de libertar o contexto, modelo e backend. O pai confirma o desaparecimento das vistas do GGUF, audita os providers, aguarda o exit e mede se a VRAM global regressa até 64 MiB acima do nível anterior ao arranque. A amostragem pode perder transientes entre observações. Outros processos gráficos podem alterar o valor global; uma violação deste gate preserva a falha sem inferir qual alocação a causou. A contagem de setores do NVMe inclui todos os utilizadores. Não se obtêm tempos do primeiro token ou débito de inferência desta prova.

A C55 deve ser própria deste teste, começar depois da publicação do protocolo e ter prefixo de diretório `tesy-ik-capacity-c55-`. Usar o monitor de serviço empacotado em `/tmp/tesy-packed-service-nvml-20261125-r01/lib`, com o recibo `PASS_CPU_CAMPAIGN_MONITOR` de SHA-256 `58aa72dfb873e951ac49ed35e6da534b18870fcf1d845ed520c030d82ee23260`. A preparação verifica a seleção real pelo loader. Dentro do scope repete essa verificação e exige igualdade integral do recibo. A autoridade C110 ENV49 tem outro esquema, apesar de os dois aliases NVML resolverem para o mesmo inode. A variável de monitor pertence ao supervisor; o cliente recebe o seu próprio ambiente com os quatro providers CUDA selados. Os caminhos de input e digests futuros são fornecidos pelo registo da campanha. Com a checkout congelada e os recibos externos definidos, a preparação e a execução usam o mesmo conjunto de argumentos. Cada raiz de resultados tem de ser nova.

```bash
q="$CHECKOUT/research/qualification-retake"
s="$q/ik_mapped_experts/hybrid/capacity/admission/run.py"
model=/home/pmglo/models/tesy-gpt-oss-120b-nvme/gpt-oss-120b-MXFP4.gguf
export LD_LIBRARY_PATH=/tmp/tesy-packed-service-nvml-20261125-r01/lib
# Só depois da decisão de autorização e numa janela sem outros trabalhos físicos.
python3 -IB "$q/nvme_admission/window.py" --nvme-model "$model" --new-output-dir "$C55"
common=(--commit "$COMMIT" --tiny "$TINY_FAMILY" --tiny-sha256 "$TINY_SHA"
  --tiny-review "$TINY_REVIEW" --tiny-review-sha256 "$TINY_REVIEW_SHA"
  --client "$CAPACITY_CLIENT_BUILD" --client-sha256 "$CAPACITY_CLIENT_SHA"
  --dso /mnt/sdisk-ssd-ext/Tesy/repo/build/tesy-ik-cuda-sm89-build-20261126-r01
  --inputs "$INPUT_DIR" --inputs-sha256 "$INPUT_SHA" --placement "$PLACEMENT_RECEIPT"
  --env49-map /tmp/tesy-env49-static-r01/static-map.json --c55 "$C55/receipt.json" --c55-sha256 "$C55_SHA")
python3 -IB "$s" "${common[@]}" --new-output-dir "$PREPARED"
unit=tesy-ik-e10-capacity-20261126-r01
systemd-run --user --quiet --scope --unit="$unit" -p MemoryHigh=9728M -p MemoryMax=10G \
  -p MemorySwapMax=0 -p RuntimeMaxSec=420 \
  python3 -IB "$s" "${common[@]}" --prepared "$PREPARED" --prepared-sha256 "$PREPARED_SHA" \
  --unit "$unit" --execute --new-output-dir "$PHYSICAL"
```

Usar o SHA externo de cada recibo autenticado. O verificador recusa substituir a preparação por uma família diferente, a C55 do tiny, um plano do GGUF sintético ou as DSOs da versão CPU. Em falha, arquivar a raiz inteira antes de nova identidade. Os ficheiros raw e os mapas do processo são privados. [Supervisor](run.py) · [Autoridades](sources.py) · [Contraprovas sem modelo](test_run.py)

A contraprova com o recibo físico R02, SHA-256 `2e83262ce3efb72136f2025d76db749f21e768bc78b8abbe55480648dd9fa27a`, retornou `tiny CUDA prerequisite` antes de consultar revisão, plano, modelo ou monitor. Dezasseis testes Python cobriram os quatro handoffs, proprietários ausentes/estranhos e libertação, prazos distintos por fase, os dois comparadores da VRAM, identidade da VMA por dispositivo/inode e conservação da amostra que aciona o stop. A verificação de estilo passou. O caminho positivo integral de preparação e o desempenho do supervisor ainda precisam de uma família tiny admitida.

A correção do monitor adicionou três testes. Verificam que o mesmo inode sob o recibo ENV49 é recusado antes da consulta NVML, que uma mudança de autoridade entre preparação e execução bloqueia o scope e que a preparação só recebe PREPARED_ONLY depois da autenticação do monitor. A suíte passou com 19 casos e um monitor simulado.
