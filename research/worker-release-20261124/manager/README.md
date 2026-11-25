# O que faz o worker quando a leitura do expert já arrancou

**PASS funcional do controlo bloqueante no manager C305.** Com os três produtores já atribuídos e a quarta thread à espera do expert 1, a thread que terminou a leitura expirada do expert 2 aceitou a procura do expert 4. A publicação de 4 desbloqueou o remap. A leitura expirada de 3 prolongou o cleanup para lá do retorno do router. Esta observação admite testar uma continuação que deixe a thread de 1 avançar para 4 enquanto os três produtores continuam ocupados. A contribuição para o pedido C317 continua **INCONCLUSIVE**. [Protocolo congelado](protocolo.md) · [Recibo completo](confirm01.json)

| Braço | Eventos | Worker à espera de 1 | Worker de 2 que aceitou 4 | Destinos conferidos |
|---|---:|---:|---:|---:|
| OFF 1 | 0 | — | — | 12/12 |
| ON 2 | 63 | 1 | 2 | 12/12 |
| ON 3 | 63 | 0 | 1 | 12/12 |
| OFF 4 | 0 | — | — | 12/12 |

Cada processo executou o `worker_loop` do pin C305 com quatro threads, um remap de aquecimento e um remap com IDs fornecidos [1,4,8,9] numa camada CPU. Em cada braço houve três leituras C305, duas expirações em curso, uma espera, um consumo e zero erros. A procura direta fez três leituras adicionais, uma por componente. Os doze componentes dos quatro destinos ocuparam 52 876 800 bytes. A referência calcula os bytes a partir da fórmula congelada e verifica cada SHA-256, ordem dos ranks, slot e geração. Depois de finish ficaram zero claims e fila vazia. O digest conjunto foi `3aa0ce706797e89970774a75de6e180ea2e9b1cf95039f85932052c32adad74f`.

Os dois journals ON puseram a publicação de 4 na posição 48, a saída da barreira na 49, o retorno do remap na 50 e a entrada em finish na 51. A conclusão de 3 ocorreu na 57, antes de finish sair na 58. Cada journal tem o seu próprio relógio de processo. Os portões de serviço antecedem o syscall real e impõem a ordem causal. O journal mostra a espera no predicado da condição C++, sem identificar cada suspensão do kernel. OFF executa o mesmo binário e os mesmos portões com o journal desligado. O ensaio cobre igualdade funcional com dados sintéticos e threads reais. A duração dos braços inclui a verificação e a escrita da fixture pelo processo nativo. Não há estimativa da melhoria de decode, neutralidade temporal, sobreposição no controlador NVMe ou paridade numérica de um forward. Os slots de destino eram livres e as gerações observadas valiam 1. Reutilização de gerações, falhas de leitura e concorrência adicional de novos pedidos especulativos precisam de testes próprios.

## Reproduzir

O commit Tesy da confirmação limpa é `2fbf3aaa1293b10d918c0a00e6dd3b090dcc14fc`. O pré-registo está em `b0a0eaabc384134efcc4c5bdc2a7055fcbbc3192`. Fornecer uma clone local que contenha o objeto backend C305 pinado e o DSO CPU identificado no recibo. O runner extrai os blobs pelo commit, confirma a árvore e o hash do DSO e recusa diretórios de saída existentes. Executar a partir da raiz da checkout.

```sh
python3 -m unittest discover -s research/worker-release-20261124/manager
python3 -B research/worker-release-20261124/manager/run.py \
  --backend "$TESY_C305_BACKEND" --ggml-base "$TESY_GGML_BASE" \
  --new-output-dir "$TESY_NEW_OUTPUT_DIR"
```

A confirmação usou 110 198 784 bytes alocados antes de gravar o recibo final. O pico foi 390 664 KiB na compilação e 291 280 KiB por braço. O ficheiro sintético esparso tinha 1 692 061 696 bytes lógicos. Não houve GPU, modelo, pedido de rede ou consumo de um orçamento físico 120B. O recibo bruto da confirmação tem SHA-256 `3db174f3664530360c5463bc8a169632b358bba6bc5821f856c50d03a8d958a5`. A exploração anterior r01 ficou preservada no volume de projeto, com o protocolo já commitado e o código da fixture ainda por commitar. O SHA-256 do respetivo recibo é `d055f669670c371fac54526165edeca197e04fd391d7a16d494dd26099a6f229`.
