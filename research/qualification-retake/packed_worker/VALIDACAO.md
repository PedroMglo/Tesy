# Fixture do worker C291 em CPU

Executar numa checkout limpa com o protocolo congelado na mesma pasta. O passo candidato requer também a revisão do `arena.patch` após os gates anteriores. Não se iniciam serviços de inferência, não se lê o GGUF e não se instala software.

## Executar após admissão

O supervisor exige cgroup v2 de utilizador com 1 GiB de memória e swap zero. Executa os filhos em série no mesmo scope dedicado e confirma que o scope contém apenas o supervisor no início e no fim de cada etapa. O runner impõe 180 s por comando e 720 s para a família inteira. Dar um nome novo à unidade systemd e a ambos os diretórios a cada tentativa. O diretório pai dos dados sintéticos deve estar autorizado no volume Btrfs NVMe do projeto. O diretório privado de relatórios pode ficar em `/tmp` e deve ser arquivado antes do fim da sessão.

```sh
RESEARCH=research/qualification-retake/packed_worker
BACKENDS="$TESY_C7/backends"
DATA="$TESY_NVME_DADOS"
UNIT=tesy-packed-worker-original-r01
systemd-run --user --scope --unit="$UNIT" -p MemoryMax=1G -p MemorySwapMax=0 \
  python3 -I -B "$RESEARCH/run.py" --phase original --scope-unit "$UNIT.scope" \
  --backend "$BACKENDS/c291-expert-store" \
  --base-dso "$BACKENDS/c269-layer-last-use/build-c269-cuda/bin/libggml-base.so.0.15.3" \
  --new-output /tmp/tesy-packed-worker-original-r01 \
  --new-nvme-dir "$DATA/tesy-packed-worker-original-r01"
```

`RESEARCH` deve apontar para a pasta de integração escolhida na checkout limpa. Para a confirmação posterior com o mesmo original, substituir a unidade e os dois destinos por novos, usar `--phase candidate --original-receipt /tmp/tesy-packed-worker-original-r01/receipt.json --original-sha256 DIGEST_CONGELADO` e manter disponíveis os raws do original. O candidato autentica o recibo, relê o raw, refaz a comparação e desconta o tempo ativo do original dos 720 s da família. Os SHA dos dois programas Python e da fixture C++ devem coincidir entre estas fases. Alterá-los exige nova referência. Também se pode usar `--phase full` num único scope novo para executar os 12 braços em ordem.

O runner extrai 34 blobs da tree C291 `3962daa588dfa89971c60c95ce4c5054bc27fd3f`, incluindo os nove ficheiros privados. Refaz o SHA-1 Git com o cabeçalho de blob e regista também SHA-256. O candidato usa uma segunda cópia da mesma origem com aplicação do patch restrita a `src/`. O linker e os endereços das funções expostos pelo processo autenticam os fornecedores C269 de GGML base e OpenSSL. A fixture usa o construtor de teste selado do C291 em todas as unidades de tradução. A referência usa o manager original. DENSE, STAGED e DIRECT no candidato usam o mesmo executável.

## Interpretar os resultados

- O pack contém seis registos sintéticos de 13 258 752 bytes, 79 552 512 bytes no total. Os primeiros 36 experts compartilham um registo de pesos zero no índice da fixture. Os restantes cinco têm dados e digests independentes por componente. Cada filho relê e autentica todo o pack através do próprio descritor O_DIRECT que o worker irá servir. O recibo distingue essa leitura de prova das leituras autoritativas.
- O positivo começa com nove remaps de aquecimento, 36 misses e 475 891 200 bytes lógicos. A fase seguinte reclama quatro experts distintos em simultâneo, incluindo o slot 39, com quatro misses e 52 876 800 bytes lógicos. O remap seguinte tem quatro hits. Por fim, uma substituição do slot 0 entrega 13 219 200 bytes e há três hits. São 41 cargas, 7 hits e 541 987 200 bytes lógicos no total. O registo conserva separadamente os bytes pedidos, apresentados pelo leitor e copiados por SET em cada fase. O transporte de STAGED e DIRECT deve pedir exatamente 13 221 888 bytes por falta. DENSE conserva o arredondamento original à unidade do descritor.
- Cada leitura da fase concorrente fica retida depois da reivindicação e antes do syscall. O próprio `pick_victim_locked` deve recusar os quatro LOADING e encontrar o único candidato autorizado ao libertar o slot 35. A igualdade de bytes e geração das três vistas é verificada em todos os 40 slots, antes e depois da substituição. Essas duas passagens lêem 1 057 536 000 bytes de RAM para diagnóstico. O DIRECT verifica também o padding de cada janela. Há uma barreira artificial, cálculo de hashes e leitura de dados quentes. Os tempos e o RSS do supervisor caracterizam o custo desta fixture.
- Há um positivo DENSE original e onze braços no mesmo executável candidato. Incluem três positivos, três leituras com devolução inferior ao payload, três cancelamentos com leitura reclamada e dois erros de transporte com devolução igual ao payload. Nestes últimos dois, o wrapper realiza o syscall integral e devolve 13 219 200 bytes à API. O resultado deve ser a rejeição da publicação por STAGED e DIRECT. No caso de shutdown, o controlador coloca a flag de cancelamento e esvazia a fila sob o mutex durante a leitura. O destrutor nativo junta os workers ao sair.
- O primeiro erro termina a família e conserva o diretório privado, o pack e os logs disponíveis. Num PASS, removem-se apenas os dois ficheiros sintéticos criados nesta tentativa e o respetivo diretório, depois da guarda de identidade. O manifesto gold, os raws de todos os braços, os logs e o recibo permanecem no diretório de saída. Cada ficheiro de evidência deve ser arquivado com o respetivo digest antes de limpar a saída.
- Um PASS qualifica a entrega e a publicação na camada CPU sintética com geometria C291. A carga do manifesto integral de 36 camadas, CUDA, o consumidor FFN completo e os logits do target precisam dos seus próprios gates. O número de bytes pedidos à API e copiados nas vistas não quantifica o tráfego físico no NVMe nem a latência de uma conversa.
