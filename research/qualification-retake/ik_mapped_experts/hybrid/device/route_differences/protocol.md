# Localizar diferenças de rotas e do token guloso na pequena fixture ik

Auditoria secundária. Antes desta análise já eram conhecidas diferenças
agregadas CPU/GPU no braço residente. Aguardar o SHA exterior do recibo
terminal da família R02 para abrir os dados. Vincular o CPU independente ao
recibo 95e0697e0c9d65c16a921fff06af57ddd2b43e22d4c3be39f256afe023dd5508
e o GPU ao manifesto integral de ficheiros ou aos hashes do braço completo.
Manter a falha de família caso exista.

Comparar CPU→RESIDENT e RESIDENT→BANK9, RESIDENT→BANK7 nas fronteiras que
tenham bytes produzidos, íntegros e F32 finitos. São 32 linhas de prefill,
posições 0–31, e 1 teacher fornecido na posição 32; 32 logits por posição,
duas camadas com top-4 entre oito experts. Reabrir os vetores de ROUTE no
stdout, com a ordem token-major, nomes e consumo de bias verificados no
revisor canónico para cada braço completo. Se o log incompleto incluir
apenas algumas ROUTE, validar separadamente identidade, cardinalidade,
uniqueness e offsets desse bloco; recusar linhas truncadas/duplicadas ou
fora de domínio. Publicar a interseção identificável, a cobertura em falta
e o estatuto DIAGNÓSTICO. Uma comparação parcial não qualifica o mecanismo.

Por (posição, camada), classificar o quarteto como igualdade ordenada,
permutação do mesmo conjunto ou substituição de um ou mais membros.
Reconciliar os 66 sítios possíveis, publicar os índices por tipo e a
distribuição da interseção de conjuntos. Para cada posição com logits
admitidos, comparar palavras binárias e máximos. Há identificação gulosa
só se o máximo for único em ambos; em qualquer empate publicar o conjunto
dos máximos sem atribuir coincidência nem divergência de ID único.
Nas divergências e empates publicar IDs do top-1/top-2, valores e margens
(top-1 menos segunda maior pontuação incluindo multiplicidade) nas duas
vias; indicar também o teacher. Publicar associação descritiva dos sítios
de rota alterada com igualdade/divergência gulosa, sem inferir o primeiro
operador divergente de logits finais. Reproduzir o diagnóstico das cópias
seladas disponíveis; nenhuma execução de modelo, CUDA ou compilador.
