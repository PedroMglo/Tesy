# Custo no relógio do prefill C163

**NO_GO condicional para a redução de 10% do prefill por esta alteração de vítimas, mantendo o serviço dos restantes pedidos e o trabalho fora das esperas fixos.** O resultado geral de latência permanece INCONCLUSIVE. A janela é a soma de CALL_BEGIN a CALL_END nas duas chamadas históricas de 5 e 148 do mesmo braço C163. O intervalo entre retornos fica fora. A janela contém só prefill e foi medida com trace ligado no probe de 44 slots. [Protocolo](time_protocol.md) · [Recibo](time-evidence/receipt.json)

| C163 | Prefill observado | Corte de 10% | Teto com trabalho fora de WAIT fixo | Interior observado dos callbacks grátis | Todo o trabalho além do serviço retido grátis |
|---|---:|---:|---:|---:|---:|
| ON-1 | 9,059526 s | 0,905953 s | 0,653145 s | 0,653420 s | 4,031600 s |
| ON-2 | 9,058899 s | 0,905890 s | 0,660163 s | 0,660408 s | 4,005769 s |

A ablação gerou de novo a sequência física de reservas de C163. O comparador juntou as admissões pela chamada, tile, camada, wave, expert e papel de procura ou preload. O preload conserva como origem a wave que o emitiu. As liberações e deadlines provêm da geometria do target. EARLY e LATE concordaram nos 851 serviços retidos e 50 removidos. O candidato acrescentou zero leituras dentro do prefill. O teto admite gratuitamente quaisquer novos serviços, transferências, reconstituição e redispatch dos quatro workers. Abrange todos os callbacks das duas chamadas, incluindo as waves cujo conjunto de misses se conserva mas cujos slots ou filas podem mudar.

Para cada geração retida, o início mais cedo permitido é a primeira DEMAND da wave emissora e o fim mais tardio é WAVE_DONE ou REMAP_DONE da wave consumidora. A duração mínima assumida é o LOAD_BEGIN→LOAD_END do mesmo expert e braço, menos a resolução de 1 µs. A precedência individual e a soma do serviço dos jobs inteiramente contidos em cada intervalo, dividida por quatro, dão limites inferiores. O caminho mais longo acumula limites dos intervalos disjuntos. A diferença para o relógio original dá o teto. A ordem das quatro workers é livre e cada chamada é tratada separadamente na fronteira drenada. O segundo teto da tabela concede custo zero desde a primeira DEMAND até DONE em cada callback mensurável. No diário das waves faltam o carimbo de início e o de retorno real; na sensibilidade mais permissiva fica grátis inclusive o compute nesse interior indistinguível. [Cálculo](timing.py) · [Fixtures](test_timing.py)

A diferença para o corte chega a 252,808 ms e 245,727 ms no cenário que congela trabalho fora de WAIT. Um ganho maior dependeria de mudança no serviço por contenção ou em trabalho fora dos intervalos observados. Quantificar esse mecanismo exige comparar serviço e callbacks com limites completos num candidato, numa ablação e em R0 contemporâneos. O relógio deste ensaio não identifica tempo de cliente ou ganho no regime de 40 slots.

Reprodução com destino exclusivo, a partir da raiz do projeto:

```sh
out=$(mktemp -d)
python3 research/prepin44/timing.py --raw-dir "$TESY_C163_RAW" --new-output-dir "$out/time"
```

Dois ensaios locais consumiram 1,72 e 1,57 s, pico 128 596 KiB. O primeiro calculou os limites de WAIT e de serviço retido; o segundo incluiu a sensibilidade intermédia previamente prevista. Quatro fixtures model-free passaram. Recibo SHA-256 70528097dc08d8792d58b1a447cf1ab10389b1ee7879b6aeb9a1c99f824dae7e.
