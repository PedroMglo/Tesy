# O KV de ON coincide até à camada 25 nas três posições

No snapshot de 192 posições do bloco ON, **todas as 512 palavras de K e de V de cada nova posição coincidem com AR até à camada 25 inclusive**. As primeiras diferenças do KV nas três posições aparecem na camada 26. A camada 25 já apresentava diferenças nos logits do router nas posições 189 e 190. A convergência do KV em F16 deixa em aberto diferenças na query, na atenção, no seu output, no residual e nos valores F32 que se podem arredondar para o mesmo F16. O snapshot também não guarda a ativação F32 que entrou no router. [Contrato](protocol.md) · [Resultados máquina-legíveis](receipt.json)

| Posição | Primeira camada com KV diferente em OFF | Primeira camada em ON | K diferentes no primeiro desvio de ON / 512 | V diferentes / 512 | Palavras diferentes em OFF / 36 864 | Em ON / 36 864 |
|---:|---:|---:|---:|---:|---:|---:|
| 189 | 26 | 26 | 491 | 501 | 9 925 | 9 925 |
| 190 | 13 | 26 | 478 | 495 | 22 468 | 9 973 |
| 191 | 14 | 26 | 481 | 495 | 22 303 | 9 911 |

No total, mudaram 54 696/110 592 palavras das três posições novas em OFF, e 29 809/110 592 em ON. O snapshot completo contém 5 898 240 palavras F16 por processo, repartidas entre 192 células nas 18 camadas ímpares e 128 células nas 18 camadas pares com atenção deslizante. A parte comum ao prefixo de 189 permaneceu idêntica em 11 304 linhas por processo; 108 linhas das camadas de janela deslizante expiraram. K e V em conjunto acrescentam 216 linhas relativas às três posições. O tamanho integral passou de 11 690 596 para 11 801 224 B, incluindo os índices de posição e o cabeçalho. Nos três processos, V está armazenado por célula. [Descodificador e tradução de posições](screen.py)

A validação física de origem é independente do diagnóstico. O log identifica o filtro de camada e o tipo de cada cache em cada processo. Para AR, OFF e ON, as 84 linhas Kcur/Vcur de F32 nas camadas 0–13 reproduziram exatamente as respetivas linhas F16 do snapshot; a cobertura direta é de 43 008 palavras por braço. O significado das camadas seguintes assenta nas mesmas regras de escrita e nos filtros registados pelo C269. A implementação consome o ficheiro até ao último byte e os testes detetam trocas de célula, formato inválido, extensão indevida e diferença no sinal de zero. [Testes sintéticos](test_screen.py)

O C270 conserva a entrada attn_post_norm da camada 25 de AR para 189/190, e este par conserva o correspondente resultado do router em ON. A próxima observação discriminante é recolher a entrada **de ON** da mesma camada juntamente com a sua atribuição de buffer e o resultado. Uma entrada igual a AR isola a diferença na projeção ou na sua recomposição; uma entrada diferente move o ponto de investigação para o caminho anterior. No segundo caso, na mesma aquisição interessam a saída da camada 24, Q/K/V pós-RoPE aplicável e o resultado da atenção da 25. A posição 191 continua sem gold do router nessa camada.

Pré-registo b43d3b5f; execução offline da revisão c2216a58, 0,23 s e 81 528 KiB de RSS máximo. Nenhum forward adicional. O recibo recuperado tem SHA fb3fc4f954085c69073a36e833040b4664e6dbc3d00140b8ebc2c5acfaec8283.

```sh
python3 -IB "$UNIT/kv/screen.py" --backend "$C269" --family "$INTEGRATED_PAIR" \
  --archived "$PARTS/part-102/tesy-b3-first-boundary-physical-20261125-r01" \
  --new-output-dir "$FRESH"
```
