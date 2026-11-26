# O SwiGLU da e28 conserva o operando da projeção down nesta entrada

Na Radeon 890M com RADV, **979 dos 2880 valores F32** do SwiGLU diferiram da referência C269. O primeiro desvio ocorreu no índice 0. A maior diferença absoluta foi 2⁻²¹ e a maior distância foi 5 ULP. Após a quantização da saída, **as 90 escalas FP16 e os 2880 códigos i8 coincidiram bit a bit** com a entrada Q8_0 observada na CPU. A decisão pré-registada é `EQUAL_EFFECTIVE_DOWN_OPERAND_ONLY`. [Protocolo](protocol.md) · [Recibo físico](receipt.json)

O ensaio tomou os operandos reais de gate e up já somados aos respetivos biases, no primeiro decode da referência CPU0, posição 189, rank 0, expert 28. O mesmo executável Vulkan submeteu quatro segmentos consecutivos de 720 pares e verificou os 432 bytes de guarda de cada saída. O quinto despacho quantizou a concatenação com o shader Q8_1 original no ramo subgroup de 64. O quantizador CPU recompôs integralmente os 3060 bytes Q8_0 de referência a partir do SwiGLU CPU. [Captura das etapas CPU](../rank_cpu/) · [Verificador das representações Q8](../reference/arithmetic.py)

| Comparação, sempre na mesma linha de 2880 valores | Escalas distintas / 90 | Códigos distintos / 2880 |
|---|---:|---:|
| CPU e Radeon na ativação, ambas com quantizador CPU | 0 | 0 |
| Quantizadores CPU e Radeon sobre a mesma ativação Radeon | 0 | 0 |
| Entrada down observada na CPU e entrada efetiva produzida na Radeon | 0 | 0 |

O SHA-256 dos 3312 bytes de Q8_1 foi `6215822f56ad6d4c855433a44997aa5802ce0f487c224e89b3607b31c8b1fcfa`. O contraste para o dot MXFP4 extrai somente escalas e códigos. As somas adicionais e o padding pertencem à disposição Q8_1. A comparação abrange a expressão completa e deixa por identificar a primeira operação aritmética interna que divergiu. A igualdade observada permite prosseguir para o dot down desta linha. A paridade da projeção inteira, a reutilização de buffers no manager e as metas de tempo do cliente continuam em aberto.

O pré-registo ficou selado em `beea8efb`, e a checkout de execução em `aae1c6577f8dee9756f2edb306880893e3389fdd`. O build GLSL tem recibo `da0ca14443f5c778a60cf6c4b526141480f128b21bf898cf166dd284cf3ffd3c`. A referência CPU tem recibo `3ef107129e6d4c7afb755ac5836c9099b37a37f3eb3ab87f25fed3e9ba28dd53`. O recibo físico público é a cópia integral do original, SHA-256 `1c7fa886160b01c8f2eb0ce883faf5db666fbc00a04586c694d63ef520df4cd6`. Os cinco processos terminaram com código zero e os cinco scopes ficaram inativos. Com limite de 128 MiB por processo e swap zero, o maior pico observado foi 6 389 760 bytes. A família ocupou 0,367 s de parede.

### Reproduzir a graduação no arquivo privado

Definir `CPU` e `RADV` como as pastas arquivadas das famílias `tesy-e28-rank-cpu-physical-20261125-r01` e `tesy-e28-swiglu-physical-20261125-r01`. Executar nesta pasta. A comparação relê os quatro segmentos e o quinto resultado sem aceder a pesos ou a um dispositivo.

```sh
python3 -IB - "$CPU" "$RADV" <<'PY'
from pathlib import Path
from runpy import run_path
import hashlib, json, sys

cpu, radv = map(Path, sys.argv[1:])
row = Path("receipt.json").read_bytes()
assert hashlib.sha256(row).hexdigest() == "1c7fa886160b01c8f2eb0ce883faf5db666fbc00a04586c694d63ef520df4cd6"
assert (radv / "receipt.json").read_bytes() == row
r = json.loads(row)
assert hashlib.sha256((cpu / "receipt.json").read_bytes()).hexdigest() == r["cpu_receipt_sha256"]
g = run_path("grade.py")
a = run_path("../reference/arithmetic.py")
source = cpu / "ALIAS/rank"
gold = (source / "swiglu.f32").read_bytes()[:11520]
q8 = (source / "down-rank0.q8").read_bytes()
assert hashlib.sha256(gold).hexdigest() == r["inputs"]["swiglu"]
assert hashlib.sha256(q8).hexdigest() == r["inputs"]["q8"]
raw = []
for j in r["jobs"]:
    data = (radv / j["name"] / "actual.bin").read_bytes()
    assert hashlib.sha256(data).hexdigest() == j["files"]["actual.bin"]
    raw.append(data)
assert [j["name"] for j in r["jobs"]] == ["a0", "a1", "a2", "a3", "q8"]
result = g["evaluate"](gold, q8, g["assemble"](raw[:4]), raw[4], a)
assert result == r["result"]
print(result["decision"])
PY
```
