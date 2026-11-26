# R02 valida a identidade de sessão na preparação

R01 chegou ao validador do cliente C281 com um nome de unidade sem o prefixo `tesy-c281-nvme-`. O launcher terminou antes de abrir os pesos, com zero processos de modelo e zero pedidos. O primeiro preflight só tinha validado os inputs das quatro receitas. A preparação de R02 executa agora a mesma função de identidade que o cliente e usa o prefixo exigido desde a preparação. O destino original e o recibo FAIL são preservados. Mantêm-se os quatro braços, binários, workloads e critérios publicados antes da medição.
