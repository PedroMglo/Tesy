# Cliente híbrido do ik para o GGUF de duas camadas

A referência CPU executou os 32 tokens de entrada e o teacher seguinte. Os dois perfis do observador CPU reproduziram os 1 056 F32 e as quatro sequências de top-4. Na versão final foram observados 12 MUL_MAT_ID e 12 ADD_ID em submissões reais. O pico do scope foi de 47 054 848 B, com swap zero. O [recibo compacto](cpu-reference.json) identifica o executável, o bruto e os controlos sem driver. O modelo sintético ocupa 3 390 592 B e tem 32 entradas no vocabulário.

No teste ABI sem driver, as funções interpostas chamaram uma DSO de memória do anfitrião que implementa as assinaturas CUDART. O teste conferiu as cópias 1D, pitch 2D diferente em cada lado, encaminhamento do código de erro, registo, memset e indicação de peer. Os testes do revisor incluem um fill coalescido, hit posterior sem H2D, falta de um dos três componentes, associação ao slot errado, cópia depois do consumo, observador cego no controlo e diferença de sinal de zero F32. A execução na RTX tem uma admissão e uma decisão próprias. [Protocolo do cliente](protocol.md) · [Protocolo da família](../protocol.md)

## Reprodução

Usar a checkout Tesy congelada, as DSOs CPU de R03 e o GGUF preparado pelo tiny_loader. Os comandos usam diretórios de saída novos. Guardar os seus recibos com os raws.

```sh
C=research/qualification-retake/ik_mapped_experts/hybrid/client
python3 -IB "$C/test_grade.py"
python3 -IB "$C/test_copy.py" --new-output-dir "$ABI_NEW"
python3 -IB "$C/build.py" --variant cpu --source "$IK" --objects "$CPU_OBJECTS" \
  --new-output-dir "$CPU_BUILD_NEW"
CPU_SHA=$(sha256sum "$CPU_BUILD_NEW/receipt.json" | cut -d' ' -f1)
systemd-run --user --scope --quiet --unit="$CPU_UNIT" -p MemoryMax=256M -p MemorySwapMax=0 \
  python3 -IB "$C/cpu.py" --scope "$CPU_UNIT" --build "$CPU_BUILD_NEW" --build-sha256 "$CPU_SHA" \
  --objects "$CPU_OBJECTS" --tiny "$TINY_LOADER_R02" --new-output-dir "$CPU_NEW"
python3 -IB "$C/build.py" --variant cuda --source "$IK" --objects "$CUDA_BUILD/objects" \
  --dso-build "$CUDA_BUILD" --dso-sha256 "$CUDA_BUILD_SHA" --env49-map "$ENV49_MAP" \
  --new-output-dir "$CUDA_CLIENT_NEW"
```

O cliente GPU recebe o modo `RESIDENT`, `BANK9` ou `BANK7`, o GGUF qualificado e o caminho de um diretório novo. O supervisor fornece os dois descritores das barreiras e o ambiente do loader. O controlo CPU usa o modo `CPU`. Os endereços e os vetores numéricos ficam no diretório privado dos brutos.

O revisor por braço é `grade.check_arm(mode, stdout_text, stderr_text, native_dir)`. Confere as cópias com endereço de origem na matriz do GGUF, os SET que as envolveram, a posição de destino na vista CUDA e a identidade do expert efetivamente consumido. Registos de H2D sem origem atribuível antes do routing impedem a confirmação da ausência de preload. O revisor só atribui os pedidos que atravessam as APIs interpostas no processo. O tamanho corresponde aos bytes solicitados à API. A ocupação do barramento, a atividade interna do driver e a latência de uma execução sem estes callbacks requerem outras observações.

A função `grade.compare_arms(ref_dir, ref_grade, candidate_dir, candidate_grade)` reabre os 32×32 e 1×32 F32 autenticados. Apresenta palavras divergentes, máximo absoluto, RMSE, primeiras escolhas greedy, empates e paridade de rotas separadamente. O contraste de intervenção é o residente GPU frente ao banco de nove slots. A CPU dá a comparação entre backends. O fallback com sete slots conserva as medições próprias de backend, cópias e resultado.
