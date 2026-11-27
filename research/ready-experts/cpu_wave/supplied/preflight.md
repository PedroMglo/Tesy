# Pré-voo do cliente fornecido

O pré-registo foi integrado na branch em `985db500`. Com os ficheiros reais de C280 e C293, o verificador reproduziu a identidade dos 36 pools, as cargas CPU/GPU e os logits em seis execuções históricas, três por caso. O self-test dos dois ELFs no portátil passou com os quatro conjuntos de providers sem carregar pesos.

A identidade de código R01 no commit `13e7b69a` fechou em 0,058 s quando a função do hash recebeu o nome do script como string. O erro antecedeu a gravação da proveniência e a criação da pasta do primeiro braço. Zero processos de modelo e zero amostras de custo. O recibo privado tem SHA-256 `c6083c1fb9b7fb5a1df98edd32c375c2813e874919c2d83b47468618196d7273`. A correção converte esse nome em Path. A preparação seguinte constrói os quatro comandos e verifica os providers e o monitor até à fronteira de lançamento. A execução física tem nova identidade e usa a mesma ordem e os mesmos critérios.
