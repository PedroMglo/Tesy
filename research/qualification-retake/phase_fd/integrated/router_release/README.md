# Esperar pelo router ou começar antes

**NO_GO nos preços dos dois braços para libertar as leituras apenas no início da primeira callback do router**, mesmo concedendo todos os intervalos de cálculo entre as waves da mesma camada. Os pisos até ao primeiro conteúdo final foram **10,123 s e 10,073 s**, com 875 primeiras procuras em ambos. O excesso é pequeno e depende das durações dos preads e do restante fixo. O resultado não qualifica latência noutras execuções. O cenário concede capacidade ilimitada, elimina o custo de todos os hits e cópias e permite que qualquer leitura da camada termine só no fim da última wave.

| Libertação mais cedo admitida na relaxação | Piso com preços do braço 1 | Piso com preços do braço 2 | Resultado |
|---|---:|---:|---|
| Primeira callback do mesmo router | 10,122752 s | 10,073134 s | NO_GO no regime fixado |
| Fim da última callback do router anterior | 9,191926 s | 9,139823 s | HEADROOM_ONLY |

O prefill pôde esconder 1,617/1,615 s quando a libertação começou na primeira callback do mesmo router. Nas 46 avaliações unitárias não houve intervalo entre waves do mesmo router para esse crédito. Antecipar para o router anterior credita ainda o cálculo antes de os ranks seguintes serem conhecidos. Os 0,808/0,860 s de margem da segunda linha exigiriam provar quais as leituras autorizadas ou previsões que podem começar cedo, pagar as previsões erradas, staging, pins, cópias e reposição. Não existe uma agenda física demonstrada para essa linha.

A ordem das células foi verificada no relógio do grafo, com o serviço dos mesmos jobs autenticado nos dois ensaios NVMe independentes. Para o primeiro limite, o pread não pode começar antes da primeira callback que recebe os IDs no perfil testado. Um ponto anterior que exponha os IDs reais de uma camada teria de ser observado na produção e acarreta custo de coordenação. O regime com as libertações de origem só admitiu 4,003104 s para o serviço e os dois pisos isolados excederam esse valor. [Protocolo, âmbito e relógios](protocol.md) · [Contagens e crédito por fase](evidence/receipt.json) · [Código](screen.py)
