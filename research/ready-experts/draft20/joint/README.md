# A poupança no prefill pode pagar a verificação no decode?

**NO_GO para adotar esta combinação aos custos conhecidos.** Com duas tiles em pipeline, banco renovável treinado, cópias dos hits pagas e proponente N2/M2 sem pesos, há margem matemática se o verificador de três posições custar em média **109,465 ms por bloco** sob a hipótese de preço uniforme em todos os cortes. O problema aparece também sem essa hipótese. Os dez blocos até ao primeiro conteúdo disporiam juntos de **1,095–1,394 s**. Nove deles acabaram estritamente antes da amostra 45 e já custaram **4,620 s** no 120B do portátil. Mesmo concedendo de graça o bloco que atravessa o primeiro conteúdo, esses preços dão **13,226–13,526 s** até ao cliente. Os resultados são condicionais à conservação dos custos. Não se realizou uma conversa com a combinação. [Protocolo](protocol.md) · [Preços e testemunhas por braço](evidence-20261128-r01/combined.json) · [Nove intervalos autenticados](evidence-20261128-r01/observed.json)

O cálculo substitui o prefill nominal de cada W por **4,104 s de P97** ou **4,197 s de P106**. Essas duas durações são pisos simulados para 5+148, ub32, só a partir dos dois diagnósticos correspondentes. Mantemos o custo W de cada passo serial fora dos blocos e todo o prefill do código. As escolhas e atualizações do proponente entram quando a âncora já está disponível. A primeira peça exige o bloco inteiro que a contém. A conclusão válida em código conserva o intervalo medido depois do decode. O custo de restaurar a entrada no primeiro decode, a disputa e o cleanup adicional foram concedidos de graça. Os hits de decode da simulação anterior não voltam a ser descontados.

| Controlo nominal / prefill substituto | Primeiro conteúdo com B3 gratuito, N2/M2 | Maior preço comum por bloco de N2/M2 | Primeiro conteúdo com B3 gratuito, maioria |
|---|---:|---:|---:|
| W3 / P97 | 8,811–8,813 s | 118,7–118,9 ms | 12,441–12,443 s |
| W3 / P106 | 8,904–8,905 s | 109,5–109,6 ms | 12,534–12,535 s |
| W4 / P97 | 8,606–8,607 s | 139,3–139,4 ms | 12,130–12,132 s |
| W4 / P106 | 8,698–8,700 s | 130,0–130,2 ms | 12,223–12,225 s |

O segundo proponente escolhe o par com maioria estrita no contexto mais longo de um a quatro IDs que já tenha duas ocorrências. No teste do portátil, o índice e a busca direta no prefixo tomaram as mesmas decisões até ao EOG. No nominal antecipou **2/8 IDs** em quatro blocos. N2/M2 antecipou **12/22** em onze. Mesmo com verificação gratuita, o decode nominal desta regra de maioria ficaria em 8,017–8,329 s para 47 IDs. Em código, os dois métodos anteciparam 13/36 e 40/92, respetivamente. O limite para preservar ambos os relógios dos dois W de código fica entre 405,6 e 408,2 ms por bloco para a maioria e entre 424,9 e 425,4 ms para N2/M2. Os 11 blocos N2 nominais medidos custaram 5,320 s. Se conservarem esses custos com o novo prefill, o decode leva **9,812–10,019 s**, acima dos 7,833 s permitidos. [Servidores anteriores com os mesmos 47 IDs](../../../qualification-retake/packed_nvme_manifest/server_profile/verified_block/server_reserve/causal_server/http/kv_width/natural/cpu_attention/target/http/family.md)

