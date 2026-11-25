# A seleção de 353 vítimas tem margem que as duas políticas causais não encontraram

**HEADROOM_ONLY.** Entre as 2 829 chaves distintas oferecidas ao banco durante T1, existe um mesmo conjunto de 353 que, no cenário otimista, cobre tempo suficiente nos dois pedidos sem sequer mudar a verificação AR. A margem até ao primeiro final é **1,475 s no P97 e 0,315 s no P106**. A testemunha escolhe as chaves depois de ver T2. Em cada callback afetada até à drenagem concede gratuitamente o serviço de todos os experts, incluindo os que o banco não guardou. O resultado justifica investigar a qualidade da seleção e o preço residual. [Protocolo](protocol.md) · [Recibo do limite e das testemunhas](receipt.json)

| Agenda e escolha a K=353 | Margem para 10 s no P97 | Margem para 6 tok/s no P97 | Margem para 10 s no P106 | Margem para 6 tok/s no P106 |
|---|---:|---:|---:|---:|
| AR e recência causal | −2,905 s | +0,529 s | −4,168 s | +0,269 s |
| AR e frequência causal de prefill | −3,423 s | −0,345 s | −4,668 s | −0,618 s |
| AR e seleção retrospetiva | **+1,475 s** | +2,956 s | **+0,315 s** | +2,738 s |
| Prefixo em bloco, sufixo serial e recência | −0,419 s | +3,167 s | −1,543 s | +3,069 s |
| Prefixo em bloco, sufixo serial e frequência | −0,655 s | +2,570 s | −1,773 s | +2,444 s |
| Prefixo em bloco, sufixo serial e seleção retrospetiva | **+3,635 s** | +5,216 s | **+2,612 s** | +5,159 s |

Cada linha usa o mesmo banco nos dois pedidos, e cada testemunha vale apenas na sua agenda. Com AR, no P106 teriam de desaparecer pelo menos **96,80% dos 9,843 s** cobertos pela testemunha até à primeira peça. Na agenda repartida seriam 71,05% dos 9,022 s e ainda seria preciso pagar a verificação do prefixo. A mesma conta aplicada às duas políticas causais reproduz os défices da tabela. [Composição dos dois mecanismos e preços](../bank/README.md)

A procura gulosa acrescenta a chave com mais nanossegundos marginais em callbacks ainda descobertas. Foram testadas oito ponderações fixas, da atenção a um único relógio à soma dos quatro. O testemunho publicado em cada agenda foi escolhido pelas quatro margens, logo **não é uma previsão fora de amostra**. O certificado de capacidade limita a margem de qualquer banco AR ao primeiro final a +3,023/+1,785 s, e a de qualquer banco na agenda repartida a +4,274/+3,168 s. Estes limites individuais podem exigir bancos diferentes. Cada certificado soma o já coberto a, no máximo, 353 contribuições marginais no restante. [Implementação](oracle.py) · [Enumeração exaustiva pequena e contraprova de uma chave indisponível](test_oracle.py)

O protocolo foi congelado em `79a710bf` e o código em `b8e56fd6`. Duas reproduções levaram 1,76 s cada, com menos de 66 MiB de RSS e zero forwards. O SHA-256 do recibo é `615d5aa5f55bfdeeead270942ee2c4b2909dcfa7afe6a938891bfe56141b05c9` e o das duas listas integrais privadas é `e2e8daca3341a6556379280a8a90adabf2a439367565c1120afd1094f13e692b`.

```sh
prlimit --as=536870912 --cpu=90 -- python3 -IB "$UNIT/oracle.py" \
  --archive "$PARTS" --intersection "$COMBINED_RECEIPT" --new-output-dir "$NEW"
```
