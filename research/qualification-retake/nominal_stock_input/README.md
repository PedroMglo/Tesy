# Entradas dos dois turnos nominais de C281 no stock

**PASS nos dois turnos.** O renderizador C269 com a Jinja original e o stock e95426f com a Jinja de data explícita reproduziram byte a byte as entradas históricas de R0. Os dois tokenizadores oficiais reproduziram todos os IDs em cada posição. O turno 2 incorporou o conteúdo final que o primeiro turno realmente gerou e que o validador aceitou em C281. [Recibo e hashes completos](evidence-r01/receipt.json)

| Turno | Bytes do prompt em cada motor | IDs oficiais em cada motor | SHA-256 dos IDs i32le |
|---|---:|---:|---|
| 1 | 12 132 | 2 043 | `0946e5070c4bfcc945d584e0778e33fb544a46bc313201bfc26a5f72f547f7a0` |
| 2 | 12 933 | 2 197 | `cf7e9b19362c5aeaf5e54e2185048acac09ec55459fb4a6fc262ec434f037425` |

A Jinja stock de Aster aceita também a data de C281, `2026-10-05`, através de `tesy_template_date`. Nos quatro pares motor/turno, o controlo `2000-01-02` alterou apenas os dez caracteres da data. Os dois vetores partilham 2 043 IDs de entrada. No R0 físico, a geração anterior deixou um token adicional reutilizável em KV, permitindo o corte **2 044 em cache + 153 novos**. No stock, esse corte, a geração natural, o conteúdo final e os relógios do cliente continuam **NOT_RUN**. O próximo teste exige enviar a resposta efetivamente gerada pelo próprio servidor na história de T2 e observar o corte no pedido. [Conversa de referência em E20](../nvme_conversation/README.md) · [Protocolo](protocol.md)

Pré-registo `e198c217`, execução na revisão limpa `7e7278d7c34c18c9d98dca57159c6d7ddd6e3632`. O ensaio reutilizou quatro binários autenticados e um GGUF de vocabulário de 12 980 384 B com zero tensores. Parede **2,46 s**, CPU **1,70 s em utilizador + 0,55 s em sistema**, pico **355 732 KiB RSS**. Zero forwards, zero uso de GPU e zero abertura do GGUF 120B. SHA-256 do recibo `c3e0b72ecaa2e13ac6871af6cef5ef05d6ba1b5b7f76cf685177ce83f121b92c`. [Verificador](screen.py) · [Testes](test_screen.py)
