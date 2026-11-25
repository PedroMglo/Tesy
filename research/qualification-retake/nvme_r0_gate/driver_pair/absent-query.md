# Busca opcional já observada e sem fornecedor

A leitura completa do log de R01, incluindo nomes com prefixo `libnv`, identificou também a busca exata de `libnvcuextend.so.620.70.06`. O mesmo PID tentou-a no caminho privado e no sistema, sem executar um inicializador. O caminho `/files/lib/libnvcuextend.so.620.70.06` inexiste na árvore do commit OSTree assinado. R01 terminou o grafo apesar dessa ausência.

Antes da R02, manter exatamente os quatro aliases do protocolo e acrescentar ao registo a observação desta busca histórica. A sua tentativa é admissível apenas enquanto permanecer sem inicialização. Se o processo carregar qualquer fornecedor desse nome, falhar o gate. Uma nova busca de driver fora das quatro identidades internas e desta ausência específica também encerra a campanha. Esta regra não acrescenta ficheiros ao loader, não adia a falha de providers mistos e não altera os resultados R01.
