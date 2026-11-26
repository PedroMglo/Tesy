# Qual o custo de voltar a uma linha na primeira camada CUDA?

**Mesmo oferecendo gratuitamente o prefixo em bloco, seria preciso retirar pelo menos 51,81% ou 62,49% da duração das callbacks que sobram para obter o primeiro conteúdo final em 10 s.** Os valores respeitam aos dois pedidos naturais observados e mantêm o preço do sufixo de cada linha desde o primeiro remap da camada 25 até ao retorno. Apagar metade das callbacks ainda daria **10,187 s no P97 e 11,281 s no P106**. O decode isolado tem margem nos dois. [Critérios anteriores à conta](protocol.md) · [Recibo com os dois relógios e as contagens](receipt.json)

| Pedido e preço do sufixo | Tempo imputado ao sufixo até à primeira peça | Primeiro final com 0% / 50% retirados dos remaps | Decode de 47 saídas com 0% / 50% retirados | Mínimo a retirar perante os dois alvos | Verba por tentativa ao retirar 50%, limitada pelo primeiro final |
|---|---:|---:|---:|---:|---:|
| P97, L25 até retorno | 1,043 s | 15,336 / 10,187 s | 5,805 / 3,567 s | 51,81% | −18,690 ms |
| P97, só callbacks L25–35 | 0,938 s | 15,231 / 10,082 s | 5,690 / 3,452 s | 50,79% | −8,178 ms |
| P106, L25 até retorno | 1,061 s | 16,409 / 11,281 s | 5,920 / 3,692 s | 62,49% | −128,103 ms |
| P106, só callbacks L25–35 | 0,955 s | 16,304 / 11,175 s | 5,804 / 3,577 s | 61,46% | −117,544 ms |

O proponente causal faria 11 tentativas. Cinco rejeitariam a primeira proposta e só enviariam a âncora para o sufixo. Seis enviariam as três linhas. Assim, o decode cobra 23 linhas do sufixo e conserva as 23 chamadas ordinárias. A primeira peça chega durante a décima tentativa, após 21 dessas linhas. A parcela à qual se poderia aplicar uma segunda aceleração inclui os remaps das chamadas ordinárias, os das chamadas de prefill aplicáveis ao relógio e os dos sufixos cobrados. São 10,299/10,257 s até ao primeiro final e 4,476/4,456 s no decode. As duas colunas temporais têm trabalho em comum.

A 100% de eliminação dos remaps cobrados, o cenário L25 até ao retorno ainda admite 496,2/384,7 ms por tentativa antes da primeira peça. **NO_GO como intervenção isolada ou acompanhada de uma redução uniforme de 50% neste regime.** A margem a 100% serve apenas para testar combinações que atinjam os mesmos intervalos. O preço das linhas do sufixo é condicional à conservação dos custos AR observados; reagrupar o prefixo pode alterar residência, contenção e serviço. Os custos das linhas rejeitadas no prefixo, restauro de KV, cópias de ativações e sincronização ficam por medir. A igualdade bit a bit do prefixo para estes 47 tokens também está por demonstrar. [Limites numéricos observados no ensaio independente](../../../../../../../history_lookup/b3_numeric/first_boundary/router_row/integrated/README.md)

Os dois replays em CPU correram nos originais e nas cópias arquivadas, após o protocolo `ee0e9fb3` e o código `1e35a24a`. Levaram 1,44/1,42 s e 60 528/60 416 KiB de RSS. O SHA-256 idêntico é `2b1f7f3111cd5442d0177546ccbbff9180ca1e3a10067b056d6d399631201561`. As duas fixtures exercitam o corte a meio da tentativa, a carga única do sufixo e a recusa de uma camada ausente. [Implementação](score.py) · [Fixtures](test_score.py)

```sh
prlimit --as=536870912 --cpu=90 -- python3 -IB "$UNIT/score.py" \
  --p97 "$PACKED_P97" --p106 "$FULL_T1_P106" --new-output-dir "$NEW"
```
