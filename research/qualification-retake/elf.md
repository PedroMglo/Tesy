# Dependências que o linker resolve para R0

**MEDIDO em 24 de novembro de 2026. Identidade C281 NO_GO.** O linker resolveu os 23 objetos congelados. Dezanove têm o SHA-256 histórico e quatro mudaram. O executável mantém o digest `054e983528d35731e2dc6222f1418f2f08120ef83e0c5f2a8db11805dd38effa`. Dos 12 nomes pedidos diretamente pelo executável, o grafo de dependências estende-se a CUDA e OpenMP. O vDSO e o interpretador ficam fora do denominador de 23. O tempo da auditoria principal foi 0,439 s. Nenhum servidor ou modelo foi iniciado. [Protocolo anterior à resolução](elf-protocol.md) · [Recibo com todos os SHA-256](elf-evidence/receipt.json)

| Nome pedido ao loader | Ficheiro físico histórico | Ficheiro selecionado agora | SHA-256 histórico / atual, prefixos |
|---|---|---|---|
| `libcuda.so.1` | `libcuda.so.615.71.09` | `libcuda.so.620.70.06` | `85a8cc8cf004` / `aa6bd5117c0c` |
| `libgcc_s.so.1` | `libgcc_s-16-20260819.so.1` | `libgcc_s-16-20261029.so.1` | `c71a62b5ef44` / `5a52ae4a6f1b` |
| `libgomp.so.1` | `libgomp.so.1.0.0` | `libgomp.so.1.0.0` | `637b2ab4eedf` / `1e20cd85608b` |
| `libstdc++.so.6` | `libstdc++.so.6.0.36` | `libstdc++.so.6.0.36` | `fc224ee3cc56` / `49811507d8fc` |

As sete bibliotecas do backend têm o mesmo conteúdo. A função original `backend_library_hashes` reproduziu seis pares chave/digest. Para `libllama-server-impl.so`, a chave histórica e a chave atual são caminhos absolutos diferentes que designam o mesmo ficheiro por `samefile`; o digest é idêntico. A igualdade estrita de mapas falha neste ambiente relocalizado. Isto é uma diferença de proveniência de caminho independente das quatro mudanças de conteúdo. [Comparação com a função original](elf-evidence/backend-keys.json) · [Implementação](../../tools/run_bounded.py)

A resolução ocorreu no ambiente de loader limpo do protocolo. A sessão também estava sem overrides `LD_*` ou `GLIBC_TUNABLES`. O contrato de ambiente OpenMP inicial coincide, mas o `libgomp` selecionado tem digest diferente. O manifesto histórico identifica ficheiros físicos e hashes. Os nomes ABI na primeira coluna são os que o linker reportou na consulta. `ldd` inspeciona dependências de arranque e não observa mapeamentos por `dlopen` após a inicialização, alterações de variáveis efetuadas pela biblioteca, equipas OpenMP, execução de CUDA, logits ou tempos de inferência. O inventário anterior já apontava caminhos divergentes. Esta consulta identifica os substitutos e a divergência da chave do backend. [Contrato de OpenMP](../../tools/parallel_runtime.py) · [Inventário inicial](host.md)

Para requalificar esta instalação, congelar uma nova identidade de caminhos resolvidos, hashes e runtime paralelo, preservando o protocolo C281. Numa campanha admitida, comparar os mapas efetivos do processo e o seu ambiente no arranque e após ativar a computação de backend. Antes de timing, usar a referência numérica independente e verificar rotas, logits finitos e IDs nas fronteiras pertinentes. A equivalência funcional e as condições de armazenamento e memória continuam pendentes. [Verificações do servidor](../../tools/c2_server_run.py)

Reprodução em 60 s de orçamento, com as entradas locais de C281 identificadas no manifesto, sem GPU nem modelo. O diretório de saída deve ser novo.

```sh
python3 -B research/qualification-retake/elf_resolution.py --new-output-dir "$TESY_NEW_ELF_OUT"
```
