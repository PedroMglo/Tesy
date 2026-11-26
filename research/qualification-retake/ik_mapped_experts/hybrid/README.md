# Cache CUDA do ik em 8 GiB

**Configuração medida.** O CMake 4.3.0 identificou NVCC 13.3.73 e completou os probes de ABI com o host GNU 15.3.1 em 1,970 s. GCC 16.2.1 é o default do sistema; o toolkit rejeita GNU posterior a 15. Um namespace com dispositivos privados e rede isolada permitiu verificar a toolchain sem GPU e sem modelos. O Ninja exigiu 401 passos para o menor alvo da API do modelo (`llama`): 272 CUs CUDA, 124 C++, três C e as ligações partilhadas de `ggml` e `llama`. As 272 CUs declaram apenas código nativo SM89 e o mesmo compilador host. Os dois objetos CUDA de identificação são do CMake; zero CUs do projeto foram compiladas nesta etapa. O tempo de uma compilação integral e a compatibilidade de cada CU continuam por medir. [Método e gates seguintes](protocol.md) · [Resultados da configuração](result.json)

A ligação planeada usa cuBLAS, cuBLASLt, cudart e o stub de link de libcuda do toolkit. A execução precisa dos providers do driver 620.70.06 autenticados no portátil e da nova libggml CUDA. O validador de link reabre os providers efetivos, exige a libcuda real e recusa indefinidos. NCCL não está instalado; o teste é para um único dispositivo. O aviso de `FETCHCONTENT_FULLY_DISCONNECTED` identifica uma opção não usada pelo pin; o isolamento de rede é aplicado por `bwrap --unshare-net`. Estes comandos não dependem de ferramentas no PATH do ambiente CUDA. [Verificador de configuração](configure.py) · [Builder limitado](build.py)

Configuração R01 (26 de novembro, UTC). Ficheiros privados em `/mnt/sdisk-ssd-ext/Tesy/repo/build/tesy-ik-cuda-sm89-config-20261126-r01`; `receipt.json` SHA-256 `826ee49eaedc00faf8990aaedfd5d3c4875e308eed6745f16bc48511e2e0e477`. O log CMake iniciou às 00:18:50,110562539 e recebeu a última escrita às 00:18:52,038389588. O dry-run começou às 00:18:52,079538521. O recibo terminou às 00:18:52,148824717. Arquivo completo antes do recibo: 8 369 030 B. Estão preservados o comando exato, CMakeCache, as regras Ninja, os 401 comandos de produção, a identidade dos providers e as hashes dos compiladores. Para reproduzir, escolher novo sufixo no destino.

```sh
w=/tmp/tesy-prefill-uv20p0/qualify
h="$w/research/qualification-retake/ik_mapped_experts/hybrid"
root=/mnt/sdisk-ssd-ext/Tesy/repo/build
python3 -IB "$h/configure.py" --source /tmp/tesy-ik-source-20261125-r01 \
  --env49-map /tmp/tesy-env49-static-r01/static-map.json \
  --new-output-dir "$root/tesy-ik-cuda-sm89-config-20261126-r02"
```

A compilação tem campanha independente e depende de janela autorizada. O builder clona os ficheiros configurados para um único destino novo e expõe essa cópia ao Ninja pelo caminho absoluto esperado num namespace privado. Assim conserva a configuração R01 e a identidade de todos os comandos. O scope concede dois jobs, 6 GiB de RAM, zero swap, até 90 minutos de Ninja; a política interrompe quando o diretório atinge 8 GiB ou o FS desce de 11 GiB livres, amostrado a cada segundo. A idade de um configure não permite atribuir um tempo esperado para as 272 CUs. O scope deixa margem para o fecho da auditoria do loader.

```sh
w=/tmp/tesy-prefill-uv20p0/qualify
h="$w/research/qualification-retake/ik_mapped_experts/hybrid"
root=/mnt/sdisk-ssd-ext/Tesy/repo/build
unit=tesy-ik-hybrid-build-20261126-r01
systemd-run --user --scope --quiet --unit="$unit" \
  -p MemoryHigh=6G -p MemoryMax=6G -p MemorySwapMax=0 -p RuntimeMaxSec=5550 \
  python3 -IB "$h/build.py" \
  --configure-dir "$root/tesy-ik-cuda-sm89-config-20261126-r01" \
  --configure-sha256 826ee49eaedc00faf8990aaedfd5d3c4875e308eed6745f16bc48511e2e0e477 \
  --env49-map /tmp/tesy-env49-static-r01/static-map.json --unit "$unit.scope" \
  --new-output-dir "$root/tesy-ik-cuda-sm89-build-20261126-r01"
```

O primeiro teste físico mede a cópia antecipada das seis matrizes no controlo residente e a sua ausência na variante de cache, seguida de H2D por IDs confirmados com o mesmo resultado numérico. Um controlo de sete slots discrimina o fallback a 32 tokens e a retoma a um token. O campo de bytes de upload lógico do cache só conta fills do hook. A extensão ao modelo 120B precisa ainda do pico real de VRAM com atenção/KV/contexto e da pressão do mmap no orçamento do portátil. [Proveniência anterior da fixture](../tiny_loader/README.md)
