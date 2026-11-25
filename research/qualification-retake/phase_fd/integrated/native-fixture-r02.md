# Reparação da identificação do manifesto do build

R01 terminou antes de compilar ou lançar um filho. O SHA-256 em
`build.py:193` fixa a serialização JSON canónica com chaves ordenadas e
separadores compactos. O ficheiro privado usa indentação para leitura. O
verificador R01 tratou o digest canónico como um hash da apresentação.

R02 valida as 171 entradas pelo método original e volta a verificar os
ficheiros individuais que liga. O teste sintético aceita indentação e
rejeita a mudança de um valor mantendo o número de entradas. Mantêm-se
os cinco braços, o binário candidato, orçamento e critérios congelados.
Usar nova raiz de saída e conservar o FAIL de R01
`41a12db8acc9604a513bbdf144c1ab1c8ee80feb7041c438f6a70a46156c4cd8`.
