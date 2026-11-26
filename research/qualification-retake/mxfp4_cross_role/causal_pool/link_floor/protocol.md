# Piso da ligação para 254 leituras CPU sem medição local de tempo

Pré-registo antes do cálculo. Fixar a única trajetória U1262 reconstruída na
composição e os mesmos preços e identidades em R02/R03, SHA-256
`08c4f7fe5c8487202be6a24bb0b47e21a0f3bad155fd6dfc225f5b552ff389d3`.
Conceder a cada job, incluindo os experts não amostrados, o melhor registo
C287 com 11 259 904 B alinhados. Conservar 1 048 jobs de disco no prefill,
918 no decode, as cadeias READ+SET conhecidas, 47 tokens e o exterior. Cabe
ao worker devolver o bloco inteiro dentro da callback que dele necessita.
Conceder os custos zero de codec, remap, tag, despacho e serviço do SSD.
Analisar como caso mais favorável G=0. Os dois G positivos do protocolo
anterior só aumentam o custo. [Composição original](../protocol.md)

O recibo do pack usado nos braços de serviço tem de autenticar a colocação
no NVMe interno, a mesma identidade do ficheiro e filesystem nas duas ordens.
Registar separadamente a observação sysfs sobre o controlador Micron e a
ponte. A placa do portátil expõe 16 GT/s ×4 de link atual e máximo.
Dar uma capacidade **superior** de 8 000 000 000 B/s num sentido, ignorando
até o custo da codificação 128b/130b e os pacotes. O valor não é o maior
débito medido no SSD. [PCI-SIG](https://pcisig.com/faq?field_category_value%5B%5D=pci_express_4.0)

Para cada callback i, K_i é a maior cadeia já paga ao preço do melhor
registo, em ns (zero quando todas as leituras são desconhecidas), e U_i é a
soma dos payloads de disco de jobs **sem** tempo conhecido. Exigir o custo
de pelo menos max(K_i, U_i/B). O custo novo é apenas a parcela acima de K_i;
admitir que cada byte de U_i possa sobrepor-se às leituras ou SET conhecidos
mesmo usando o mesmo link, uma relaxação favorável. Grupos de até quatro
jobs simultâneos, mas os quatro workers partilham o link. Contar também o
piso só nos grupos sem cadeia conhecida. Verificar por frações exatas que
U=0 reconstrói as quatro margens anteriores antes da aplicação do piso.

Para cada ordem publicar os 254 jobs, o número de callbacks e os bytes que
têm de transitar, tempo adicional, custo de decode, margem conjunta e a de
6 tok/s. Por bisseção em B/s inteiros obter a banda agregada mínima que
permite as duas condições, ou impossibilidade com B infinito. Dar também a
fração máxima destes bytes que poderia atravessar a 8 GB/s ainda com folga,
concedendo escolher livremente que leituras ou partes são servidas de outro
tier: dentro de cada K_i podem caber min(U_i,B×K_i) bytes, e a soma das sobras
partilha o menor entre o orçamento de decode e o conjunto. Este teto pode
fracionar um registo que o runtime teria de entregar inteiro. Se nem o link
superior permitir a melhor ordem, fechar a suficiência **para payloads
inteiros distintos que passam pelo link depois da decisão causal**. Cache de
páginas/host, deduplicação de pedidos, dados em ficheiros esparsos, compressão
no filesystem ou prefetch anterior mudam U_i ou os intervalos. Os contadores
de um pack raw anterior não medem os bytes de um codec ainda hipotético.

Dois processos em diretórios exclusivos, 512 MiB e 120 s por processo,
apenas metadados e traces arquivados. Preservar falhas. Nenhuma nova
leitura de pesos, campanha no SSD ou execução do modelo.
