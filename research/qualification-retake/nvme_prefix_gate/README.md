# Canário numérico do C294 no NVMe

**PASS_PREPARED_MODEL_FREE.** O cliente experimental tem SHA-256 `eacf65a6b00b602c91c64ca1c7f0de61ce797c9dfd51a911f57d5006ae1d6147`. A preparação confirmou a fixture C110, os seis vetores históricos completos de logits, 63 headers e a libllama privada C294. O cliente lê as entradas da referência, recusa o modo longo, rejeita entradas inválidas e preserva um destino já existente. Iniciar fisicamente o canário requer a admissão C55 e a verificação por braço C118. A receita R0 de produto mantém 40 slots e E20. [Critérios congelados](protocol.md) · [Recibo da preparação](attempt-02/receipt.json)

As chamadas 16+1+1 fornecem três vetores independentes já conhecidos com 201 088 floats finitos por vetor. O custo histórico máximo nesta fixture de 32 slots foi 12 821 348 352 B de memória cgroup. O gate reserva 13,5 GiB e interrompe aos 13 GiB. Só o ensaio físico dirá se o backend reconstruído respeita esse orçamento. A paridade dos logits, a cobertura de grupos top-4 e a quantidade de memória são os resultados admissíveis. Tempos do canário têm valor de diagnóstico. [C110](../../../results/c110-decode-triangle-20260929T0900Z/resource-summary.json) · [Avaliador](gate.py)

Na primeira preparação, `git apply --include` ignorou o header ao trabalhar numa subpasta do repositório e a comparação com o layout do build recusou o resultado. A segunda derivou a secção do header a partir do patch completo congelado e reproduziu os seus bytes. A compilação e as verificações seguintes passaram em 2,779 s, com pico de RSS amostrado de 252 872 KiB e 109 141 B finais de ficheiros privados. Ambas as tentativas consumiram zero forwards. [FAIL preservado](attempt-01/receipt.json) · [Preparação e verificação do pin](prepare.py)

## Reprodução sem modelo

Na raiz da checkout, indicar duas pastas novas em `TESY_NEW_CANARY_BUILD` e `TESY_NEW_RECEIPT`. O build que passou encontra-se em `build/qualification-nvme-canary-20261124-b` na checkout persistente.

```sh
TESY_PROJECT=/mnt/sdisk-ssd-ext/Tesy/repo
TESY_C7="$TESY_PROJECT/c7-native-placement-screen-20260927-1117utc"
TESY_GATE=research/qualification-retake/nvme_prefix_gate
python3 -B -m unittest discover -s "$TESY_GATE" -p test_gate.py
python3 -B "$TESY_GATE/prepare.py" \
  --backend "$TESY_C7/backends/c294-service-window" \
  --ggml-bin "$TESY_C7/backends/c269-layer-last-use/build-c269-cuda/bin" \
  --prefix-build "$TESY_PROJECT/build/qualification-prefix-r0-20261124-a" \
  --raw-parent "$TESY_C7/results" \
  --private-workspace "$TESY_NEW_CANARY_BUILD" --new-output-dir "$TESY_NEW_RECEIPT"
```

## Execução física admitida

O coordenador seleciona a checkout limpa com o commit de medição, a janela C55 do NVMe, o recibo privado original da colocação e um destino privado exclusivo em volume com espaço. `run_pair.py` confere o digest de cada biblioteca que `ldd` resolveu e os pins de entrada, aplica o limite de RAM a duas unidades systemd transitórias e executa o `run_bounded.py` com inventário fresco de 60 s antes de cada Popen. A primeira divergência encerra o par. Os artefactos de logits, IDs ou journal ficam privados. Acrescentar `--prepare-only` exercita a admissão estática e prepara o protocolo da medição sem arrancar qualquer processo de modelo.

```sh
python3 -B "$TESY_GATE/run_pair.py" \
  --window "$TESY_NVME_C55" --placement "$TESY_PLACEMENT_RECEIPT" \
  --executable "$TESY_PROJECT/build/qualification-nvme-canary-20261124-b/nvme-prefix-canary" \
  --backend "$TESY_C7/backends/c294-service-window" --raw-parent "$TESY_C7/results" \
  --measurement-commit "$TESY_MEASUREMENT_COMMIT" --unit "$TESY_NEW_SERVICE_STEM" \
  --new-output-dir "$TESY_NEW_PRIVATE_RESULT"
```
