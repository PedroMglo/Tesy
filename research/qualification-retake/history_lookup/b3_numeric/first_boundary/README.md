# A primeira divergência medida ocorre no router da camada 0

**A entrada F32 do router coincidiu nas três posições. O primeiro produto de matriz do router, antes do bias, já devolveu 311 de 384 padrões F32 diferentes.** As posições 189, 190 e 191 tiveram respetivamente 108, 97 e 106 diferenças entre os 128 logits. Os quatro experts escolhidos mantiveram a identidade e a ordem nas 42 combinações observadas de posição e camada. As diferenças nos pesos dos ranks propagaram-se ao residual já na camada 0. [Pré-registo](protocol.md) · [Recibo reproduzido](receipt.json)

| Camada 0, coordenadas com padrão diferente | 189 | 190 | 191 | Coordenadas por posição |
| --- | ---: | ---: | ---: | ---: |
| Embedding, saída da atenção e entrada normalizada do router | 0 | 0 | 0 | 2 880 por fronteira |
| Logits do router antes do bias | 108 | 97 | 106 | 128 |
| Logits com bias | 106 | 97 | 105 | 128 |
| IDs top-k ordenados | 0 | 0 | 0 | 4 |
| Pesos após softmax | 3 | 4 | 1 | 4 |
| Gate, up, SwiGLU e down | 0 | 0 | 0 | 11 520 por fronteira |
| Contribuições após ponderação | 8 126 | 11 364 | 2 373 | 11 520 |
| Saída MoE somada | 2 454 | 2 469 | 706 | 2 880 |
| Residual de saída da camada | 1 726 | 1 981 | 343 | 2 880 |

As primeiras palavras diferentes nos logits têm índices 2, 0 e 0 nas respetivas posições. O primeiro desvio observado em Q/K/V pós-projeção foi na camada 13, posição 190, com 4 090/4 096, 509/512 e 507/512 F32 diferentes. Os gate/up/down também concordam até à camada 12 inclusive. O corte de K/V explica onde os bytes guardados começaram a mudar, enquanto o router localiza um desvio já presente treze camadas antes. A exatidão de uma alteração local no router, o efeito a jusante e o throughput de B3 exigem provas próprias. [Estado KV](../kv_difference/README.md)

Cada braço reproduziu os seus próprios 2 248 testemunhos de prefill, os cinco vetores de logits (prefill e quatro saídas), KV e pool iniciais e KV pós-bloco. Cada captura contém 885 payloads privados, 19 324 992 bytes. O comparador observou 388 pares de payloads distintos. A igualdade com o controlo OFF autentica as saídas e snapshots. O sincronismo adicional do callback limita a atribuição dentro de trechos sem observação. O programa identifica a operação lógica; o kernel físico exato ainda precisa de observação do dispatch.

| Recursos por processo | AR | B3 |
| --- | ---: | ---: |
| Tempo nativo / scope com C118 | 28,982 / 89,778 s | 27,781 / 88,536 s |
| Pico de memória do cgroup | 16 053 424 128 B | 16 281 337 856 B |
| VRAM / swap | 6 872 MiB / 0 B | 6 870 MiB / 0 B |
| CPU / GPU / NVMe máximos | 72,125 / 52,58 / 45,85 °C | 70,625 / 51,95 / 47,85 °C |
| Tamanho raw | 128 186 333 B | 128 147 273 B |

A família durou 181,071 s. Ambos os serviços terminaram inativos com MainPID zero. Estes tempos incluem a instrumentação e não estimam o benefício de uma política. O primeiro inventário C55 foi recusado pelo isolamento do bus systemd antes da admissão (SHA 41ea9c5b5c62b839c4fdb9b55c1dcc3605aa5beb02c95379311cd0315280c5e3). O segundo inventário admitiu E20 com 62 amostras em 61,003 s. Os dois braços numéricos correram uma vez. O JSON contém os hashes do binário, da família, de cada braço e da comparação individual. [Supervisor](profile.py) · [Comparador](grade.py)

## Reprodução

Usar a revisão 1317fd0c1f9ebe6b8d0faf402c2f0e2f99001677 para construção e aquisição. Para a auditoria posterior basta a árvore preservada da família e a cópia dos controlos na parte 32. O revisor reabre monitores e lançamentos pelos hashes, os 4 496 testemunhos de prefill, os restantes ficheiros do controlo e todos os 1 770 payloads das fronteiras. Pode correr com ambas as árvores realocadas.

```sh
u=research/qualification-retake/history_lookup/b3_numeric/first_boundary
python3 -IB "$u/test_boundary.py"
python3 -IB "$u/reopen.py" --family "$PHYSICAL" \
  --family-sha256 9f4f7d6006cac1befa989df086af85a193778d8e5cae26775114b2ad66532fac \
  --archived-family "$OFF_PART32" --new-output-dir "$NEW_AUDIT"
```
