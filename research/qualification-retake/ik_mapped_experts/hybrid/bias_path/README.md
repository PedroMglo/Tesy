# O lugar onde o ik soma os biases dos experts depende da largura

**REPRODUZIDO a partir do ensaio físico R03 de duas camadas.** Com BANK9 a RTX executou todas as multiplicações dos experts no prefill e no teacher. Na chamada de 32 posições as seis somas usaram os biases já residentes na RTX. Na chamada de uma posição, as seis somas executaram na CPU e leram o endereço da vista do bias no ficheiro. Os 1 056 logits do BANK9 coincidiram com o residente GPU nesta fixture. A pesquisa por nome ou o local de execução da multiplicação não bastam para identificar o executor da soma. [Contraste numérico](../device/README.md) · [Evidência e código da reanálise](audit.py)

| Braço | 32 posições, MMID → ADD_ID | Uma posição, MMID → ADD_ID |
|---|---|---|
| RESIDENT | 6 GPU → GPU | 6 GPU → GPU |
| BANK9 | 6 GPU → GPU | 6 GPU → CPU |
| BANK7 | 6 CPU → GPU | 6 GPU → CPU |

Cada célula reúne três papéis em cada uma de duas camadas. O revisor cruza os ponteiros NODE com os SUBMIT bem-sucedidos no mesmo processo e fase. Para o bias cruza ainda o endereço do operando com o SET/COPY CUDA do arranque ou a vista CPU do GGUF. A fonte do fork seleciona o duplicado quando a largura é inferior a 32 e há duplicados dos três papéis. Os recipientes da capacidade 120B verificaram que coexistem os 108 pares, num contexto inicialmente vazio. Os seis pares de operadores que mudam de dispositivo no modelo pequeno não identificam seis sincronizações independentes, nem o tempo exposto ao cliente. [Decisão no construtor do grafo](https://github.com/ikawrakow/ik_llama.cpp/blob/7a5d90009b7ae55d3239cdd33244977c4eb10ff6/src/graphs/build_openai.cpp#L34-L42) · [Censo no 120B](../capacity/README.md)

**Hipótese de engenharia.** Onde os três produtos dos experts já correm na cache da GPU, escolher os biases principais residentes poderá reduzir as travessias do resultado entre processadores. O teste de 16+1 do 120B observará para cada ADD_ID o executor, o endereço do operando e os IDs lógicos. Se o percurso já ficar na GPU ou as travessias deixarem de existir com o observador desligado, o antecedente pequeno não justifica mudar o backend do produto. Se o percurso for confirmado, o menor contraste causal é manter o mesmo banco/routing e variar somente a escolha de bias com o banco elegível. Exigir a igualdade dos logits e rotas na fixture pequena, preservar o fallback e comparar o tempo com o observador desligado. A variante ainda não tem medição de velocidade. [Contrato do próximo teste no modelo original](../full_parity/protocol.md)

O comando abaixo usa uma nova pasta e reabre apenas os recibos e stdout selados. Os originais e o arquivo deram SHA-256 `e163daebf006665b2a382ed787bf87062156c41594c1b72223515d270d1fc11b`. As execuções não carregam pesos nem acedem à RTX.

```sh
python3 -IB audit.py "$TINY_R03" --new-output-dir "$NOVO"
```
