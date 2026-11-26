# Plano de cadência do primeiro decode nominal

**PREPARED_GROUP_CADENCE_ONLY.** As 36 camadas da primeira avaliação de
decode T2 têm 92 faltas e 52 hits no replay ClassLRU de 288 slots. Em uma
camada (28) todos os quatro experts já estão presentes. Três camadas têm
uma falta, doze têm duas, quinze têm três e cinco têm quatro. Estes números
fixam uma travessia de 276 SET de pesos (1 216 166 400 B), além de 576 B de
IDs D2H e 18 432 B de mapas H2D. O ensaio físico de cadência fica **NOT_RUN**.
O ensaio anterior de um fill já superou os quatro cortes de banda em ambas
as ordens. O plano fica disponível caso a futura execução integrada exponha
uma discrepância de cadência. [Protocolo prévio](protocol.md) · [Recibo](result.json)

O preparador reabre o PFJ P97, os offsets de C283 e a trajetória selada de
slots desde o início vazio de T1. Para cada camada guarda os quatro IDs
autoritativos em ordem, o mapa de 128 entradas antes e depois, os pares
expert/slot, SET na ordem gate–up–down e o resíduo de cada endereço original
na página. O mapa reduzido traduz os quatro slots ativos para 0–3 e atribui
−1 aos restantes experts. As duas cadências recebem exatamente esse mapa.
O plano preserva a lista upstream de chamadas antes da tradução. [Estudo de slots e coalescência](../natural_runs/README.md)

O futuro grupo pagaria 36 drains terminais nos dois braços; TRIPLET acrescentaria
92 drains intermédios. A medição por sítio inclui o retorno do SET do mapa,
as esperas e a aplicação do plano. Os 52 hits precisariam de inicialização
exterior no banco reduzido antes do respetivo sítio. A preparação, os poisons
e a verificação dos hits precisam de um contador e relógio próprios; uma futura
fixture pode materializar os marcadores no dispositivo por D2D para manter o
orçamento H2D de pesos. O intervalo do primeiro ao último sítio incluiria
esses trabalhos de preparação. Apenas a soma das paredes de serviço entra
no contraste pré-registado. O percurso em produção inclui dependências do
grafo, estado vivo do banco inteiro, política e custos de página adicionais.

Duas execuções exclusivamente offline produziram um plano privado de 57 935 B,
SHA-256 `be8a739377fe72085712a85f260637a5ea5032f270945ebe77a99ec678975287`.
O compacto é byte a byte idêntico nas duas (SHA-256
`b4791aac3082c8284423bf928793d728cc1f03e2d06b0ba3ed8d8a2690151806`).
O protocolo foi congelado em `fe80f080` e o preparador em `fefb3366`.
Os dois testes cobrem recuperação do slot da vítima, alias, hits falsos
e preservação da ordem dos SET. [Preparador](prepare.py)

```sh
python3 -m pytest -q test_prepare.py
nice -n 18 python3 -IB prepare.py --runs "$NATURAL_RUNS" \
  --pfj "$P97/ON/raw/events.pfj" --inventory "$C283_METADATA" --new-output "$NOVO"
cmp result.json "$NOVO/receipt.json"
```
