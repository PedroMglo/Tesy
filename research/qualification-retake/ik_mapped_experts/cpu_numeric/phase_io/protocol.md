# Contadores de leitura nas fases do C110 CPU

Reanálise secundária dos dois braços encerrados. Autenticar os recibos D0
8343243f506088714e3c16e83d834e82c85faa30878010a8837815f678c90c37 e D1
a55554e02a4312ea81e49c9cdf31ff22e3fa115439d11692f9caf0c5b042b9ee com o
revisor de custo. Recalcular em nanossegundos inteiros cada janela de fase
relativa à primeira marca nativa. O início desta marca pode cair em qualquer
ponto desde zero até à duração do supervisor menos a distância nativa entre
a primeira e a última marca. Não fixar o instante de spawn.

O supervisor recolheu amostras sequenciais com os contadores primeiro e só
depois o carimbo relativo. A leitura de cada contador pode ocorrer entre o
carimbo da amostra anterior (zero para a primeira) e o seu carimbo. O delta
antes do spawn até depois do filho é conhecido, mas os valores absolutos
nesses dois extremos não foram guardados. Usar monotonia, esse delta e os
valores efetivamente observados para limitar o trabalho estritamente dentro
de cada fase e o que pode caber nela, respeitando um único deslocamento por
fase. Não atribuir a uma fase todo um incremento que atravesse o seu limite.

Separar bytes de leitura do cgroup no 259:0, no 8:0 quando reportado, e dos
setores do namespace NVMe × 512. Uma amostra sem dispositivo tem valor
desconhecido. Para a ausência do dispositivo em todo o braço verificar
a semântica do delta no produtor. Não somar esses três denominadores, ou
limites superiores marginais de fases diferentes. Publicar limites D0/D1 e
da sua diferença para cada forward. O sinal só é identificado se o intervalo
for estritamente de um lado de zero. A ordem de execução, a cache e os
trabalhos desencadeados antes ou consumidos depois impedem atribuição causal.
Testar atraso de coleta, origens diferentes, contas monotónicas com oráculo
de pequenas agendas e regressões. Sem modelo ou acesso ao estado vivo.
