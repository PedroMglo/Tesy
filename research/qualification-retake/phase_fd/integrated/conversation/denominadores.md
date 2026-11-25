# Denominadores condicionais do prefill nominal

Adenda prospetiva ao protocolo da conversa, antes do primeiro braço C281 PFJ1. A mesma execução publica obrigatoriamente duas linhas, com os mesmos relógios observados de primeiro conteúdo final, prefill e decode. Seja S = 10 s − primeiro final + prefill + decode.

- A métrica de produto C281 conta N=47 tokens em predicted_ms. O orçamento condicional do prefill é S − 47/6 s. Esta é a linha M4.
- A relaxação de serviço AR concede que o primeiro dos 47 tokens já foi produzido pelo prefill. Conta as 46 avaliações seguintes ao preço de 1/6 s cada. O orçamento condicional é S − 46/6 s. Esta linha mede a sensibilidade à definição de serviço.

O segundo orçamento excede o primeiro em exatamente 1/6 s antes de arredondar. Registar ambos mesmo se um cenário de 4,5 GB/s atravessar o limiar e o outro não. Na referência nominal R0 independente obtêm-se, respetivamente, 2,424377302 s e 2,591043969 s arredondados para cima ao ns. Os 750 000 000 B adicionais vêm da hipótese, sem mudança do trabalho físico. [Conservação por chamada](../conservation.md) · [Relógios de R0](../../../nvme_conversation/phase_reads/README.md)
