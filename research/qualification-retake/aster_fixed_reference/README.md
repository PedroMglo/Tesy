# A resposta independente a Aster no histórico fixo C133

**O stock também omitiu Aster e falhou o validador C132 neste turno.** A omissão é reproduzível no runtime independente com os mesmos 435 IDs. A causa permanece INCONCLUSIVE. O primeiro conteúdo final chegou aos 377,850 s. Aos 600 s o turno ainda estava incompleto. O cliente manteve o mesmo POST e recebeu a conclusão natural aos 1584,289 s. A validação terminou aos 1584,290 s. **M3 continua PARTIAL.** C133 conserva 20 conclusões naturais, 19/20 no validador e a falha do turno 2 após 452 saídas. A experiência independente forneceu o primeiro turno e gerou apenas a resposta de T2. [Protocolo](protocol.md) · [Sessão C133](../product.md) · [Recibo físico](physical-r01/receipt.json)

| Fronteira medida | Resultado |
|---|---|
| Primer, slot 0 | 123 IDs novos, 1 saída, 87,633 s no cliente |
| T2, IDs totais / reutilizados / novos | 435 / 122 / 313 |
| T2, primeiro fragmento de raciocínio / de conteúdo final | 225,957 / 377,850 s |
| T2, conclusão de transporte / validação no cliente | 1584,289 / 1584,290 s |
| T2, saídas no contador do servidor / política | 495 / 768 |
| T2, prefill / geração no servidor | 213,599 / 1370,646 s, 0,360 tok/s |
| Cliente completo após READY, incluindo primer | 1671,943 s |

O cliente usou esforço medium, amostragem greedy, seed 42 e cap de 768 saídas. A contagem de saídas provém do servidor. O cliente mede fragmentos e conclusão no seu relógio monotónico. O mesmo PID produziu os bytes previstos em `/apply-template` e os 435 IDs em `/tokenize` com ambas as opções de `add_special`. A reserva do servidor utilizou contexto 8192, ub32/b256, full SWA, slot único e 161 experts em cache CUDA para 36 camadas. Modelo oficial GPT-OSS-120B MXFP4 em NVMe interno e llama.cpp stock independente e95426f, autenticados pelo PID e mapas de memória no READY. A pergunta de paridade do mecanismo e a comparação de velocidade no caso nominal de 153 tokens conservam os seus protocolos. [Contrato de entrada](../aster_split/README.md) · [Sonda anterior de oito saídas](../aster_turn2_budget/README.md)

**Recursos e encerramento.** O C55 recolheu 62 amostras durante 61,028 s e admitiu até 23 GiB. Este processo usou max 10 GiB, high 9,5 GiB e swap máximo zero. O C118 próprio recolheu 61 amostras em 60,212 s. O recibo regista um arranque, 2 POSTs de geração e 769 tokens de orçamento solicitado ao sampler. Tempo total do supervisor 1772,645 s, servidor 1711,967 s, READY 38,691 s e encerramento 0,795 s. O processo filho terminou com código 0 e o supervisor confirmou o seu encerramento. [Janela C55](c55-r01/receipt.json) · [Medição](physical-r01/receipt.json)

| Recurso e âmbito | Observado |
|---|---|
| RAM de pico do cgroup / swap final / OOM kills | 10 203 054 080 B / 0 B / 0 |
| Máximos de memória anónima / de ficheiro no cgroup | 468 619 264 B / 9 868 697 600 B |
| VRAM máxima amostrada / potência GPU máxima amostrada | 4382 MiB / 12,48 W |
| Temperaturas máximas CPU / GPU / NVMe | 71,00 / 51,38 / 59,85 °C |
| MemAvailable mínimo / PSI memória full avg10 máximo do host | 26 166 407 168 B / 12,60 % |
| Bytes lidos pelo namespace NVMe / rbytes deste cgroup no dispositivo | 3 619 330 719 744 / 3 618 126 602 240 B |
| Amostras do monitor | 2785 |

O contador do namespace abrange todos os processos no mesmo dispositivo. O io.stat regista a carga atribuída ao cgroup. O ensaio não integrou a energia do sistema. O limite de leitura era 5 TiB e o limite local de evidência privada 64 MiB. [Arquivo privado, lote 13](../private_archive/part-13.json)

**Limite da intervenção no runtime.** Para este histórico fixo e este validador determinista, qualquer otimização que preserve toda a sequência de IDs confirmados de uma das execuções que omitiu Aster, a terminação e a descodificação em texto conserva a falha de conteúdo. Pode reduzir a latência dessa resposta. Uma nova sessão natural pode apresentar ao segundo turno um histórico diferente. A cobertura dos restantes 19 turnos e a qualificação conjunta pertencem à receita de produto.

**Proveniência.** Pré-registo f3803c06, commit de medição `894c36c920b00e19b25a16bcf50cd396648b598e`, árvore `9ad98f9adb69adf8df5da806ee3bb1ee6dd7a4b0`. O primeiro precheck terminou antes de C118 e de arrancar o servidor, por faltar workloads/c133_diverse_session.json na checkout sparse. O segundo passou com os inputs da mesma revisão materializados. Os recibos publicados incluem o SHA-256 do original privado. [Precheck R01 conservado](precheck-r01/receipt.json) · [Precheck R02](precheck-r02/receipt.json)

Para auditar os validadores sem modelo, executar na checkout de medição:

```sh
python3 -B -m unittest discover -s research/qualification-retake/aster_fixed_reference
```

A reprodução física exige uma nova identidade e orçamento prospectivo. O comando utilizado invoca `profile.py` com `--expect-head` no commit acima, `--historical-results` na pasta C7/results, `--policy` na política da janela C55, `--binary`, `--build-receipt`, `--placement`, `--original-jinja` e dois destinos exclusivos `--new-raw` e `--new-output`. O precheck acrescenta `--before-inventory-only`. O prazo absoluto desta identidade foi fixado em 25 de novembro às 06:20 UTC. [Supervisor](profile.py)
