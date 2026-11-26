# O que a primeira pergunta ensina sobre as faltas da segunda

**NO_GO no cenário CPU do P97 para a política de frequência combinada com previsão perfeita uma camada antes.** Usar as rotas do prefill de T1 para escolher as vítimas elevou a cobertura de 65 para 101 das 375 primeiras procuras estritas na CPU. A 8 GB/s, com transferência parcial e todos os outros benefícios concedidos, o piso ainda é de **95,035 ms** para um orçamento de **90,641 ms**. A política melhora a componente de prefill. Na agenda de decode reduz as oportunidades de entrega do banco em CPU de 143 para 41. O efeito no tempo de uma conversa com o banco ativo continua por medir. [Protocolo anterior à observação](protocol.md) · [Resultados compactos](result.json)

### Seleção feita antes da segunda pergunta

A PFJ C291 da parte 106 cobre as posições 0–2119 de T1, 74 278 quartetos e 4 548 ofertas reais de vítimas. Os primeiros 2 043 tokens contribuíram para a frequência. Foram selados os bytes do prefixo e os dois bancos antes do segundo POST. As 4 548 ofertas continham 2 001 chaves CPU e 828 CUDA distintas. Cada banco tinha 353 lugares. A recência sobre o T1 completo recuperou as mesmas 353 chaves do sufixo histórico. Só 37 chaves estavam nos dois bancos finais (24 CPU e 13 CUDA). As duas reproduções reconfirmaram o estado, a geração, a identidade e o claim de todos os 1 440 slots, os 7 012 quartetos de T2 e os 375 pares chave/sítio CPU. [Gate do journal](../../full_prefix/README.md)

| Escolha feita em T1 | Cópias CPU / CUDA em T1 | Payload de aquisição CPU / CUDA, GB | Primeiro uso estrito de CPU / CUDA em T2 | Entregas simuladas no prefill CPU / CUDA | Entregas simuladas no decode CPU / CUDA |
|---|---:|---:|---:|---:|---:|
| Últimas vítimas (LRU) | 3 238 / 1 268 | 42,804 / 16,762 | 65 / 21 | 110 / 45 | 143 / 29 |
| Frequência do prefill, recência no empate | 1 126 / 423 | 14,885 / 5,592 | 101 / 49 | 171 / 126 | 41 / 35 |

Cada cópia representa 13 219 200 bytes úteis das três matrizes. Para as entregas, o banco chega a T2 fechado e oferece os mesmos bytes quantas vezes a agenda primária observada reservar a chave. Na política de frequência, 982 admissões CPU e 323 CUDA de T1 acabam sem qualquer entrega em T2. As contagens e os volumes são derivados do trace. A aquisição de uma vítima antes de sobrescrever o seu slot, os últimos leitores, as possíveis cópias D2H e a reposição do primário ainda têm custos em serviço. Nenhum deles recebeu um crédito em segundos.

### Composição por janela no relógio de referência

Em cada uma das 110 janelas desiguais do P97, retiram-se primeiro as chaves presentes no banco. Sobre os bytes restantes aplica-se o horizonte de antecipação da mesma tile. A tabela dá o piso residual em milissegundos no cenário de transferência parcial. O envelope retrospetivo escolhe até 353 ofertas de todo T1, respeitando a capacidade global e o crédito útil de cada janela. [110 janelas e as duas interseções](windows.tsv)

| Banda útil | Previsão sem banco | Previsão + últimas 353 | Previsão + frequência | Previsão + melhor seleção retrospetiva |
|---|---:|---:|---:|---:|
| 4,5 GB/s | 501,703 | 367,556 | 312,278 | 13,704 |
| 8 GB/s | 162,036 | 109,161 | 95,035 | 1,915 |

Com experts inteiros, a política de frequência custa pelo menos 381,888 ms a 4,5 GB/s e 118,973 ms a 8 GB/s. As ofertas de todo o turno incluem 321 das 375 chaves. A 8 GB/s bastariam 117 escolhas retrospetivas nos sítios certos para obter aquele piso de 1,915 ms. A 4,5 GB/s o ótimo usa 191 chaves. A seleção real de frequência precisa ainda de substituir no mínimo três entradas por acertos bem colocados a 8 GB/s ou 76 a 4,5 GB/s no cenário parcial, mantendo os demais créditos e concedendo a aquisição e a entrega. São condições para uma nova regra causal e os seus controlos; o turno futuro só foi usado para calcular o limite.

O défice de **4,394 ms** pertence ao relógio histórico da parte 97 sob essas concessões. Na nova sessão, o próprio exterior que resta depois de apagar as callbacks CPU já excede o alvo de 10 s em cerca de **1,21 s**. O seletor também ocupou parte do intervalo cronometrado do cliente antes de enviar o segundo pedido. A medição independente reconstrói esse relógio a partir do mesmo processo. [Orçamento do novo pedido](repeat)

### Reprodução e proveniência

Protocolo e política foram congelados antes dos resultados. O avaliador em `e7426db5527257969ecc7c2ceae0c261284fc4de` reabriu as partes 63, 97, 101 e o novo pedido. A cópia da família na parte 106 tem manifesto `d54f29ed903b5dbc772af42be9bd489dc15b2e9819de8cb8ac8b4dea7988a89d`. O original e a cópia produziram byte a byte o mesmo recibo `04765c8b016a1e69ce61ba150e985bed8c64a6d8e11d58bd7fb9f87768186dac` e a mesma tabela `a9596e4d0a0f3b6eb61d66cf5d9f50e0d693fb2c1a282a4ae6e1fc0774701be6`. O replay dura segundos na CPU e dispensa os pesos.

```sh
python3 -IB test_evaluate.py
python3 -IB evaluate.py \
  --session "$ARC/part-106/tesy-full-prefix-natural-physical-20261125-r01" \
  --session-sha256 90750b0ccf87d7f5ceb6d89b6b320e1bf9cf07c0082c1961a31f14b67326aee9 \
  --part63 "$ARC/part-63" --p97 "$ARC/part-97/tesy-c281-pack-observer-natural-20261125-r01" \
  --part101 "$ARC/part-101" --new-output-dir "$NOVO"
```
