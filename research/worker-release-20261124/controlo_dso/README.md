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

## Aresta do grafo no DSO original

**PASS no scheduler GGML CPU da biblioteca histórica.** A primeira chamada de decode do braço C317 nominal-2, camada 4, tem 128 scores reais autenticados. O grafo executou ARGSORT, VIEW, CONT e MAP_CUSTOM1, com uma tarefa de remap. O resultado ordenado foi [13,22,60,72], igual aos quatro registos de routing do target. Cada um dos quatro workers foi identificado e terminou após a destruição do manager. A fila terminou vazia e ficaram zero claims. A referência independente conferiu as três componentes de cada destino. [Recibo da confirmação](edge-confirm01.json) · [Preparação e verificação](edge.py) · [Aresta nativa](edge.cpp)

| Rank | Expert | Slot e geração no router histórico | Slot e geração no ensaio |
|---|---:|---|---|
| 0 | 13 | falta, nova reserva 20/5 | 0/1 |
| 1 | 22 | residente 10/2 | 1/1 |
| 2 | 60 | residente 0/2 | 2/1 |
| 3 | 72 | residente 1/1 | 3/1 |

A cache vazia força os quatro caminhos de entrega de bytes. Apenas os scores e o routing provêm do C317. Os pesos de serviço são sintéticos. Não se executaram o predictor, a atenção, o FFN completo, os logits, uma conversa nem uma operação na GPU. O pin ggml carrega bibliotecas CUDA transitivamente, registadas entre os mapeamentos do processo. O scheduler só tem um backend CPU. O OpenMP instalado tem o SHA-256 `1e20cd85…`, diferente do histórico `637b2ab4…`; o ambiente de uma futura medição integrada requer qualificação própria. O gate de símbolo exige que a definição do callback seja efetivamente a da libllama original. Doze componentes corretas e a concordância nesta linha de scores constituem o âmbito da prova.

```sh
python3 -B research/worker-release-20261124/controlo_dso/edge.py \
  --backend "$TESY_C305_BACKEND" --raw-dir "$TESY_C317_RAW" \
  --libllama "$TESY_C305_LIBLLAMA" --ggml-dir "$TESY_C317_GGML_DIR" \
  --new-output-dir "$TESY_NEW_EDGE"
```

Confirmação em checkout limpa `88278d4d16936e884093ff2647047b4318a92787`, com 55 566 336 bytes alocados antes do recibo, 369 272 KiB de RSS na compilação e 321 940 KiB na execução. Recibo SHA-256 `0960fb9b736f96ea2c47d8652ca66616a2d122684136f049ae404ce36ef5cbd0`. A exploração r01 foi interrompida antes do grafo porque a PLT do executável impedia identificar o proprietário do símbolo. O recibo preservado tem SHA-256 `3e0f7a17af7bf88272251529781ec37a39b79e567e355c655d7b0b330ebbd69b`. O cliente recompilado com endereçamento independente da posição permitiu validar a definição sem mudar o DSO. A exploração r02 e a confirmação usaram diretórios novos.

## Condição de retoma

O próximo ensaio deve comparar o mesmo callback ligado a A e B, com preads livres e mais de uma rota, e registar a primeira divergência dos tickets e o destino de cada leitura. Um controlo explícito de despacho pode restringir a continuação aos casos com procura autoritativa elegível. A reconstituição de uma entrada histórica no decode tem de atravessar o prefill incremental de 153 tokens, pois o snapshot inicial C317 antecede essa chamada. Para admitir timing de produto, o observador integrado terá de provar primeiro neutralidade OFF/ON e a mesma matriz completa finita de 33 × 201 088 logits em cada caso. O fixture de uma camada funciona com o DSO original e serve de referência antes desse investimento. A política de recursos e o binário do launcher exigem recibos contemporâneos para qualquer nova execução 120B.
