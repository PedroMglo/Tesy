# O que os histogramas permitem provar

Para uma componente, codificamos separadamente as escalas e os nibbles por duas instâncias de rANS com tabela fixa. Cada stream pode escolher gratuitamente as frequências inteiras que mais lhe convenham. A soma das frequências é `M`, a frequência do símbolo atual é `f>0`, e o seu offset cumulativo é `B`. Admitimos estado inicial e final arbitrários no intervalo `[L,bL)`, `L=RM`, `R≥256`, radix `b=256`.

1. Seja `x` o estado de entrada. Enquanto o estado for pelo menos `bRf`, o encoder emite o byte menos significativo e divide o estado por `b`, arredondando para baixo. Depois de `k` emissões, `y=floor(x/b^k)≥Rf`. Se não emitir, esta desigualdade decorre de `x≥L≥Rf`.
2. O estado seguinte é `x' = floor(y/f) M + B + (y mod f)`. Como `B≥0` e o resto é no máximo `f−1`, resulta `x'≥M(y−f+1)/f`. Usando `x < b^k(y+1)`, obtemos `b^k x' ≥ x (M/f) (1−f/(y+1)) ≥ x (M/f) (1−1/R)`. A mesma normalização mantém `L≤x'<bL` pela condição de saída `y<bRf` e por `B+f≤M`.
3. Multiplicando pelos passos do mesmo stream, os estados intermédios cancelam. Os extremos contribuem pelo menos `−log2 b` bits. Para uma tabela fixa `q=f/M`, a informação acumulada `Σ n_s log2(1/q_s)` é pelo menos `N H₀` pela divergência KL da distribuição empírica relativamente a `q`. Os bits emitidos são, portanto, pelo menos `max(0, N H₀ − N log2(256/255) − 8)`, independentemente da ordem dos símbolos. Neste documento `H₀` é em bits/símbolo. Os campos `h0_bits` representam o total `N H₀`. Este argumento inclui a folga finita do coder e permite qualquer estado legal nos extremos.
4. O verificador calcula `N H₀ = N log2 N − Σ n_s log2 n_s` com limites dirigidos. Envolve cada logaritmo natural arredondado numa casa decimal representável de cada lado, divide com arredondamento para fora e converte para limites inteiros de nanobits. Usa o extremo inferior para a informação e o superior para a folga. A comparação com 20% usa inteiros, separando CPU e CUDA. Cada componente oferece dois streams gratuitos. Os bytes dos biases residentes ficam excluídos.

O cálculo permite que o melhor componente represente todos os bytes servidos. Frequências por contexto, dependência entre nibbles e escala, dicionários, informação lateral e experts fora da amostra exigem outro teste. Os histogramas não identificam ordem, contenção, serviço no caminho crítico ou desempenho de um encoder real.

## Reprodução

No topo da checkout, apontar `C319_RESULTS` para o diretório histórico `results` que contém C287 e C319. O manifesto C319, o protocolo C319 e o manifesto C287 têm SHA-256 fixos. O tamanho e SHA de cada um dos dois raws são confirmados pelas entradas desses manifestos antes do seu uso. O avaliador C319 valida também a amostra contra o índice C287 e o contrato de leitura da campanha original. O script não lê o GGUF.

```sh
python3 -B -m unittest discover -s research/qualification-retake/mxfp4_entropy -p 'test_screen.py'
python3 -B research/qualification-retake/mxfp4_entropy/screen.py --results-root "$C319_RESULTS" --new-output-dir "$NEW_OUTPUT"
```

`components.json` contém a informação e os pisos de bits das duas streams para cada uma das 192 matrizes. `receipt.json` contém o seu SHA-256, os denominadores, os agregados por camada e dispositivo, o componente mais favorável e os dois testes de margem.
