# Projeções Radeon sobre o primário CPU do GGML

**GO para gate e up no primário CPU denso.** Na posição 189 e camada CPU0, a Radeon 890M leu as janelas dos slots físicos e reproduziu os 8 640 F32 do subgrafo de referência medido na CPU. O custo de uma política que faça isto durante o pedido continua DESCONHECIDO. [Protocolo](protocol.md) · [Recibo integral sanitizado](evidence/receipt.json)

| Expert | Slot e geração | Matriz | Offset da página desde o início do buffer (B) | Offset do descritor dentro da página (B) | F32 diferentes |
|---|---|---|---:|---:|---:|
| 28 | 3, geração 6 | gate | 13 217 728 | 1 472 | 0/2 880 |
| 28 | 3, geração 6 | up | 365 727 680 | 3 520 | 0/2 880 |
| 24 | 14, geração 6 | gate | 61 685 696 | 3 904 | 0/2 880 |

**MEDIDO.** As bibliotecas CPU/base C269 reservaram três tensores MXFP4 contíguos com forma 2880×2880×40 e 176 256 000 B por papel, num único buffer CPU de 528 768 000 B. Seis leituras de 4 406 400 B alimentaram seis chamadas reais a `ggml_backend_tensor_set`, incluindo os pesos down. A fixture autenticou as seis matrizes pelo endereço de destino. O import de cada projeção abrangeu 4 411 392 B alinhados a 4 096, sempre dentro do buffer proprietário e da mesma VMA anónima privada gravável. O descritor expôs apenas os 4 406 400 B do papel e slot escolhido, com ID local 0. Os três fences precederam o fecho das respetivas vistas e as novas verificações SHA. O mesmo kernel aplicado à gate de e24 distinguiu o segundo expert e reproduziu integralmente a sua linha independente de CPU.

O primário e o staging consumiram parte dos 38 649 856 B de pico do scope inteiro (128 MiB, swap zero). A submissão fez um despacho de RHS e três produtos ordenados. O programa não copiou payload de pesos para uma alocação Vulkan dedicada. Os 26 438 400 B são bytes pedidos e entregues ao primário; o ensaio não tem contador físico de NVMe ou de tráfego da iGPU. O envelope do supervisor foi 114,206454 ms, incluindo arranque e encerramento. O scope terminou inativo. Não houve forward do modelo nem implementação de escalonamento concorrente.

**Âmbito.** A utilização desta geometria na implementação C281/R0 decorre do source do manager. Este processo independente construiu a alocação através das DSOs pinadas. As identidades e gerações são as do corte de referência. Uma política de produção terá de manter a lease até ao último leitor da geração, demonstrar a redução e confrontar o tempo de uma execução 3+1 toda CPU com 3 CPU + 1 Radeon. O resultado anterior do memfd partilhado permanece NO_GO. O próximo discriminante de exatidão é aplicar down ao RHS decorrente de SwiGLU na própria Radeon e conferir a contribuição ponderada. [Importação do memfd](../rank_radv/README.md)

**Reprodução.** Protocolo `b13b1739`, implementação `a2d57f7e4e353835ee0dfa0c38dfb05da8bd50a4`, C269 `d0ebfbcc6c8f456bc1083027c1b08075a32824d8`. A passagem independente de CPU forneceu o recibo `3ef107129e6d4c7afb755ac5836c9099b37a37f3eb3ab87f25fed3e9ba28dd53`. O build R01 `ef67fa3aee5f5f0ca8cd279e9eb3823cc270501e1a341922324a64c13c2af89e` herdou os módulos SPIR-V autenticados. O SHA-256 do recibo físico R01 é `66d7f6f83252ffa0290ac1c712a5a2fc09bd9c27a08ed81796a4963a79fd6449`.

A partir de uma checkout limpa da implementação, com o diretório atual nesta unidade e destinos exclusivos:

```sh
python3 -IB test_run.py
python3 -IB build.py --backend "$C269" --headers "$VULKAN_INCLUDE" \
  --previous-dir "$RANK_RADV_BUILD_R01" --new-output-dir "$NEW_BUILD"
python3 -IB run.py --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_RECEIPT_SHA256" \
  --cpu-dir "$RANK_CPU_R01" --cpu-sha256 "$CPU_RECEIPT_SHA256" \
  --reference-dir "$DECODE_REFERENCE_R01" --pack "$C290_FULL_PACK" --new-output-dir "$NEW_RUN"
```

Os testes sem modelo detetam troca de slot, tipo de memória incompatível, leitura no offset errado, libertação da lease com a seleção errada e violação do limite de memória.
