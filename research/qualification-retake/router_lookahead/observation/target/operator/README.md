# Oferta +1 com o router residente na CPU

**Uma SGEMM por sítio trouxe o produtor para dentro do prazo de prefill CPU em 63 dos 71 sítios com um acerto identificado**, no cenário de 4,5 GB/s. Com o projetor escalar, a primeira leitura cabia em 11. A comparação combina o custo observado neste operador com a janela do mesmo sítio no C292, desde a última wave da camada fonte (E23) até ao primeiro de aceitação pelo worker (E13) e espera do consumidor (E19). Concede uma ligação ociosa e a escolha antecipada da chave correta, sem enfileiramento, SET ou custo de obter a ativação. [Prazos no C292](../../../demand/deadlines/README.md) · [Protocolo](protocol.md)

| Fase e destino | Sítios | Escalar, ms | BLAS, ms (p10–p90) | Diferença emparelhada, ms | Sítios com hit | Primeira leitura a tempo a 4,5 GB/s¹ | A 8 GB/s¹ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prefill CPU | 72 | 6,904 | 0,307 (0,291–0,308) | 6,597 | 71 | 71 / 11 / 63 | 71 / 11 / 71 |
| Prefill CUDA | 31 | 6,912 | 0,342 (0,322–0,344) | 6,570 | 28 | 4 / 4 / 4 | 7 / 4 / 5 |
| Decode CPU | 96 | 0,216 | 0,017 (0,016–0,017) | 0,199 | 57 | 1 / 1 / 1 | 39 / 19 / 39 |
| Decode CUDA | 44 | 0,216 | 0,017 (0,016–0,017) | 0,199 | 26 | 3 / 3 / 3 | 4 / 4 / 4 |

¹ Ordem das três contagens por taxa: projeção grátis / escalar / BLAS. Cada sítio contribui uma vez, pelo prazo mais cedo entre as gerações acertadas. As colunas temporais dão a mediana entre sítios das oito medições por modo, e a diferença usa os oito pares de cada sítio. CPU e CUDA identificam onde o modelo consome o expert. Ambos os produtores da experiência correram no mesmo núcleo da CPU. [Recibo compacto](receipt.json)

**Exatidão.** Antes do timing, os dois modos reproduziram em ordem os 3 400 quartetos oficiais +0 de C270, as 3 303 previsões +1 previamente calibradas e todas as listas de até quatro ofertas. A máscara da camada final, a exclusão dos experts já presentes e os desempates por ID fazem parte do operador medido. Três controlos sintéticos exercitaram sinal, empate, ocupação e uma linha mascarada com NaN. Revalidámos cada resultado cronometrado. Esta paridade cobre decisões de routing em larguras 1, 29 e 32. A equivalência de logits F32, a generalização a outras entradas e as larguras 5 e 20 carecem de gold próprio. [Calibração anterior](../README.md)

**Construção e recursos.** As gammas, os biases e as matrizes originais ocuparam 37 164 800 B para destinos CPU e 16 352 512 B para destinos CUDA. A representação previamente arredondada das 11 matrizes CUDA somou 16 220 160 B. O banco total foi de 69 737 472 B. Um backend que consiga referenciar os originais residentes só precisa de materializar os coeficientes adicionais e o scratch aplicável. A preparação em RAM demorou 50,882 ms para reabrir, autenticar e carregar os dados, 1,797 ms para a validação de finitude e 3,731 ms para o arredondamento. O scratch principal BLAS tem 385 024 B; a ativação escalar no stack tem 11 520 B. O máximo do scope completo foi 212 934 656 B, com swap zero. AMD Ryzen AI 9 HX 370, CPU lógica 0, uma thread OpenBLAS, AC presente, Tctl de 47,875 a 62,875 °C, 10,03 s para a família. Zero forwards e zero bytes do GGUF. [Código nativo](operator.cpp) · [Supervisor](run.py)

**Decisão.** O custo de projeção residente justifica testar a sua integração assíncrona para prefill CPU. Nas 28 janelas de prefill CUDA com acerto, mesmo a projeção grátis só permite a primeira leitura em quatro a 4,5 GB/s. Para avaliar uma conversa falta observar disponibilização da ativação no host, disputa de CPU e NVMe, ordem das quatro ofertas e publicação antes da procura. A medição do operador inclui normalização, SGEMM ou dot escalar, bias, top-4, filtragem e ofertas em RAM; a cópia D2H, a sincronização e o trabalho dos quatro workers ficam fora dessa janela.

## Reprodução

Freeze do método `146acdbf`, fonte limpa `255315187f275951be06d26c9b11233233dc55ec`. Na checkout congelada, definir `TESY_ROOT` para o repositório e `TESY_ARCHIVE` para o arquivo privado que contém as partes 23 e 95. A família abaixo usa uma identidade e um destino novos. O recibo original `/tmp/tesy-router-resident-operator-20261125-r01/receipt.json` tem SHA-256 `ada7bd601df6f63b82f788b23dae62d9c935a06cca95576652f9dbda980fa55d`. A reabertura conferiu a distribuição dos 1 944 pares a partir das durações brutas e a inatividade do scope.

```sh
unit=tesy-router-resident-operator-replay
study=research/qualification-retake/router_lookahead/observation/target/operator
systemd-run --user --scope --quiet --unit="$unit" \
  -p MemoryMax=1G -p MemorySwapMax=0 -p RuntimeMaxSec=150s -- \
  env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 BLIS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /usr/bin/time -f '%e s %M KiB' timeout 120 prlimit --as=536870912 -- \
  "$TESY_ROOT/.venv/bin/python" -IB "$study/run.py" --unit "$unit" \
  --c7 "$TESY_ROOT/c7-native-placement-screen-20260927-1117utc" \
  --bundle /tmp/tesy-router-lookahead-diagnostic-20261125-r01 \
  --part23 "$TESY_ARCHIVE/part-23" --part95 "$TESY_ARCHIVE/part-95" \
  --original /tmp/tesy-router-c292-demands-20261125-r01 \
  --new-output-dir "/tmp/$unit"
```
