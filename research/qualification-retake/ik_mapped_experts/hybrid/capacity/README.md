# Capacidade de carga do cliente ik

**R02 qualificou a carga e um contexto vazio de 8 192 posições com ClassLRU de 288 slots.** As 108 matrizes de experts, com 60 914 073 600 B, permaneceram mapeadas no GGUF. O censo de contexto identificou uma vista CPU e uma instância CUDA para cada um dos 108 biases. O máximo de VRAM observado foi 6 150 MiB, com regresso a 2 MiB após o exit. A R01 permanece FAIL porque a pesquisa por nome só identificou a ocorrência CPU. Os dois ensaios terminaram com zero forwards. [Resultados e reprodução](physical/README.md) · [Protocolo da sonda](protocol.md) · [Admissão](admission/protocol.md)

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