O custo de preparar o índice de maioria foi 1,828–3,306 ms nos dois pedidos e replays, conforme os valores brutos. O maior RSS dos dois processos foi 20 488 KiB, com 128 MiB admitidos. Somar o maior pico nominal W de 15 824 297 984 B, o payload adicional do banco de 4 666 377 600 B e todo o orçamento de 128 MiB do proponente deixa **298,6 MiB** antes da paragem preventiva E20. Essa conta só estabelece uma margem de capacidade. O pico dos buffers vivos, a cópia e a execução simultânea têm de ser demonstrados. Já o 20B completamente residente excedia RAM admitida mais VRAM mesmo sem o banco secundário.

## Correção do fim de resposta do 20B

A primeira unidade usou o número real de IDs restantes para passar a serial na cauda do código. O limite que um servidor conhece é o cap do pedido, 256 no nominal e 768 no código. Na nova fixture, o 20B reproduziu todos os 255 argmax da referência de código, emitiu as duas propostas do último bloco antes da confirmação e acertou EOG na primeira. O segundo ID foi emitido especulativamente e descartado. Os dois forwards custaram 41,794 e 40,823 ms. A contagem aplicável ao servidor passa a **162/188**, em **94 blocos** e zero passos de cauda. No nominal preserva-se **30/32** em 16 blocos. A seleção ideal do nominal foi recalculada permitindo B3 até à última posição. Os tetos simultâneos de 22,693 / 55,964 ms com auxiliar perfeito e de 21,275 / 52,466 ms com o 20B gratuito mantiveram-se. [Recibo da correção e novos percursos](evidence-20261128-r01/terminal.json)

Somámos apenas os dois forwards terminais desta nova execução ao serviço do 20B anteriormente medido. Com esse custo, o target teria em média **505,211 / 505,180 ms** em todo o decode de código e **476,609 / 477,645 ms** até à primeira peça. Oito blocos são diretamente comparáveis por prefixo e dois IDs aceites aos do servidor anterior. Passam a faltar 86 por observar. Se o preço desses oito se mantiver, os restantes 86 dispõem de **497,0–497,2 ms** em média. Todos estes valores pressupõem que os pesos do proponente já estejam acessíveis. A colocação simultânea e o produto integrado permanecem por medir.

**Condição de reabertura.** No pior braço, os nove intervalos conhecidos teriam de encolher em pelo menos **76,3%** se o décimo fosse gratuito e o resto continuasse fixo. Outra via é adiantar ou evitar trabalho obrigatório do target antes de o cliente esperar por ele, com um novo testemunho que localize os segundos retirados. Esta triagem fecha as duas combinações avaliadas e preserva R0 como controlo operacional, M3 PARTIAL e M4 NOT_MET.

O protocolo foi congelado em `8ac0db4f`. O 20B correu na CPU em `251b03a5`, árvore limpa, com C55 de 60,030 s e C118 de 60,164 s. A verificação integral do SHA ocupou 5,603 s, o processo 55,311 s. Pico de 12 941 127 680 B, zero swap, 94,875 °C na CPU, 58,49 °C na GPU e 36,85 °C no NVMe. A GPU fez zero forwards. Energia GPU amostrada 196,1 J em 54,61 s, energia total do portátil desconhecida. Os dois replays sem pesos duraram 0,19 e 0,20 s. O arquivo privado exclusivo preserva 22 ficheiros com 676 862 B. [Comandos e identidades](evidence-20261128-r01/provenance.json) · [Arquivo](evidence-20261128-r01/archive.json)

Na validação final passaram 444 testes de repositório, 42 gates adicionais e Ruff. Oito testes específicos cobrem a rejeição, EOG na primeira ou segunda proposta, a publicação de um bloco que atravessa o corte e a seleção da mesma agenda para os dois critérios. Os recibos compactos e os dois arquivos privados reproduziram os resultados sem carregar pesos.

~~~sh
u=research/ready-experts/draft20/joint
e="$u/evidence-20261128-r01"
python3 -IB "$u/compose.py" --check "$e/combined.json"
python3 -IB "$u/observed.py" "$e/combined.json" --check "$e/observed.json"
python3 -IB "$u/terminal.py" --check "$e/terminal.json"
~~~
