# C281 com IDs amostrados e cópia causal

**Na nova conversa nominal, a cópia N=2/M=2 teria poupado 12 das 46 avaliações subsequentes ao primeiro token de T2.** A regra efetua 23 chamadas AR e 11 verificações de bloco. Para atingir 6 tok/s no relógio histórico sem debug, o custo médio de cada bloco, incluindo rejeições e coordenação, poderia chegar a **1,231807 vezes** o custo médio de uma avaliação AR. Se cada bloco custar exatamente uma avaliação AR, sobram **0,546487 s no total** dos 46 passos para custos adicionais. Autorizada somente a fixture seguinte. O preço real do bloco e o efeito de usar três posições na aritmética do target estão por medir. M3 PARTIAL e M4 NOT_MET. [Pré-registo](protocol.md) · [Crivo reproduzido](evidence/b3.json)

| Janela depois da âncora | AR | Verificações B3 | Aceites/propostos | Propostas completas | Rejeições | Chamadas poupadas | B3/AR máx. para −15% no decode |
|---|---:|---:|---:|---:|---:|---:|---:|
| Primeiras 32 avaliações | 19 | 7 | 6/14 | 3 | 4 | 6/32 | 1,171429 |
| Até ao EOG, 46 avaliações | 23 | 11 | 12/22 | 6 | 5 | 12/46 | 1,463636 |

A referência temporal é o T2 da C281 pós-atualização sem debug. O seu contador reporta 47 tokens em 9,858674 s, incluindo o ID inicial fornecido pelo prefill. A triagem distribui esse tempo por 46 avaliações AR. Para 6 tok/s o orçamento é 47/6 = 7,833333 s. O primeiro final histórico levou 20,385070 s e o prefill 10,784107 s. Mesmo creditando todo o decode ao caminho até ao primeiro final, restam 10,526396 s. Com o decode exatamente a 6 tok/s e o restante trabalho fixo, ainda seria preciso recuperar 8,359730 s para os 10 s. As hipóteses sobre custo médio e sobreposição tornam estes limites condicionais. [Controlo sem debug](../../nvme_conversation/postupdate/physical-r01/evidence.json)

## Prova dos dois turnos

Um servidor C281, um slot e duas conclusões naturais. O único acréscimo ao comando histórico foi `--log-verbosity 5`. O supervisor autenticou executável e bibliotecas, dono da porta e argv integral no primeiro e último limite de cliente. Reconstruiu o histórico com a resposta do próprio T1. O log continha 78 e 47 amostras, com contador consecutivo e EOG final em ambos. As 77 e 46 inserções no lote seguinte corroboraram independentemente os IDs anteriores ao EOG. O cliente C269 offline verificou a peça de cada ID e reconstituiu a sequência de choices e usage da SSE. Os 71 e 40 objetos foram idênticos aos dos mesmos turnos históricos. Os dois validadores funcionais e os dois validadores de prefixo passaram. T1 processou 2043 IDs e T2 recuperou 2044 e processou 153 dos seus 2197. A trajetória da nova sessão fica identificada. O SSE histórico continua compatível com múltiplos IDs finais. [Verificação](evidence/verified.json) · [Ambiguidade histórica](../natural47/README.md)

A C55 e a C118 autorizaram E20, com 20 GiB e swap zero. A sessão com diagnóstico durou 168,992 s desde o início da supervisão, incluindo C118 e cleanup. O pico de cgroup foi 14,64 GiB e o máximo da GPU 6848 MiB. O processo saiu com código zero e libertou a porta. A árvore raw da sessão ocupou 1 548 635 bytes, dos quais 639 371 no log nativo. O verificador offline levou 7,53 s e 390 524 KiB de RSS sem forward. O arquivo privado part-29 contém 45 ficheiros e 3 263 682 bytes. A reabertura de part-23 e part-29 reproduziu o recibo B3 byte a byte. O compacto identifica os hashes dos recibos privados e do manifesto do arquivo. [Recibo da sessão](evidence/capture.json)

## Reprodução

Na checkout limpa do commit de medição, preencher os argumentos `C281_ENV` com as flags e identidades da [qualificação pós-atualização](../../nvme_conversation/postupdate/README.md). Incluem `--repo`, `--window`, `--window-sha256`, `--placement`, `--preflight-dir`, `--preflight-sha256`, `--c270`, `--c270-sha256` e `--commit`. A preparação e a campanha usam unidades e diretórios exclusivos. A preparação não lança o servidor.

```sh
u=research/qualification-retake/history_lookup/native_ids
python3 -B "$u/profile.py" "${C281_ENV[@]}" --historical "$HIST" --unit "$UNIT_PRE" --new-output-dir "$PRE"
python3 -B "$u/profile.py" "${C281_ENV[@]}" --historical "$HIST" --unit "$UNIT" --new-output-dir "$CAPTURE" --execute
python3 -B "$u/verify.py" --historical "$HIST" --capture "$CAPTURE" --capture-sha256 "$CAPTURE_SHA" \
  --vocab "$VOCAB_ZERO_TENSORES" --native-backends "$C7_BACKENDS" --new-output-dir "$VERIFIED"
python3 -B "$u/b3.py" --historical "$HIST" --capture "$CAPTURE" --verified "$VERIFIED" \
  --verified-sha256 "$VERIFIED_SHA" --new-output-dir "$SCREEN"
```

As duas últimas invocações consomem os arquivos já preservados. O passo de verificação usa o GCC e os providers selados no recibo e o vocabulário com zero tensores. Manter os vetores i32, mensagens e bytes privados fora do Git. [Próximo discriminante sem modelo](b3_fixture/protocol.md)
