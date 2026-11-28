# A escolha das propostas muda o preço?

**TRACE_DERIVED · NO_GO para passar diretamente à campanha com o filtro estudado.** A regra só verifica um par proposto quando existem pelo menos duas ocorrências anteriores do bigrama e todos os sucessores já conhecidos coincidem com a proposta. Usou exclusivamente o prompt e os IDs já confirmados. Escolheu cinco dos 46 blocos. Quatro terminaram com dois IDs aceites e um com zero. Prevendo preços iguais aos observados nos seis servidores, pouparia 77–120 ms até à amostra que produziu o primeiro conteúdo final e acrescentaria 89–160 ms até ao fim do decode. Os dois sinais eram necessários. [Protocolo](protocol.md) · [Recibo por corte, profundidade e controlo](result.json)

| Processo ON / controlo | Ganho do filtro até à amostra 85, ms | Ganho do filtro até ao fim, ms | Teto com escolha perfeita ao primeiro final, ms | Teto com escolha perfeita até ao fim, ms |
|---|---:|---:|---:|---:|
| 3ON / 1W | 98 | −131 | 1 158 | 1 689 |
| 3ON / 2OFF | 120 | −134 | 1 136 | 1 719 |
| 4ON / 5OFF | 77 | −160 | 1 030 | 1 577 |
| 4ON / 6W | 95 | −89 | 990 | 1 623 |

Em cada contraste, 16 dos 46 blocos foram mais rápidos que a sequência serial correspondente. Somados por profundidade, os 17 blocos de aceitação integral pouparam **1,544–1,655 s**. Os seis que só aceitaram um ID perderam 1,034–1,076 s e as 23 rejeições perderam 7,057–7,402 s. Portanto, há oportunidades locais observáveis com o executor existente. O teto com futuro perfeito escolhe separadamente cada intervalo positivo em cada par e corte. Uma política executável tem de decidir antes de ver o futuro e pagar seleção, estado das caches e trabalho deslocado. A mistura de intervalos é condicional à invariância desses preços. Apenas a família com os seis servidores mediu o efeito real sobre o cliente. [Medição física](../README.md)

Esta regra é um teste de engenharia. O SuffixDecoding já usa frequências de continuações e confiança. A comparação de latência da figura 4 usa Llama-3.1-8B-Instruct, batch 1, numa H100, e mede tempo por token contra decode serial. O caso ponta a ponta usa vLLM em quatro H100, com oito tarefas concorrentes na figura 6. O teste Tesy usa uma única conversa com o 120B repartido entre NVMe, RAM e GPU discreta. Os preços vêm das 46 oportunidades reais desse pedido. Consulta em 27 de novembro de 2026. [SuffixDecoding, NeurIPS 2025, secções 4.1–4.3](https://proceedings.neurips.cc/paper_files/paper/2025/file/b7aea253ab34a773967f1e4cdea9e4fb-Paper-Conference.pdf)

A escolha foi especificada depois de conhecer a aceitação agregada e o primeiro trio da família, antes de consultar preços por profundidade. O protocolo e o cálculo ficaram no commit `6eebdf37`. A primeira execução terminou antes de abrir os intervalos porque o programa procurou o manifesto um diretório acima da sua localização. O commit `a26b7b6c` corrigiu o caminho. A decisão usa o manifesto original e os critérios congelados. O resultado reproduziu-se a partir da cópia selada. [Comandos e identidades](../commands.json) · [Arquivo das tentativas](../archive.json)
