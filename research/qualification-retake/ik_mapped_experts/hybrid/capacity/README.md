# Capacidade de carga do cliente ik

O cliente foi ligado às DSOs CUDA sm89 do ik e o inventário das 687 entradas do GGUF foi preparado. Esta etapa executou três testes Python, o compilador e a verificação de símbolos e relocações do ELF. O cliente de capacidade teve **zero execuções**. A capacidade efetiva de criar o contexto 8192 e manter 288 slots na RTX depende da admissão física. [Protocolo da sonda](protocol.md) · [Admissão](admission/protocol.md)

| Identidade | SHA-256 |
| --- | --- |
| Família CUDA minúscula R03, 3 processos | `2d165f3e9c8f8108a04e758a5496e610cdbe0051afaee1fe1da35123b8373bfd` |
| Reabertura independente dessa família | `8bd67de71f07326e5d7fac23d32a7c9748b11388856e259949ee3591ca459293` |
| Build do executor de capacidade R01 | `aa1a4de30a776cf5918ae62daa23da3735fbbf278eb0a04c88f8621bf9f88d17` |
| ELF capacity-client | `af597dd51d1c9bd12a8f489b73e3d4a3a6fdf7adcfa3ef6313a0ddda8232a7b6` |
| Recibo da preparação de metadados R01 | `0c5a1e8b6f0155857b45336a1f8e6df6c3c0e6338415c3db943ddff7652e3a8a` |
| Plano dos tensores para o processo | `4c60c7ad261c4f61e85c576a08866dd71abb3d1003369bb2876ed3669f9f5730` |

A revisão `e83d99806154d71d538e7cb28d801a1e6193e7ee` foi ligada numa checkout limpa. O recibo do build vincula 15 fornecedores do ELF, o comando do compilador e 12 fontes. O plano usou o inventário C283 e o recibo da releitura direta da colocação NVMe. A única consulta contemporânea ao GGUF foi a identidade por metadados do sistema de ficheiros. A origem dos intervalos será verificada no processo por FD, offsets e VMAs.

O argumento `n_seq_max=1` fixa uma sequência. Neste pin, o getter de mesmo nome devolve o número de células KV. O verificador exige uma reserva de 8192 células e zero células usadas após a criação do contexto. O valor pedido ao cache é 3 821 010 944 B. Um grupo de 36 camadas com 288 slots e uma guarda requer pelo menos 3 820 348 800 B. A linha `context` do breakdown já inclui o banco.

Para reproduzir a preparação, usar `inventory.py --inventory C283.jsonl --placement COLOCACAO/receipt.json --new-output-dir NOVO` e as hashes do protocolo. Para recompilar, `build.py --help` lista as quatro pastas seladas, os respetivos digests e o mapa do loader. Os controlos portáveis correm com `python3 -IB test_capacity.py`. O supervisor autentica o plano, o ELF, as DSOs, os cortes E/L/C/F, as condições da C55/C118 e o fecho de cada processo. [Supervisor](admission/run.py)
