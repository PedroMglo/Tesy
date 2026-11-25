# Os dois turnos C281 passam no frontend offline de ik

**Duas execuções do fork ik reproduziram cada byte dos prompts, cada ID oficial e todos os deltas de raciocínio e conteúdo da trajetória C281 selada.** Ambas usaram a mesma Jinja com data vinculada, vocabulário GPT-OSS original sem tensores e CPU. [Recibo e hashes](evidence.json) · [Pré-registo](protocol.md) · [Contrato do servidor e da cache](../frontend.md)

| Turno | Bytes do prompt | IDs oficiais | IDs amostrados de referência, incluindo EOG | Deltas não vazios idênticos |
|---|---:|---:|---:|---:|
| T1 | 12 132 | 2 043 | 78 | 68 |
| T2 com final real de T1 no histórico | 12 933 | 2 197 | 47 | 37 |

O BPE do fork tokenizou também os renders selados diretamente e coincidiu nas 4 240 posições. O prefixo dos dois prompts é de 2 043 IDs. O caminho PEG de produção emitiu o mesmo conteúdo acumulado de cada canal e a mesma sequência de atualizações não vazias. Cada vetor teve EOG apenas no final. Nos dois controlos, mudar a data para 6 de outubro alterou estritamente a linha da data e os IDs, e deslocar o EOG para a primeira posição levou à rejeição. O SHA de stderr é o único campo diferente entre os dois recibos privados. A resolução das bibliotecas e das referências dinâmicas passou tanto no build como antes de cada execução.

**Âmbito.** A prova usa a continuação conhecida de C281 como entrada para o parser. Os 78/47 IDs gerados espontaneamente pelo fork, o split de cache 2044+153, os eventos HTTP completos, o modelo com pesos e os relógios de produto continuam por testar. Um ensaio natural teria de construir T2 a partir do próprio final de T1 e verificar os contadores de prefixo do fork na mesma sessão. A correspondência dos prompts e canais satisfaz a parte de frontend desse gate. [Fonte da política de histórico](../../../../tools/optin_integration_client.py) · [Referência dos turnos](../../history_lookup/native_ids/README.md)

## Reprodução

Usar o checkout e providers autenticados pelo recibo de build. `OBJECTS` é a pasta de CMake CPU do ik com o alvo `common` já construído. `PART29` aponta à parte 29, `VOCAB` à cópia privada de 12 980 384 B com zero tensores e `FIXED` à Jinja datada autenticada. O runner verifica os hashes e passa os dados privados apenas no pipe do filho. Reservar um diretório novo por invocação.

```sh
u=research/qualification-retake/ik_mapped_experts/frontend
python3 -IB "$u/run.py" build --src "$IK" --objects "$OBJECTS" --new-output-dir "$BUILD"
python3 -IB "$u/run.py" verify --part "$PART29" --vocab "$VOCAB" --template "$FIXED" \
  --build "$BUILD" --build-sha256 "$BUILD_SHA" --new-output-dir "$OUT"
```
