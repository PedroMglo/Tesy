# Quanto falta ao primeiro conteúdo final se o decode chegar a 6 tok/s?

Nos dois pedidos T2 naturais com pack, o cliente recebeu o primeiro conteúdo final aos 18,515 e 18,313 s. À meta exata de 6 tok/s, os 47 tokens do relógio do servidor dispõem de 7,833 s de decode. Mesmo concedendo ao cliente toda a redução desta fase, ainda faltariam 7,417 e 7,379 s no restante pedido. Estes números refinam a escolha de intervenções para M4. [Recibo das duas ordens](evidence/ordens.json) · [Cálculo para os seis braços](evidence/decode_budget.json)

| Ordem e braço de produto | Primeiro final observado, s | Decode observado, s | Primeiro final se o decode fosse gratuito, s | Redução adicional necessária a 6 tok/s, s | Prefill admissível se pagasse toda a diferença, s |
|---|---:|---:|---:|---:|---:|
| ROP · pack | 18,515 | 8,930 | 9,584 | 7,417 | 2,404 |
| POR · pack | 18,313 | 8,768 | 9,545 | 7,379 | 2,405 |

A conta é condicional ao mesmo trabalho, 2 044 posições de histórico, 153 novas, 47 saídas e os mesmos frames. Usa o primeiro conteúdo final no relógio do cliente e a duração total do decode no servidor. Dá crédito integral a cada redução antes do primeiro final e fixa as restantes fases. O crédito pode ser menor porque há trabalho depois desse frame. Uma nova agenda que desloque trabalho através daquele corte precisa de medição direta. Se só o decode mudasse e todo o seu ganho se refletisse no primeiro final, o teto de duração para cumprir 10 s seria 0,416 s em ROP e 0,455 s em POR, equivalentes a 113,0 e 103,4 tok/s. Nos quatro braços sem pack, mesmo a relaxação de decode gratuito excede 10 s. Atingir o alvo com o pack continua a admitir a composição de ganhos que atinjam ambos os relógios no mesmo pedido. [Crivo anterior de bytes e banda](../product-protocol.md)

Reprodução sem modelo a partir da raiz, com um diretório de saída novo.

```sh
python3 research/qualification-retake/packed_nvme_manifest/server_profile/conversation/decode_budget.py --new-output-dir "$TESY_NEW_BUDGET"
```
