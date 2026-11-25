# O limite de espaço virtual impediu o arranque da fixture CPU

**FAIL_PRESERVED no primeiro braço stock.** O carregador dinâmico terminou com código 127 antes de entrar em `main`. O erro identificou a biblioteca e a operação: `libcublasLt.so.13: failed to map segment from shared object`. O stdout ficou vazio. O controlador esperava observar a identidade da libllama e registou `loader ELF identity stock`. Os braços candidato OFF, ON e inválido ficaram NOT_RUN. O processo não abriu o GGUF através do loader em ensaio e não executou nenhum forward. O efeito do prefault nos logits, nos mappings do GGUF e no arranque do 120B continua desconhecido. [Protocolo](protocol.md) · [Recibo preservado](tiny-r1/receipt.json)

O controlador criou um GGUF Llama sintético de 50 816 B, SHA-256 `31a310d53e5c4c2a22994fc2fa75f095446af380885948120306fd6e7213a08d`, e compilou o cliente. A execução total levou 0,41 s e teve RSS máxima de 86 336 KiB. Este máximo inclui a preparação. Cada braço tinha `RLIMIT_AS=805306368` B (768 MiB). O primeiro devolveu o erro antes de produzir os 64 logits previstos. O recibo de 1195 B tem SHA-256 `a2db2c7507d40cf99c6cb88a8b07fdae2d9d7bcf59777d6592dd1d1257be98a6`. A checkout de medição foi `365006e3e7fe29606c10062fba872398988f1784`, árvore `3dfefd8a11ced49e76cf0bf2e6a23236b4183117`. [Cliente da fixture](tiny_fixture.py)

## Limite formal devido aos segmentos ELF

A leitura dos cabeçalhos ELF do executável stock e dos seus DSOs nesta estação identificou a cadeia `probe → libggml.so.0 → libggml-cuda.so.0`. O último declara em `DT_NEEDED` as duas bibliotecas cuBLAS e `libcuda.so.1`, independentemente do número de camadas que o cliente viria a colocar na GPU. Os quatro ficheiros abaixo bastam para exceder 768 MiB de espaço virtual. Para cada objeto, o cálculo arredonda o início de cada segmento `PT_LOAD` para baixo e o fim `p_vaddr+p_memsz` para cima, segundo a página local de 4096 B. Soma a união dos intervalos de páginas desse objeto e, depois, as uniões dos quatro DSOs distintos.

| DSO resolvido | Páginas PT_LOAD em bytes |
|---|---:|
| libcublasLt.so.13.6.0.2 | 619 364 352 |
| libcublas.so.13.6.0.2 | 55 504 896 |
| libggml-cuda.so.0.29.0 | 41 525 248 |
| libcuda.so.620.70.06 | 101 470 208 |
| **Total parcial obrigatório** | **817 864 704** |

São **779,977 MiB**, 12 558 336 B acima de `RLIMIT_AS`, antes de incluir o executável, libllama, as restantes bibliotecas, stack, heap ou qualquer página do modelo. A biblioteca a que a mensagem se refere ocupa sozinha 590,672 MiB de páginas de segmentos e o seu intervalo entre extremos mede 596,664 MiB. O seu build ID é `fd85f2d003d17b73bc3572e420da662fff202d7f`. O conjunto mínimo excede o limite mesmo omitindo os espaços entre os segmentos. A residência física dessas páginas e o seu consumo no cgroup só poderiam ser medidos num processo que passasse esta etapa.

A inspeção ELF é reprodutível sem abrir o GGUF nem executar o cliente. Usar `readelf -W -d` no cliente e nas bibliotecas da cadeia para obter os SONAME necessários, `ldconfig -p` para resolver os fornecedores do sistema, `getconf PAGESIZE` e `readelf -W -l` nos quatro ficheiros para obter os intervalos. O GPU não foi usado para computação.

**Condição de reabertura.** Uma nova identidade pode distinguir memória virtual de memória residente. Antes de qualquer execução, teria de congelar um orçamento de VA que comporte a cadeia ELF completa e documentar separadamente o limite de memória cobrada pelo cgroup, swap, backend CPU e durações. A observação mínima seria o arranque do carregador da mesma ABI e a identificação de cada DSO mapeado. A prova de prefault continuaria a exigir as observações de mmap/WILLNEED e os mesmos logits na fixture. Esta tentativa termina no bloqueio demonstrado.
