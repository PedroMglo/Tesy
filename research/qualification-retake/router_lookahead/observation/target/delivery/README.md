# Dois experts de prefill chegam pelo mesmo pool sem segunda leitura

**GO para uma fixture com registos do tamanho real.** Em C305 sobre C291, o produtor e a procura consumiram o mesmo ticket e os bytes do mesmo FD do pack. Quando o expert 0 foi pedido, a sua leitura já tinha terminado. A procura do expert 1 encontrou a leitura em curso e aguardou-a. Os dois foram publicados pelos workers sem voltar a ler o pack. A proposta do expert 2 gastou uma leitura completa e não teve consumidor. Nos dois braços, o router recebeu os mesmos 128 IDs de slot, o payload e a geração de cada slot no fim coincidiram. [Contrato](protocol.md) · [Recibo reaberto](result.json)

| Trabalho no pack privado | OFF | ON |
|---|---:|---:|
| Leituras feitas pela procura | 4 | 2 |
| Leituras antecipadas pelos mesmos workers | 0 | 3 |
| Bytes devolvidos por pread | 49 152 | 61 440 |
| SET / bytes copiados para o primário | 12 / 49 152 | 12 / 49 152 |
| Pico de leituras em curso | 2 | 3 |

O processo usou quatro workers reais, um FD O_DIRECT no Btrfs do NVMe e 40 slots da CPU. O mesmo projetor do C292 calculou um único quarteto a partir dos marcadores em cada braço. O produtor repetiu a oferta nas 32 linhas. O remap por waves recebeu a mesma matriz autoritativa nas duas execuções. O OFF calculou a previsão sem emitir E/S. A oferta inteira deixou inalterados os 40 membros, estados, gerações, claims, idades e contadores de frequência. A procura usou a entrada 3 já residente e leu diretamente a entrada 4 que faltava à previsão. A entrada 2, cancelada durante a leitura, manteve o seu buffer até ao retorno de pread. O teste verificou o conteúdo final de cada uma das três componentes e o número total de SET. O teste obteve os mesmos slots para as quatro escolhas em cada uma das 32 linhas. [Fixture e barreiras](fixture.cpp) · [Verificador](review.py)

**Fronteira reutilizada.** C305 `c94780b1` deriva de C291 `c89c88b3`. A sua fila despacha primeiro a demanda, limita o trabalho especulativo a três e bloqueia um worker consumidor quando o produtor ainda está a ler. Essa espera continua no presente ensaio. O C305 original restringia a previsão a CPU2–24, rejeitava uma remap multi-token, procurava pelo identificador de call de decode e lia três janelas de GGUF por proposta. A fixture C305 completava manualmente a primeira leitura antes de iniciar o pool. O C309 e o C318 já estudaram o custo dessa intervenção em decode. [C305](../../../../../C305-CPU-STAGING-NATIVE-BOUNDARY-FREEZE-20261007.md) · [Fixture C305](../../../../../../tools/expert_staging_fixture.cpp) · [C309](../../../../../C309-UNTRAINED-STAGING-COST-NO-GO-20261007.md)

A extensão privada preserva a prioridade e os estados do C305, acrescenta uma identidade de chamada/tile a cada item de demanda, expira as propostas erradas com os ranks da wave 0 e usa o reader C291 para uma janela contígua. Os bytes das três componentes pertencem à entrada da arena até os SET acabarem. Para a contraprova, o produtor do expert 1 ficou retido enquanto o consumidor já tinha a claim; o ensaio mudou a geração do slot sob o mutex. O worker rejeitou a entrega antes do primeiro SET, preservou a claim da geração nova e drenou a entrada. A alteração explícita de abandono corrige o caso em que o ramo herdado liberava a claim sem comparar a geração e deixava a entrada READY marcada como procurada. A cópia integral nos casos positivos e o negativo de geração são observações distintas. [Alteração do manager](overlay.py)

O marcador tem três slabs de 4 096 B, janela de 12 288 B e stride de 16 384 B. A fonte de dados é sintética; a sessão não abriu o modelo nem usou a GPU. O tamanho de produção é 4 406 400 B por slab e janela de 13 221 888 B. Os eventos de sincronização dirigidos garantem a ordem dos casos e não fornecem timing de throughput. Permanecem por testar as janelas completas à escala da largura de banda e memória, a ligação entre o callback produtor e a tile correta no C281, as grades numéricas e o desperdício real. A hipótese de poupar tempo ao pedido requer o custo das leituras erradas e da produção do sinal no mesmo braço.

R01 terminou antes da compilação porque o nome de cgroup passado ao supervisor omitia o sufixo `.scope`. R02 terminou antes de executar os braços porque o cabeçalho privado não incluía `<stdexcept>`. R03 executou e fechou em 4,344 s incluindo compilação, pico de 400 216 064 B e swap zero. Os dois FAILs e R03 têm identidades distintas. O comando abaixo reabre a medida sem executar o binário.

```sh
python3 -IB "$DELIVERY/review.py" --raw "$R03" --new-output-dir "$NEW"
```
