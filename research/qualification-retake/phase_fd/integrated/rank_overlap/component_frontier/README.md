# Disponibilizar partes do expert acrescenta menos de 2 ms ao teto do primeiro final

**Nos dois processos C291, mesmo libertando o cálculo de cada wave logo à entrada do remap, o primeiro conteúdo final ainda exigiria pelo menos 15,494450 s no P97 e 16,431270 s no P106.** Mantivemos o instante relativo da última publicação de cada wave, os custos de serviço e o restante pedido. A intervenção pode antecipar mais operação numa geração que ainda carrega pesos. No P106 essa possibilidade acrescenta 1,791320 ms ao teto anterior no prefill de 148 posições e zero no decode. O resultado exclui esta intervenção isolada para as metas conjuntas de 10 s e 6 saídas/s neste regime. [Pré-registo](protocol.md) · [Recibo por wave, fase e tier](receipt.json)

| T2, prefill e decode, CPU e CUDA | Piso anterior até ao primeiro final (s) | Novo piso até ao primeiro final (s) | Crédito adicional até ao primeiro final (ms) | Novo piso do decode, 47 saídas (s) | Crédito adicional no decode (ms) | Margem até 47/6 s (ms) |
|---|---:|---:|---:|---:|---:|---:|
| P97 | 15,496262 | 15,494450 | 1,811697 | 7,708371 | 0,584332 | +124,962 |
| P106 | 16,433061 | 16,431270 | 1,791320 | 7,863156 | 0 | −29,823 |

**Por que fica tão pouco trabalho adicional?** A conta anterior já autorizava antecipar toda a computação movível da wave desde a primeira geração completa. Onde havia um rank READY à entrada, o seu limite já começava nesse instante. Das 2 987 callbacks, apenas 11 waves de P97 e 10 de P106 tinham todas as gerações pedidas ainda pendentes. Nas restantes, o crédito adicional foi exatamente zero. Entre as inteiramente pendentes há ainda uma segunda limitação: a computação posterior ao remap tem de acabar antes da próxima wave ou camada que consome a sua redução, quando essa cerca está comprovada. No P106 as sete waves de decode com todos os ranks pendentes já esgotavam esse período. [Referência anterior sobre ranks completos](../packed_decode/README.md)

| Fase | P97, inteiramente pendentes / com crédito adicional | P97, adicional CPU / CUDA (ms) | P106, inteiramente pendentes / com crédito adicional | P106, adicional CPU / CUDA (ms) |
|---|---:|---:|---:|---:|
| Prefill, chamada de 5 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Prefill, chamada de 148 | 4 / 2 | 0 / 1,227365 | 3 / 3 | 0,535400 / 1,255920 |
| 44 avaliações até à primeira peça final | 7 / 1 | 0,584332 / 0 | 7 / 0 | 0 / 0 |
| Duas avaliações posteriores | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Só com CPU, a intervenção mais favorável deixa o primeiro final em 15,877166/16,814132 s e o decode em 7,949372/8,105443 s (P97/P106). As margens de prefill e decode partilham as primeiras 44 avaliações; cada crédito entra uma vez no seu próprio relógio.

## O que o pack permite observar

Verificámos as 7 012 linhas de rota, os 1 440 slots à entrada, as 2 354 gerações e a sequência de retorno do pread e dos três SET (gate, down, up) antes da publicação no host. Conservando a disponibilidade do primeiro SET gate registado, mas concedendo todo o cálculo imediatamente a seguir, os dois pisos do primeiro final são 15,494450 s e 16,431355 s. Concedê-lo logo após o pread integral também dá 15,494450 s e 16,431270 s. Esses limites descrevem pontos conhecidos do mesmo staging e continuam a ser otimistas para uma MMID que depende de várias gerações. O cenário principal liberta inclusive antes do pread e domina os restantes. [Instrumentação dos SET e da publicação](../../../../igpu_resident_rank/request_budget/device/pack_native/observer.patch)

A intervenção avaliada conserva o trabalho completo de gate, up, down, bias e redução, as posições e os tempos relativos de publicação e a independência dos leitores. Os limites concedem ainda IDs disponíveis à entrada, despacho e sincronização gratuitos e acesso imediato à marca do host no CUDA. A ausência de uma dependência posterior comprovada dá à alternativa a janela inteira. Não se adicionou o crédito dos ranks completos ao novo limite; ambos são avaliados sobre a mesma wave e a diferença mede apenas a extensão. Este resultado não determina o efeito de dividir/reordenar preads, alterar contenção ou o serviço de E/S, mudar residência ou libertar leituras de waves futuras. A fixture de cálculo CPU residente continua a descrever apenas a sua própria tile. [Equipa e tempos de MMID da C266](../../cpu_residual/resident_team/README.md)

## Reprodução

Protocolo `8f81a64b`, código `f6e8755c`. Cada um dos dois processos reabriu P97 e P106 e reproduziu integralmente o recibo de ranks completos antes deste cálculo. Ambos terminaram em 2,38 s, com RSS máxima de 60 792 e 60 784 KiB, sem leituras de matrizes, forwards ou GPU. Os dois recibos são idênticos byte a byte e têm SHA-256 `43739445cb7fdab6dd00aa07f14d3f253341cb2a16d38c5e1c80984064f02d42`. Destinos privados `/tmp/tesy-pack-component-frontier-20261125-r01` e `/tmp/tesy-pack-component-frontier-20261125-r02`. Os testes incluem prazos saturados, empate de publicações, parking, caso sem cerca e recusa de componente ou tempo inválido. O verificador exige também o controlo dos quatro cortes anteriores para cada população e relógio. [Código](screen.py) · [Testes](test_screen.py)

```sh
python3 -IB test_screen.py
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  taskset -c 4 timeout 60 prlimit --as=536870912 --cpu=60 python3 -IB screen.py \
  --archive /mnt/sdisk-ssd-ext/Tesy/outputs/qualification-20261124-nvme-01 --new-output-dir "$NEW"
cmp "$NEW/receipt.json" receipt.json
```
