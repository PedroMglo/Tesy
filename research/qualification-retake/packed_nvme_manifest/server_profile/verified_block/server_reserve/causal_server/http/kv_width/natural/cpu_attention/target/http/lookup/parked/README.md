# Pode o Tesy saltar o cálculo de uma wave CPU totalmente estacionada?

**MEDIDO no Ryzen, referência nativa C269.** Devolver diretamente o acumulador falhou a igualdade bit a bit em 15 219 de 368 640 F32 no ensaio com os IDs e bias reais da CPU0. O novo atalho reproduziu os 368 640 padrões da referência. Com bias e acumuladores adversariais, a cópia simples divergiu em 17 920 padrões e o atalho reproduziu todos. Repetir em outro processo produziu os mesmos bytes. É um GO para integrar a transformação numa tile routed e medir o seu efeito. O ganho de tempo no cliente continua por demonstrar. [Protocolo](protocol.md) · [Dois resultados completos](result.json)

| Bias usado com os 128 IDs da tile C266 | F32 por caso | Saídas +0 da MMID estacionada | Diferenças da cópia | Diferenças do atalho |
|---|---:|---:|---:|---:|
| Down original da camada 0 | 368 640 | 368 640 | 15 219 | 0 |
| Padrões F32 adversariais | 368 640 | 368 640 | 17 920 | 0 |

O ensaio correu as quatro operações originais no provider CPU, com oito threads e 40 slots MXFP4. Nos 32 tokens da tile, o router arquivado selecionou cinco experts distintos. As matrizes e o RHS da MMID estacionada são dados de fixture. Em ambos os casos o acumulador anterior inclui ±0, extremos, valores normais e subnormais. Isso testa valores no domínio do operador. A frequência de acumuladores com esses padrões na conversa é desconhecida. A referência aplicou bias, máscara e soma depois do down. Mesmo que todos os IDs físicos sejam −1 e a MMID escreva +0, uma saída pode adquirir o sinal do bias ao multiplicar pela máscara. A implementação conserva os valores normais finitos e refaz a aritmética F32 dos restantes. Um rank físico ativo, uma máscara incompatível ou um ID lógico inválido impediram o atalho. O controlo de NaN também passou. [Implementação e referência](fixture.cpp)

O alvo seguinte é o FFN completo da tile C266, com router do target, cinco experts residentes e as oito waves mantidas. Comparar o atalho, a mesma agenda com cálculo original e a referência independente, incluindo os 92 160 F32, IDs, máscaras e todos os slots ao sair. Cobrar decisão, materialização e sincronização e medir a diferença marginal contra a CPU que já evita os dots estacionados. Só depois estender a outras distribuições de ranks e ao pedido. A análise anterior estimou que 18,2% e 41,8% dos intervalos após waves CPU vazias teriam de se tornar poupança no cliente até no cenário de decode mais favorável. [Orçamento da conversa](../empty.md) · [Controlo de tile residente](../../../../../../../../../../../../../phase_fd/integrated/cpu_residual/resident_team/README.md)

**Proveniência.** A primeira compilação passou, e R01 parou no teste de NaN antes do grafo. R02 corrigiu a seleção da função do teste e preservou a falha de R01. O SHA do build corrigido é `944dcf8dd72c80cfda2c52d53a08cd335b937f684ed872d385fba27eb363cf94`. O ELF tem SHA `c09c8ded22b68b5171f5ca3390d1e74c5ae670068cff2c6d29b22eec8343ede7`. O JSON dos dois grafos tem SHA `34dc2d12afba06b15918229666ed75db0a53d07564c20990b0f1c325ee015fae`. Os dois recibos de execução têm SHA `c0f684b606255244b4b558b6cb10cb3e7b9cb8402b066f04531b1eea8478b921`. Os processos duraram 158 e 157 ms incluindo supervisão e verificação, com picos de 201,6 e 203,2 MiB, zero swap na unidade. Estes relógios não isolam o operador. Sem novo pedido, GPU de cálculo ou abertura do GGUF. O inventário de entrada registou corrente externa, 27,42 GB de RAM disponíveis, CPU a 45,1 °C, RTX a 40,3 °C e NVMe a 31,9 °C. [Diagnóstico da falha](r02.md) · [Recibo do arquivo, 24 ficheiros e 265 884 B](../../../../../../../../../../../../../private_archive/part-200.json)

Na checkout limpa de `599773e8c734b50807e8b83834c06551b8d17b30`, usar o backend C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8` e a pasta de preparação C266 com SHA `a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269`. Para cada comando chamar `systemd-run --user --wait --pipe --collect` com nova unit, diretório de trabalho na checkout e propriedades MemoryMax=805306368, MemorySwapMax=0 e TasksMax=24. Os destinos são exclusivos.

```sh
python3 -IB "$STUDY/run.py" build --backend "$C269" --commit "$HEAD" --new-output-dir "$BUILD"
python3 -IB "$STUDY/run.py" run --backend "$C269" --commit "$HEAD" --input "$C266" \
  --build "$BUILD" --build-sha256 "$BUILD_SHA" --new-output-dir "$RUN"
```
