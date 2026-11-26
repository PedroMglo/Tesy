# A MMID CPU_Mapped usou a nova geração no mesmo grafo

**A paridade numérica foi reproduzida, incluindo a restauração e o controlo negativo.** O scheduler C269 consumiu as três vistas MXFP4 no endereço original dos pesos CPU durante a execução do grafo misto. Ao substituir e depois restaurar as páginas do slot 39, mantendo a mesma alocação do grafo, as saídas acompanharam o conteúdo da geração publicada. Duas auditorias dos ficheiros físicos R02 chegaram ao mesmo resultado. A família original conserva o seu FAIL de pós-voo. [Protocolo](protocol.md) · [Auditoria numérica e de recursos](evidence/audit.json) · [Recibo físico R02](evidence/r02.json)

| Estado na mesma VA CPU | Geração esperada | Páginas apresentadas | MMID CPU e saída CUDA |
|---|---|---|---|
| Original | A | A | Iguais aos vetores densos A |
| Substituição | B | B | Iguais aos vetores densos B |
| Restauração | A | A | Iguais aos vetores densos A |
| Controlo de vínculo errado | A | B | Iguais aos vetores densos B, com 8 610 diferenças em relação a A antes e depois da máscara |

Cada endpoint abrangeu 103 680 floats completos antes da máscara e outros 103 680 depois. Os dois controlos densos confirmaram a fórmula escalar independente para as três posições e os quatro ranks. O resultado denso A reproduziu também o SHA publicado no estudo misto anterior. As diferenças do controlo negativo ficaram exclusivamente no slot 39, posição zero e rank zero. Houve 2 870 diferenças em cada uma das três projeções gate/down/up. Os outros slots e os valores de parking conservaram a paridade bit a bit. [Grafo de referência](../../../../../../../packed_cpu_mixed/README.md) · [Comparações por fase](review.py)

O grafo conservou sete splits. As 18 observações das MMID nos seis endpoints testemunharam a ligação ao tensor de pesos, ao buffer e ao endereço autorizados. Os quatro endpoints do candidato usaram o mesmo owner CPU_Mapped, as mesmas três vistas, a mesma VA e stride de 13 221 888 B. Os dois offsets do memfd estavam selados contra escrita. A sincronização completa do scheduler precedeu cada substituição. Nas três transições o teste rejeitou o bilhete de geração antigo antes do mmap. A alteração observável dos valores após o remapeamento exclui uma cópia permanente e desatualizada dos pesos no operando. O custo de temporários internos aos kernels, de pagetables e TLB, e a sincronização com os quatro workers exigem provas próprias.

## O que falhou nas duas execuções

R01 obteve saídas corretas para A e para os controlos densos e terminou com SIGSEGV ao reutilizar o grafo. A fixture não repunha os scores, a máscara e as ativações que o alocador pode sobrescrever depois do último consumidor. No core o índice calculado para uma matriz com 40 slots era 86. R02 reapresentou os cinco inputs e verificou os seus bits antes de cada compute. Na primeira repetição, 380 dos 384 scores, os 12 valores da máscara e 34 280 das 34 560 ativações de down tinham mudado. O core comprimido de R01 ocupou 140,1 MiB fora da saída Tesy. R02 limitou os core dumps dos filhos a zero. [Falha original](evidence/r01.json) · [Derivação do índice](evidence/r01-diagnosis.json) · [Correção pré-registada](input-lifetime.md)

Em R02 o processo nativo acabou com código zero. Os seis endpoints, quatro fotografias de providers e a série do monitor estavam completos quando uma consulta geral, já no supervisor Python, tentou ler um campo de proprietários GPU que essa consulta não emite. O monitor dedicado já tinha gravado o proprietário nas fases ativas e zero proprietários depois de terminar o filho. O verificador independente confirmou esta série, as 61 observações C118 em 60,149 s, o C55 válido à entrada e o SHA das imagens. A memória GPU observada evoluiu de 2 para 104, 106 e 2 MiB. O pico acumulado do cgroup na amostra depois da saída do filho foi 291 471 360 B, sob o teto de 2 GiB, com swap desativado. Até essa amostra o máximo de temperatura observado foi 48,375 °C na CPU, 41,2 °C na GPU e 34,85 °C no NVMe. Falta o valor do pico posterior até à extinção do scope. A correção do supervisor usa o monitor efetivamente disponível e tem contraprova de proprietário residual. [Critérios de pós-voo](postflight.md) · [Verificador](audit.py)

O próximo gate é entregar estes mapeamentos pelo próprio manager C291 e confirmar o último leitor de cada geração com filas e preloads reais. O custo de retenção CUDA e os objetivos da conversa M3/M4 continuam em aberto. Nenhum ensaio usou pesos do modelo.

## Reprodução

R01 usou o commit `58a379ab`. R02 usou `59a44f43`. Depois do freeze do verificador em `2a5ff5bb`, duas execuções offline produziram o SHA-256 `c34b4c3b1eadc918b3f014d765db1808816808da185b1110b62725a2753ba52f`. Uma terceira execução, lendo os mesmos ficheiros da parte 67 do arquivo privado, reproduziu o recibo byte a byte. O manifesto da parte 67 tem SHA-256 `ed651628165b6e08dcf8fae8740b357e41b10029735db55139344666d6fa2852` e sela 32 ficheiros que totalizam 5 353 977 B. A parte 65 conserva a falha R01. O recibo identifica o compilador, os ficheiros gerados e o binário. Numa checkout limpa, com destinos exclusivos, usar as variáveis abaixo para apontar ao raw R02, ao mapa R02 de providers, à política C55 e ao recibo anterior de transição CUDA.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias/mixed
python3 -IB "$unit/test_mixed.py" -q
python3 -IB "$unit/audit.py" --family "$PHYSICAL_R02" --map "$STATIC_MAP" \
  --c55 "$C55_RECEIPT" --prior "$PRIOR_CUDA_RECEIPT" --new-output-dir "$NEW_OFFLINE"
```

O comando físico chama o supervisor da checkout de medição, com inventário próprio e o caminho privado de NVML autenticado pelo C55. O alias do driver do filho é criado exclusivamente no diretório novo da fixture. O estudo não mudou o launcher.

```sh
systemd-run --user --scope --quiet --unit "$SCOPE" \
  -p MemoryMax=2G -p MemoryHigh=2G -p MemorySwapMax=0 -p RuntimeMaxSec=250 \
  env LD_LIBRARY_PATH="$NVML_ONLY" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /usr/bin/python3 -IB "$unit/run.py" --commit "$COMMIT" --unit "$SCOPE" \
  --backend "$C269_REPO" --map "$STATIC_MAP" --c55 "$C55_RECEIPT" \
  --c55-sha256 "$C55_SHA256" --prior "$PRIOR_CUDA_RECEIPT" --new-output-dir "$NEW_RAW"
```
