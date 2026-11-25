# O RADV recusou o backing memfd do slot C291

**NO_GO para a importação deste memfd MAP_SHARED por VK_EXT_external_memory_host na Radeon 890M da estação.** A consulta de compatibilidade de ponteiro passou. Na operação seguinte, vkAllocateMemory devolveu VK_ERROR_INVALID_EXTERNAL_HANDLE. O primeiro produto gate, o segundo produto up e as provas de última utilização e de troca de geração ficaram **NOT_RUN**. Mantém-se a igualdade já medida com o shader ordenado e o primário anónimo da fixture anterior. [Recibo físico](evidence/receipt.json) · [Protocolo](protocol.md) · [Projeção ordenada anterior](../ordered_dot/README.md)

| Fase da R01 | Evidência |
|---|---|
| Entrada posição 189 e quantização Q8_1 | Um dispatch. Todos os 3 312 bytes produzidos voltaram a coincidir com a referência física. |
| Carga de e28 | Um pread de 13 221 888 B do pack existente diretamente para o mmap do memfd. Os três SHA da gate, down e up passaram. A campanha não mediu tráfego físico do NVMe. |
| Vistas do slot 3 | O código identificou na tabela de VMAs uma vista rw-s para importação e a vista r--s de CPU a 39 665 664 B da base, ambas com o mesmo inode, offset 0 e tamanho real do backing. |
| Tamanho, alinhamento e tipo | A memória pedida pelo buffer coube na janela. Ponteiro, tamanho, alinhamento de up e a existência de um tipo HOST_VISIBLE e HOST_COHERENT passaram antes da alocação. O journal só escreveria os valores numéricos depois de uma alocação bem-sucedida. |
| Alocação Vulkan | O driver recusou o ponteiro para a janela. Quatro pequenos buffers anónimos tinham sido importados no mesmo processo. |
| Segunda janela de e24 e permuta 3/6 → 3/7 | NOT_RUN. Os golds CPU dos ranks 0 e 1 já estão disponíveis. |

A especificação admite que uma implementação rejeite um ponteiro particular durante a importação. Nesta estação, Mesa Vulkan 26.2.7 importa o símbolo amdgpu_create_bo_from_user_mem. No libdrm_amdgpu 2.4.134 instalado (SHA a28f07a5f69cd85d5a55b18f436cff5e0e33087181bdc3b8061ac2dec99d1322), esse símbolo passa flags 0x0e ao ioctl GEM_USERPTR. O cabeçalho do kernel 7.3.4 define esses bits como ANONONLY, VALIDATE e REGISTER. Isso fornece uma explicação de fonte coerente com o contraste observado. O journal não observou o ioctl nem o seu errno interno. [Contrato Vulkan do ponteiro](https://docs.vulkan.org/refpages/latest/refpages/source/VkImportMemoryHostPointerInfoEXT.html) · [Implementação publicada de libdrm](https://android.googlesource.com/platform/external/libdrm/+/refs/tags/android-14.0.0_r29/amdgpu/amdgpu_bo.c) · [Ponto exato do gate](backing.inc)

## Alternativa que muda a premissa

**O caminho operacional R0 já reserva outro tipo de armazenamento.** No pin C269, llama-model.cpp:1244–1255,1767–1772 seleciona o tipo de buffer default com suporte a MUL_MAT_ID. llama-moe-stream.cpp:165–199,229–240 cria cada tensor contíguo por papel e usa ggml_backend_alloc_ctx_tensors_from_buft. No caso CPU comum, ggml-backend.cpp:2239,2305–2319 usa memcpy no SET e um buffer de ggml_aligned_malloc. O ramo POSIX de ggml.c:332–366 pede alinhamento de 64 B. Uma matriz de cada papel ocupa 4 406 400 B em cada um de 40 slots, num tensor de 176 256 000 B. Os recibos disponíveis não identificam a VMA de cada ponteiro desses tensores para um processo C281 real. O braço pack P do servidor conserva este primário e os SET. A troca por memfd foi uma fixture de banco posterior. [Controlo R/O/P](../../../packed_nvme_manifest/server_profile/conversation/protocol.md) · [Buffers GGML CPU reais na fixture de serviço](../../../phase_fd/integrated/t1_native_sink/README.md)

O menor ensaio consiste em alocar gate e up pelo próprio GGML CPU pinado, registar VMA, endereço e limites do buffer proprietário e escolher um intervalo anónimo completamente interno que cubra o slot. Os limites para o import arredondam à página de 4 096 B, enquanto o descritor deve poder endereçar o início real do papel com o alinhamento de storage reportado pelo dispositivo. Por exemplo, o stride da matriz deixa 3 200 B de resto por página. É preciso conservar dono, slot e geração, usar o mesmo ponteiro no acesso CPU/GPU, comparar os 2 880 F32 de cada papel e impedir substituição antes do fence. Um sucesso nessa fronteira deixaria intacto o percurso de armazenamento do R0 e cobraria os SET que já faz.

Outra intervenção seria carregar um registo do pack diretamente num backing anónimo permanente alinhado por slot, com vistas por papel e leases. Isto altera o destino dos workers, o stride e a resposta a cancelamentos. Um hit num banco que conserve memfds exigiria copiar 13 219 200 B de pesos úteis para o slot ou contabilizar a cópia alinhada da janela de 13 221 888 B. Guardar uma vítima anónima que não tenha outro dono pode exigir a cópia inversa. Para eliminar ambas seria necessário gerir também a residência e a permuta do próprio backing anónimo; esse mecanismo perderia a troca de mapeamento por FD já qualificada na CPU. A receita original C291 lê 13 258 752 B para também servir biases. Nenhum destes custos recebeu preço de parede nesta campanha.

## Reprodução

Freeze limpo d55f2ab124669051f526ac59f1e70e476774cc7e. Recibo de build R01 e68f5df23021e1e732d5dc17e68be33f973edeefb6170f56df9e1d183cfe3c48. Recibo da admissão 82e36524cf11a9c97d0a6684753476fe4f96e6b753bd3105f767062f429d4180. Journal SHA 732bda52d45e06aec637a49e54d3d7284bb92f83a6f435238c1058d471954a08. Uma identidade de build e ensaio, tempo de parede do invólucro 114,6 ms, cap 128 MiB e swap zero. O supervisor confirmou a saída do filho e o scope inativo. Como o processo parou antes do último checkpoint, o pico final de RSS fica desconhecido. Model forwards 0. Os caminhos de saída têm de ser novos.

```sh
d=research/qualification-retake/igpu_resident_rank/projection/rank_radv
python3 -IB "$d/test_run.py"
python3 -IB "$d/build.py" --stock-dir "$STOCK_BUILD" --ordered-dir "$ORDERED_BUILD" \
  --headers "$KHRONOS_INCLUDE" --new-output-dir "$NEW_BUILD"
python3 -IB "$d/run.py" --build-dir "$NEW_BUILD" --build-sha256 "$BUILD_SHA" \
  --cpu-dir "$RANK_CPU" --cpu-sha256 "$CPU_SHA" --reference-dir "$PART74" \
  --pack "$C290_PACK" --new-output-dir "$NEW_RUN"
```
