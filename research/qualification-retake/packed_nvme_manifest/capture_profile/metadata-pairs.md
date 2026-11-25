# Identidades dos metadados para o pré-voo

A confirmação independente R02 da colocação usa os mesmos pesos, código, limites e critérios de R01. Como ambos os índices contêm um caminho absoluto próprio, seus digests e os dos respetivos recibos diferem. Antes de executar o loader, fixa-se o par no comando e exige-se que o construtor tenha usado precisamente a derivação indicada. Cruzar as duas produções é falha.

| Produção | SHA-256 da derivação | SHA-256 do construtor |
|---|---|---|
| R01 | `80d71b6ee146be81c4e07c5b17dde0786effde6fa58ecd3268491eda6c810810` | `ddeabdee9c60a0c5bc5eb4ec9726c864c800d066ec8c55bfccb41a412a2be2ba` |
| R02, escolhida para esta corrida | `cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9` | `c81c15cb9614fd2780f35d5f3fc2b96ce280056f9da363ca74b42b112d1642f1` |

O R02 de metadados correu no commit `b809f186e7df3ee8b8b4ef1d6d1e7550d222fdbe`. O protocolo de resolução, o digest de colocação integral e o critério de aprovação dos dois mapas continuam os mesmos. [Pré-registo do loader](protocol.md)
