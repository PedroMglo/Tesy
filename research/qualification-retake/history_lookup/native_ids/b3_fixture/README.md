# Decisão nativa B3 sobre o segundo turno observado

**O verificador compilado C269 reproduziu as 11 propostas da conversa.** Cinco blocos rejeitaram logo a primeira proposta. Nos seis restantes, o verificador aceitou as duas propostas e consultou também a linha do token bónus. Nenhum bloco natural aceitou apenas uma. As outras 23 chamadas foram AR. Os 34 passos de controlo produziram os mesmos 46 IDs subsequentes à âncora, até ao EOG. O resultado autoriza um teste de exatidão do target nas duas situações observadas. O custo de uma verificação de três posições e o estado KV real após rejeição continuam em aberto. [Crivo económico](../README.md) · [Pré-registo](protocol.md)

| Avaliações depois da âncora | AR | Blocos B3 | 0/2 | 1/2 | 2/2 | Propostas individuais descartadas |
|---|---:|---:|---:|---:|---:|---:|
| 32 | 19 | 7 | 4 | 0 | 3 | 8 |
| Todas as 46 | 23 | 11 | 5 | 0 | 6 | 10 |

O ELF original de C269 escolhe historicamente a ocorrência mais recente do bigrama e propõe os dois tokens seguintes. Só recebe o prefixo já confirmado. A função original `common_sampler_sample_and_accept_n` compara a proposta com cada linha e decide quando pedir a próxima. Os dois callbacks do executável devolvem o ID do target guardado para a posição consultada e registam o aceite. O teste compara o prefixo lógico com a referência em cada iteração. O descartado conta as posições de draft que a próxima proposta já não vê. No modelo real, a verificação de largura três pode computar também linhas que o sampler deixa de consumir. [Implementação nativa](native.cpp) · [Verificador por passo](run.py)

Seis casos sintéticos cobriram AR sem correspondência, rejeição no primeiro ou no segundo ID, aceite completo mais bónus e os cortes depois de um ou dois aceites. Num corte, o callback interrompe a tentativa de ler a primeira linha sem referência. Nenhum EOG ou token foi inventado para a preencher. As duas janelas naturais terminaram sem tentativa de consultar linhas fora da janela. Todos os passos, os totais e os SHA das bibliotecas coincidiram. [Comparação dos replays](evidence/replays.json) · [Build](evidence/build-r01.json)

## Fronteira seguinte

A primeira rejeição ocorre na posição 0 após a âncora e o primeiro aceite completo na posição 9. Num par numérico independente, reproduzir o T1 e a incorporação incremental de T2 com o mesmo estado de KV e dos pools. Em ambos os pontos, confrontar a linha completa finita e a escolha greedy com uma referência AR que tenha exatamente o prefixo correspondente. As linhas de uma hipótese divergente requerem a sua própria referência no ramo dessa hipótese. Para a rejeição, conferir também o próximo token e logits após repor o estado da conversa aceita. A contagem de descarte lógico desta fixture não mede a leitura, escrita ou reposição de uma página KV e não identifica o tempo de serviço dos experts. O efeito da largura três na aritmética e no routing deve ser qualificado antes de usar um preço B3 de desempenho. [Resultado histórico de largura dois](../../../../C245-B2-AMORTIZATION-RESULT-20261004.md)

## Reprodução e conservação

Pré-registo f1ba90fd, medição 642db2106f02aa9ec8f1b54f854040e4d0de24b0. O build durou 4,04 s com 249 668 KiB RSS. O primeiro despacho de replay recebeu uma recusa do sandbox no socket systemd antes de criar a unidade ou a saída. O recibo conserva a falha de despacho. Os replays R02 e R03 correram em processos separados, 0,53 s e 0,52 s, com 257 620 e 257 896 KiB de RSS pelo GNU time. Limites do cgroup de 512 MiB, swap zero e 120 s. Cada reprodução escreveu 54 637 bytes privados. As decisões e testemunhos de todas as iterações coincidem entre os dois recibos, que diferem somente no tempo do controlador. O arquivo privado part-30 agrega os quatro diretórios B3 e a outra fixture da unidade, com 83 ficheiros e 4 309 445 bytes. O SHA-256 do seu manifesto é `9eeb41dc68b93a71d4bca0adbe1c779416d5e9fae2e2ed353773edf94a3cc496`. Nenhum GGUF, GPU ou sessão do modelo interveio nesta unidade. [Despacho R01](evidence/dispatch-r01.json)

Na checkout limpa da medição, usar unidades independentes e destinos novos para o build e para cada replay. `BACKEND` identifica a checkout C269 original, `CAPTURE` e `VERIFIED` são os diretórios privados comprovados na unidade anterior. O digest de build publicado aplica-se à execução aqui documentada. Para outra compilação registar o seu próprio digest e conferir binário, headers e fornecedores.

```sh
r=research/qualification-retake/history_lookup/native_ids/b3_fixture/run.py
systemd-run --user --wait --pipe --collect --unit="$BUILD_UNIT" --working-directory="$PWD" \
  -p MemoryMax=512M -p MemorySwapMax=0 -p RuntimeMaxSec=120s \
  python3 -B "$r" build --backend "$BACKEND" --new-output-dir "$BUILD"
systemd-run --user --wait --pipe --collect --unit="$REPLAY_UNIT" --working-directory="$PWD" \
  -p MemoryMax=512M -p MemorySwapMax=0 -p RuntimeMaxSec=120s \
  python3 -B "$r" replay --backend "$BACKEND" --build-dir "$BUILD" --build-sha256 "$BUILD_SHA" \
    --capture "$CAPTURE" --verified "$VERIFIED" --new-output-dir "$REPLAY"
```
