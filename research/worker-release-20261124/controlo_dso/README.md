# Qualificação da biblioteca usada pelo cliente C317

**NO_GO para a hipótese de religar um controlo bit a bit idêntico com o toolchain instalado.** Confirmámos o cliente C317, cinco bibliotecas e a sequência exata de 166 objetos (9 090 808 bytes). O comando de link original correu numa cópia privada. O ELF passou de 4 207 296 para 4 207 344 bytes. Conservar o DSO histórico original como referência independente permite prosseguir com o ensaio da aresta CPU.

| Propriedade | Original | Religado |
|---|---|---|
| SHA-256 integral | `d8460ecec23274ebba145530a1aacdb2746ee94969aba40b8b2beb38e0bb90d4` | `f28cf30e4830b86bf62612a11fd0e26be4fbe268e2b636bbe117914b1ef8704a` |
| GNU build-id | `2c15de0880cf0d332e73c042a7d904bb071cd7c3` | `aec137afca72fe59ba59d683b651bf6b901bc685` |
| Símbolos dinâmicos definidos | 4 698 | 4 698, mesma lista, valores e tamanhos |
| Classe, arquitetura, SONAME, NEEDED, RUNPATH | Referência C317 | Iguais |

O conteúdo de 28 das 30 secções nomeadas coincide, incluindo o código, os dados e as relocações. As duas diferenças estão em `.note.gnu.build-id` e `.comment`. A string da revisão GCC 16.2.1 Red Hat -3 instalada é acrescentada à referência Red Hat -2. Os cabeçalhos e o digest integral do ficheiro também mudam. A igualdade da interface observada é uma evidência mais estreita do que identidade do binário e não mede paridade de inferência. A receita operacional R0 continua a usar a sua versão qualificada.

Pré-registo `01ce65f7`, confirmação limpa `f6f1da1e`, 14 311 424 bytes alocados, 0,27 s incluindo inventário. O DSO e os registos de ligação ficam no volume local. [Critérios](protocolo.md) · [Recibo confirmatório](relink-confirm01.json) · [Reprodutor](relink.py)

```sh
python3 -B research/worker-release-20261124/controlo_dso/relink.py \
  --build-root "$TESY_C305_BUILD" --c317-protocol "$TESY_C317_PROTOCOL" \
  --new-output-dir "$TESY_NEW_RELINK"
```

A identidade publicada refere-se ao portátil. O reprodutor verifica o protocolo, o comando de ligação e o manifesto ordenado de objetos antes de chamar o linker. O SHA-256 do recibo é `1a01b31de14658fd038de46728866f24ef77a7ac072d51da991a207cb9949cfa`. A receção em checkout limpa confirmou a exploração preservada em r01, cujo recibo tem SHA-256 `d2cef1c60e22d589bd554f8c32ae7525594758c488dc60219f80c4dda709fa74`.
