# Quatro buffers partilhados não recuperam o défice no P106

**NO_GO para usar os quatro buffers como cache read-through e chegar aos 10 s na segunda conversa, a 4,5 GB/s e com libertação no RANKS.** Mesmo dando ao preditor de uma camada largura ilimitada e informação futura, faltam 139,854 ms antes de usar estes buffers. Em 1 963 leituras não cobertas pelo banco FREQ353 até à primeira peça, quatro páginas partilhadas poderiam poupar no máximo **34 leituras, ou 99,878 ms** no piso de transporte. Restam pelo menos **39,975 ms de défice**, com o cálculo do preditor, arbitragens, cópias e os falsos positivos gratuitos. [Pré-registo](protocol.md) · [Recibo por pedido](receipt.json)

| Prefixo em P97 e P106 | Leituras do pack | Chaves distintas | Intervalos entre usos | Máximo otimista com quatro páginas |
|---|---:|---:|---:|---:|
| Até ao fim do prefill | 966 | 824 | 142 | 19 |
| Até à primeira peça | 1 963 | 1 466 | 497 | 34 |
| Pedido completo | 1 981 | 1 477 | 504 | 36 |

A retenção precisa de uma página para cada fronteira entre os dois usos do registo. Os intervalos foram ordenados pelo fim; cada um foi atribuído à página cujo último uso acaba o mais tarde possível antes do seu início. Esta escolha dá o máximo número de intervalos que cabem em quatro páginas com todos os usos conhecidos. Para ver a escolha gulosa, considere o intervalo aceite com fim mais cedo. Numa agenda ótima pode substituir o primeiro intervalo posterior da mesma página sem ocupar uma data posterior; usar a página com maior fim compatível preserva as outras páginas para os intervalos que começaram mais cedo. Os testes confrontam o cálculo com todas as combinações de seis intervalos que se tocam e se cruzam, a capacidades 0, 1 e 2. Para o teto deixámos ainda quatro primeiros hits de T1 completamente gratuitos. Dentro de cada célula não houve reuso da mesma chave. [Verificador](screen.py) · [Teste de enumeração](test_screen.py)

No P106, retirar trabalho suficiente ao teto já favorável exige pelo menos **48** leituras, equivalentes a **pelo menos seis páginas** nesta relaxação. Seis não constituem uma agenda com margem. No P97 a margem do cenário sem estas páginas já é positiva, 918,252 ms. Os 1 018,130 ms obtidos depois de oferecer todo o crédito são um teto. O veredito cobre o mesmo conjunto de reservas e os retornos e reduções históricos. Um cache obtido copiando vítimas diretamente dos slots primários tem outros momentos de aquisição e paga cópias. Um produtor disponível antes do RANKS também altera as janelas. [Preços e estados reais](../README.md) · [Taxa de equilíbrio e limite de interface](../bandwidth/README.md)

Protocolo 7240d891, código 6267d5d4. As duas execuções sobre os journals privados duraram 3,76/3,78 s e usaram 63 620/63 372 KiB de RSS. Recibo idêntico por conteúdo SHA-256 d5d5634c45c9b6a0a2e6bca75f82fad7104f482a139931088efe99e6f5dd0f83. O SSD do modelo e a GPU ficaram fora do ensaio. O ficheiro de evidência conserva também os dois relógios R0 utilizados no preço.

```sh
LC_ALL=C PYTHONUTF8=1 timeout 90 prlimit --as=536870912 -- python3 -IB "$UNIT/screen.py" \
  --archive "$ARCHIVE" --backend "$C291" --new-output-dir "$NEW"
```
