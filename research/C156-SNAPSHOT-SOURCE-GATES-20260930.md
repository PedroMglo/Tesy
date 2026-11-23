# C156 — gates finais de instrumentação, sem modelo

Objetivo: concluir os gates C152 sob a ordem post-C154. Evidência: REPRODUZIDO_MODEL_FREE e SOURCE_AUDITED; não é qualificação numérica ou desempenho.

O gerador reproduz os quatro ficheiros do backend isolado byte a byte. O journal inclui identidades de work/generation, request ranges e commits. Ficheiros concluídos são publicados atomicamente sem substituição; write/cancel/overflow conserva partial sem PASS. Routing continua limitado a 8 MiB; não existia o suposto desfasamento de limite.

Passaram 20 testes snapshot/journal, 15 de trace/análise, 22 de policy/entrypoint e quatro de ordem/envelope do wrapper. As chamadas externas foram substituídas apenas nos testes de ordenação; os testes maduros exercitam o gate e Popen real/dummy. Não foi executada a suite integral. Fixtures nativas finais v5 vêm do source real.

O lock produz corte lógico de manager/layers/queues/owned work. A fase atómica de retorno do worker é advisory e não um timestamp global de readiness. Não foi adicionada espera para drenar workers.

Falhas de compilação/teste preliminares permanecem nos logs; corrigidas antes do modelo. Dois inventários live ainda não admitem E20 com a reserva congelada; nenhum forward executado. A próxima unidade só começa com admissão live válida e protocolo commitado: dummy → bridge contra C140 → OFF/ON.

Outputs: results/c156-snapshot-gates-20260930T1000Z/{generation-proof,build-identity,decision}.json. C140/C142 e históricos não são reclassificados.
