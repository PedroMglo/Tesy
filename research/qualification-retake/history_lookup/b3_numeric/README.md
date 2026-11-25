# Três posições alteram os logits e o estado KV no controlo C127 de 189 IDs

**NO_GO para igualdade bitwise de B3 com AR neste prefixo e nesta geometria.** As três linhas do bloco e a primeira linha individual seguinte divergiram. Os quatro vetores eram finitos e deram o mesmo argmax único em ambos os braços. O estado KV depois do bloco também divergiu. O resultado fecha a hipótese de que se pode substituir estas chamadas AR por uma verificação de largura três preservando todos os bits. A coincidência de quatro escolhas greedy deixa em aberto outras trajetórias e a distribuição de sampling. [Recibo numérico integral, sem IDs](evidence/numeric.json) · [Protocolo congelado](protocol.md)

| Posição absoluta | Chamadas AR/B3 | Valores F32 diferentes de 201 088 | Maior diferença absoluta | RMSE | Argmax único igual |
|---|---|---:|---:|---:|---|
| 189 | AR 1 / B3 linha 1 | 201 085 | 0,127172 | 0,022571 | Sim |
| 190 | AR 2 / B3 linha 2 | 201 087 | 0,155805 | 0,024844 | Sim |
| 191 | AR 3 / B3 linha 3 | 201 088 | 0,540884 | 0,065417 | Sim |
| 192 | Chamada individual em ambos | 201 088 | 0,475828 | 0,084074 | Sim |

## Por que se podem comparar os dois braços

Dois processos E20 independentes carregaram o mesmo GGUF GPT-OSS-120B MXFP4 com o mesmo cliente, bibliotecas C269, P12, 40 slots e ub32. Executaram o prefill real do caso log_medium de 189 IDs. Cada braço reproduziu os 2248 ficheiros de prefill da C127, 81 624 144 bytes. O AR reproduziu também as duas primeiras linhas de decode históricas. A C127 guardava o fim do prefill e os passos 0, 1, 7 e 31. As referências para os passos 2 e 3 vieram do AR contemporâneo. O verificador reabriu as linhas históricas da C270 pós-atualização e aferiu os respetivos hashes. [Ponte C127/C270](../../nvme_r0_gate/README.md)

Ainda antes do primeiro batch B3, o cliente comparou byte por byte a serialização da sequência KV inicial de 11 690 596 bytes e o estado dos pools de 183 024 bytes com o AR que acabara de passar. O cálculo prosseguiu apenas após igualdade. O mesmo conjunto de quatro IDs de continuação foi fornecido aos dois braços. Os três primeiros diferem do argmax das respetivas linhas precedentes e o quarto coincide com o argmax, nos dois casos. Cada linha representa assim o prefixo fornecido exato da fixture. No fim do terceiro token, as serializações de KV tinham o mesmo tamanho de 11 801 224 bytes e hashes diferentes. A divergência sobreviveu à chamada individual comum no passo 3. A fixture não removeu nem restaurou páginas de KV.

Não foi congelado um epsilon admissível para promoção de logits entre estas duas geometrias. Os erros da tabela descrevem o resultado e a igualdade de argmax tem como denominador quatro linhas. O acordo inicial dos pools e do KV exclui uma partida diferente ao nível dos campos observados. Os hashes e os logits identificam a diferença de comportamento, sem localizar a primeira operação que divergiu. A aceitação natural de propostas no histórico C281, respetivo rollback, custos de paging e os objetivos de produto conservam os seus próprios gates. M3 PARTIAL e M4 NOT_MET. [Verificação de controlo B3 em C281](../native_ids/b3_fixture/README.md)

## Recursos e reprodução

C55 de 61 amostras em 60,044 s e zero processos GPU de compute. A família decorreu em 180,210 s. Cada processo usou cgroup de 20 GiB, swap zero e três descritores diretos do GGUF no máximo. O monitor cobriu inicialização, prefill, quatro posições de continuação, serialização e cleanup.

| Braço | C118 | Tempo do processo | Pico cgroup | Pico VRAM | CPU/GPU/NVMe máximos |
|---|---:|---:|---:|---:|---:|
| AR | 61 amostras, 60,148 s | 27,932 s | 15,002 GiB | 6874 MiB | 73,25 / 53,07 / 46,85 °C |
| B3 | 61 amostras, 60,168 s | 28,103 s | 15,070 GiB | 6868 MiB | 71,38 / 51,70 / 48,85 °C |

Estes tempos incluem o trabalho da captura e constituem custos da campanha. A árvore privada física contém 4549 ficheiros e 217 776 226 bytes. A auditoria offline levou 1,16 s e 47 708 KiB RSS, sem carregar o modelo. Os dois braços encerraram com código zero, as duas unidades ficaram inativas e a GPU ficou sem processos de compute. O arquivo privado part-32 contém 4579 ficheiros e 218 162 988 bytes. Reabrir esse arquivo produziu o mesmo recibo numérico, byte a byte. O SHA-256 do manifesto do arquivo é `94b255e1cf05ea527cc08eb938b125f4ecd96699be53de6c5b9feb627db05461`. O SHA-256 do recibo físico é `97ae7b5b9c9deed4e730fb1ddb50cdbd6d671aeea5169f73db2c96f49b40a7d9`. O recibo compacto volta a autenticar cada braço, monitor, inventário, árvore de prefill, snapshots e vetores. [Identidades da execução](evidence/sources.json)

Para reproduzir a análise numa cópia do arquivo, usar uma saída privada nova. O comando não depende da localização em que o processo original correu.

```sh
u=research/qualification-retake/history_lookup/b3_numeric
python3 -B "$u/compact.py" --family "$FAMILY" \
  --family-sha256 97ae7b5b9c9deed4e730fb1ddb50cdbd6d671aeea5169f73db2c96f49b40a7d9 \
  --new-output-dir "$AUDIT"
```

A medição foi feita na checkout limpa de b3b5f4d5, com o executável de SHA-256 `2fcde4e0307194173edc736b3ca10dd134e0f639011935b8a9486d711c747661`. A compilação e os dois arms físicos são reproduzíveis nas condições de admissão do protocolo; os diretórios de preflight, C270, colocação do GGUF, build e C55 são entradas autenticadas. O supervisor aceita os mesmos argumentos de planeamento para executar, passando `--execute` com outra unidade e outra pasta.

```sh
python3 -B "$u/build.py" --backend "$C269" --preflight-dir "$PREFLIGHT" --new-output-dir "$BUILD"
python3 -B "$u/profile.py" --checkout "$PWD" --window "$WINDOW" --window-sha256 "$WINDOW_SHA" \
  --placement "$PLACEMENT" --preflight-dir "$PREFLIGHT" --preflight-sha256 "$PREFLIGHT_SHA" \
  --c270-dir "$C270" --build-dir "$BUILD" --build-sha256 "$BUILD_SHA" \
  --measurement-commit "$COMMIT" --unit "$FRESH_UNIT" --new-output-dir "$FRESH_OUTPUT"
```
