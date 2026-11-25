# Dois pedidos naturais no GPT-OSS-120B em E20

**2/2 conclusões naturais e válidas, com reutilização de histórico no mesmo processo. Os dois alvos de desempenho nominal ficaram por atingir.** No segundo pedido o primeiro conteúdo final chegou aos **21,443 s** e o servidor fez **4,523 tok/s** de decode para 47 tokens. O validador aceitou a repetição aos 21,735 s. M3 permanece PARTIAL e M4 NOT_MET. [Evidência, proveniência e hashes dos raws privados](evidence-20261124-r1/evidence.json)

**MEDIDO no portátil entre 24 e 25 de novembro de 2026.** O cliente HTTP genuíno de C281 pediu um código e enviou o conteúdo efetivo da resposta como histórico na pergunta seguinte. Ambas as sequências oficiais de IDs e os payloads de entrada corresponderam exatamente aos C281. O validador confirmou cinco dígitos na primeira resposta e igualdade exata na segunda. Nos dois casos observou-se `finish_reason=stop` e o marcador de fim do stream. O backend não expôs os IDs completos dos tokens gerados. [Contrato](protocol.md) · [Cliente congelado](../../../tools/optin_integration_client.py)

| Pedido | IDs em cache / novos | Tokens de saída | Prefill do servidor | Decode do servidor | Primeiro texto / primeiro final do cliente | Transporte completo / validação do cliente |
|---|---:|---:|---:|---:|---:|---:|
| c112-code | 0 / 2 043 | 78 | 64,443 s | 20,438 s · 3,817 tok/s | 65,199 s / 84,448 s | 84,891 s / 84,914 s |
| c112-repeat | 2 044 / 153 | 47 | 11,331 s | 10,391 s · 4,523 tok/s | 12,054 s / 21,443 s | 21,733 s / 21,735 s |

**FORMAL sob o restante trabalho fixo.** Subtrair todo o decode do segundo pedido ao tempo até primeiro conteúdo final deixa 11,052 s, acima dos 10 s nominais. A meta de 6 tok/s para estes 47 tokens admite 7,833 s de decode e exigiria retirar 2,557 s, ou 24,61%, ao decode observado. Estes cortes são condicionais ao braço natural medido. O histórico C281 com 153 novos e 47 de saída registou 21,091 s até ao primeiro conteúdo final e 10,230 s de decode, noutra data física. Um único braço contemporâneo não identifica o efeito causal da nova colocação NVMe. [Controlo histórico](../../../results/c281-persistent-r0-runtime-20261005/compact.json)

A meta de primeiro conteúdo final exige atuar nas duas fases neste braço. Se apenas o prefill desaparecesse, mantendo o restante pedido fixo, sobrariam **10,112 s**. Se o decode passasse exatamente a 6 tok/s para os mesmos 47 tokens, a redução total seria 2,557 s. Mesmo concedendo que toda essa redução ocorresse antes do primeiro conteúdo final, o cliente chegaria aos **18,885 s**. Faltariam ainda **8,885 s**. Se viessem inteiramente do prefill, o seu orçamento seria de apenas **2,445 s**. São contas condicionais entre durações, preservando trabalho e saída natural deste turno. Uma receita que altere os tokens ou a posição da primeira emissão final requer medição de produto com o validador congelado.

A janela C55 R3 admitiu um cap de até 22 GiB; o serviço manteve o cap de 20 GiB com swap zero. O C118 imediatamente anterior ao Popen recolheu 61 amostras em 60,146 s. No processo observaram-se os 23 objetos de runtime verificados, porta local pertencente ao PID e SHA do GGUF confirmado pela colocação. O C270 contemporâneo passou o gate numérico antes do ensaio. Readiness após Popen em 3,933 s, serviço ativo 111,54 s, unidade completa 173,576 s. Pico do cgroup de 15 728 447 488 B, VRAM de 6 848 MiB, CPU a 83,5 °C e swap zero. A GPU atingiu 57,89 °C e o NVMe 52,85 °C. O monitor observou até dois FDs diretos do GGUF e zero buffered. O servidor encerrou com código 0 após a paragem pelo dono, sem eventos de OOM, e deixou a porta sem listener. Energia física e contagem de forwards ficaram sem medição. [Gate numérico](../nvme_r0_gate/README.md) · [Admissão](../nvme_admission/README.md)

A execução física partiu da checkout limpa `3b5118750e0f37efb689e200c035f1528d1e2a18`. A prova de entrada fixa os dois hashes oficiais, o binário e o conjunto exato de dependências. A aceitação temporal usa GETs/POSTs apenas no listener do próprio processo. O resultado cobre um arranque, um par e um cenário nominal. Faltam os contratos de qualidade/sessão sustentada, proteção de código e desempenho do avaliador. [Recibo de entradas](inputs.json)

## Reprodução

O teste do listener usa apenas loopback. A compactação verifica os recibos e os dois terminais aceites, com os timestamps de transporte e validação separados.

```sh
python3 -B research/qualification-retake/nvme_conversation/test_session.py
python3 -B research/qualification-retake/nvme_conversation/compact.py --raw-root "$C281_RAW_LOCAL" --new-output-dir "$NOVO_COMPACTO"
```

A preparação `session.py inputs --new-output-dir "$PREPARACAO_NOVA"` requer os ficheiros históricos originais e as bibliotecas efetivamente selecionadas no portátil. A execução requer o PASS do C270, a colocação verificada, a C55 E20 e uma raiz privada exclusiva. As compilações e os raws do ensaio não são necessários para a CI sem modelo. [Entrada da campanha](session.py)

### Repetir a conversa completa no portátil

A partir da checkout limpa de medição, usar uma janela C55 válida que admita 20 GiB, o recibo privado de colocação do GGUF e o `receipt.json` privado do C270 com o respetivo `protocol.json` ao lado. O portátil precisa dos binários, bibliotecas e inputs históricos verificados pelo preparador. A unidade abaixo inicia o servidor em loopback, verifica quem possui a porta 18442, envia as duas mensagens com a resposta real no histórico e encerra o servidor. A data UTC na identidade serve apenas para reservar uma saída nova. A data de template permanece a que consta do protocolo. [Criar a janela de admissão](../nvme_admission/README.md) · [Executar o C270](../nvme_r0_gate/README.md)

```sh
stamp=$(date -u +%Y%m%dT%H%M%SZ)
unit="tesy-c281-nvme-$stamp"
result="$TESY_PRIVATE_RESULTS/$unit"
python3 -B research/qualification-retake/nvme_conversation/session.py run \
  --commit "$(git rev-parse HEAD)" --unit "$unit" \
  --window "$TESY_NVME_C55" --placement "$TESY_PLACEMENT_RECEIPT" \
  --c270 "$TESY_C270_RECEIPT" --new-output-dir "$result"
```

Um resultado `PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY` confirma exclusivamente a conclusão dos dois pedidos, o reuso de histórico e o encerramento medidos. A latência e a taxa de decode estão no recibo e são avaliadas pelos limiares de produto. Os ficheiros privados da sessão permanecem em `$result`, inclusive se o comando devolver um código de falha.
