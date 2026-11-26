# Pode o backend CPU reconhecer a parte descartável de uma wave do FFN?

Pré-registo, 25 de novembro. A comparação isolada do MMID da CPU em 67be776eed9a478747d7204e76984b1c77e2c590 mostrou deltas com sinais opostos. A nova hipótese é suprimir também os resultados intermédios que nenhum consumidor consegue observar quando todos os IDs físicos são −1. Este teste estrutural pergunta se há de facto tal região no grafo da tile C266 CPU0 com o scheduler habitual, sem cb_eval. O seu resultado decide o investimento numa fixture de exatidão para fusão. [Primeiro corte do MMID](../parked_mmid/protocol.md)

## Evidência e condição de saída

Reconstruir a topologia executável da mesma tile de 32 posições a partir da construção de grafo autenticada da fixture. Preferir descritores sem alocação de pesos nem forward. Se necessário para reproduzir a ordenação do scheduler, preparar os descritores e os buffers da fixture presente sob um cap de 4 GiB. Registar quanto foi efetivamente compilado, lido, alocado e executado. Entradas distintas, pesos do modelo, GPU e timing de inferência têm orçamento zero nesta unidade.

Conferir o digest estrutural, 110 nós, 24 MMID, oito waves, uma só divisão de backend no FFN de referência, ou documentar a primeira divergência. Enumerar nós e dependências; para cada wave, isolar da primeira projeção até à saída do MMID down. Exigir os IDs físicos da mesma wave nos três MMID, IDs lógicos para biases, a relação entre gate, up, SwiGLU e down, e a ausência de qualquer consumidor externo dos intermediários que a região descartaria. Verificar o gate de fusão aplicável no pin C269 e a situação de views/outputs retidos. Manter o remap, o manager, o bias de down, a máscara e a adição por wave. O predicado dinâmico sobre os IDs só pertence ao futuro candidato.

- **GO_FIXTURE** se a região ficar individualmente certificada pelas dependências e pelo backend nas oito waves do grafo de referência. A etapa seguinte compara todos os bits, incluindo +0 e −0, com um único rank ativo, sinais de bias por rank lógico, efeitos de vista e inputs finitos.
- **NO_GO_LOCAL_FUSION** se a topologia e o predicado do backend autenticados excluírem o corte contíguo proposto. Identificar o primeiro edge, operador ou condição que falhou.
- **INCONCLUSIVE** se o extrator não identificar o grafo e a ordem realmente inspecionados pelo backend, ou se uma observação necessária ao veredito faltar. Distinguir o grafo lógico do recebido depois do scheduler.

Guardar a fonte e a árvore, o hash dos inputs e dos fornecedores, o comando, a tabela por wave e o resultado no novo destino. O teste não confere paridade numérica, nem redução temporal, nem autorização para alterar o launcher. [Fonte e fronteira do grafo de referência](../cpu0_suffix/source.md)
