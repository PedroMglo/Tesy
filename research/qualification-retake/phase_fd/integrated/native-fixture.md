# Fixture de proveniência do trabalho entre dois retornos

Antes da primeira execução, fixar o commit Tesy, as duas TUs C269 e o recibo
de build e5042bfb23527a1763b28ca2098c0a00700383d07ff403a97d52da4bcdf422a6.
Ligar o objeto do manager candidato já compilado a um novo executável com as
bibliotecas C269. O driver pequeno usa as mesmas funções de marcação que a
TU de contexto, extraídas do fonte gerado no build. Entra nas callbacks
originais de remap e de wave através do scheduler CPU GGML. As chamadas
externas e os IDs são sintéticos. Nenhum ficheiro de pesos, execução CUDA,
servidor, comparação de latência ou validação de um contexto 120B.

Usar quatro workers, 36 camadas com 40 slots, três pequenos slabs I8 por
expert e um FD aberto com O_DIRECT. A primeira chamada executa a wave 0
de uma camada, servindo 18 demandas e pré-carregando 18 experts da seguinte.
Uma barreira de teste no pread da última componente de um desses
experts (127) mantém a geração em curso no retorno 1. A chamada 2
pede quatro experts de outra camada enquanto esse worker continua ocupado.
Libertar a leitura só depois do segundo retorno. Conferir todos os destinos
carregados por uma fórmula independente e o número/volume real das leituras
com um observador do syscall no executável. Uma leitura curta exatamente
suficiente publica. Um byte a menos preserva os dois SET anteriores e impede
a publicação dessa geração. A fixture aguarda o estado terminal somente
depois de medir as duas fronteiras.

Braços independentes: OFF e ON com EOF suficiente, OFF e ON com EOF
insuficiente, ON com trigger apenas na chamada 2 e EOF suficiente. Neste
último caso exigir fotografia da geração anterior pendente e READ herdado
sem atribuição à chamada 2, com início desconhecido. Para os braços ON desde
o início exigir fronteiras 32/1, TLS em ambas as callbacks, 4 workers
observados a sair, cabeçalho fechado, conservação de READ/SET e payloads
concordantes com o controlo. Marcar FAIL se faltar qualquer parte. Preservar
saídas parciais e diagnóstico. O perfil controlado desta fixture permite
128 B por slab. Uma qualificação real requer os nomes, offsets e dimensões
do GGUF autêntico e uma chamada efetiva a llama_decode.

Orçamento: 512 MiB de cgroup, zero swap, até 120 s, 64 MiB de saídas,
um processo de cada vez. O ABI/artefacto candidato para produção permanece
inalterado. Sem admissibilidade deste ensaio, conservar NOT_RUN nos forwards.
