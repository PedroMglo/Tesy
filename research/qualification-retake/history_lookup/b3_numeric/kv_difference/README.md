# O desvio de B3 alcança o conteúdo do KV

**REPRODUZIDO.** Após consumir os três mesmos tokens, AR e B3 guardaram
**54 696 valores F16 numericamente diferentes** nas posições novas. As
diferenças abrangem K e V nas camadas 13–35. Os 4 744 bytes de metadados
e todas as posições anteriores conservadas coincidem bit a bit. A família
física mantém o seu NO_GO para a paridade bit a bit neste prefixo.

| Posição no KV | Valores F16 diferentes |
| --- | ---: |
| 189 | 9 925 |
| 190 | 22 468 |
| 191 | 22 303 |

Na ordem do ficheiro, o primeiro byte diferente tem offset **1 376 620**
(base zero). Pertence ao elemento 0 de K na posição 190 da camada 13 do
banco de atenção global. Recordar que o escritor termina todos os K desse
banco antes de passar aos V e ao banco de atenção deslizante. A localização
no ficheiro delimita a observação. A operação que originou a diferença e
o seu efeito individual nos logits continuam desconhecidos.

Das 216 linhas K/V novas (36 camadas × 2 × 3 posições), 110 diferiram.
No banco global diferiram 13 591 elementos K e 13 937 V. No banco
deslizante diferiram 13 508 K e 13 660 V. Cada par de elementos divergente
tem dois valores finitos numericamente desiguais. Isso exclui tanto a
codificação de sinal do zero como um cabeçalho do serializador como
explicação para essas diferenças.

O snapshot de entrada inteiro coincide nos dois braços. Dos seus 11 412
linhas identificadas por camada, tipo e posição, 11 304 voltam a ser gravados no corte após três
tokens e mantêm os bits em cada braço. Os restantes 108 correspondem às
três posições que deixam a janela de 128 no banco deslizante (18 camadas,
K e V). O conteúdo físico de células omitidas pelo serializador fica fora
desta observação.

## Reprodução

Usar o checkout de medição `f0a4a497cff3855667fe3fcaaea311ad7d5519ec`,
o código C269 e o diretório da família original ou a sua cópia na
`part-32`. O verificador autentica os dois filhos, a colocação real descrita
nos stderr e os quatro snapshots. O protocolo foi fixado em
`27000ade13748b9e029804b2768b9ade03132410`.

```sh
env LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=1 \
  prlimit --as=268435456 --cpu=60 \
  python3 -IB research/qualification-retake/history_lookup/b3_numeric/kv_difference/screen.py \
    --backend "$TESY_C269" --family "$TESY_B3_FAMILY" --new-output-dir "$NOVA"
```

R01 esgotou o espaço virtual durante a leitura do primeiro snapshot,
antes da comparação. O locale da sessão colocava o Python em 250 300 KiB
de memória virtual ao arrancar. Com `LC_ALL=C` o valor foi 21 988 KiB.
R02 (originais) e R03 (arquivo) mantiveram o cap de 256 MiB e produziram
o mesmo recibo em 0,12 s cada, com RSS máximo de 73 852 e 73 768 KiB.
SHA-256 do recibo reproduzido
`36847d6fc28512ecb19204edaad3f32f390f27ef8f8f2b3ee087bf147c289156`.
As três saídas estão na `part-33` (3 ficheiros, 7 790 bytes), manifesto
`0dea3ce0ca7a1387b423cb10f164af7084c225f9634723c338ea85a3db387ec7`.
O diagnóstico usou somente os arquivos da execução encerrada.
[Protocolo](protocol.md) · [Recibo](evidence/receipt.json) · [Falha R01](evidence/fail-r01.json)
