# Tesy

Inferência local de modelos Mixture-of-Experts maiores do que a VRAM e a RAM disponíveis. O caso de referência é uma conversa com o GPT-OSS-120B MXFP4 num Ryzen AI 9 HX 370, RTX 4060 Laptop de 8 GiB, 32 GiB de RAM e NVMe. O target conserva routing, top-k, experts, quantização, contexto e confirmação de tokens.

**Estado do 120B.** R0 `slots40-persistent` é o controlo operacional opt-in. M3 está parcial e M4 continua por atingir. O objetivo nominal é chegar ao primeiro conteúdo final em até 10 s e sustentar pelo menos 6 tok/s de decode. A última decisão experimental está em C320. C321 regista a publicação e o ponto de retoma. A reorganização de novembro reuniu o laboratório, a fundação, a tese e os relatórios científicos na `main`. [Fecho C320](research/C320-EXACT-EXPERT-SERVICE-ARCHITECTURAL-CLOSURE-20261007.md) · [Receita R0 e limites](research/C281-PERSISTENT-R0-RESTORATION-RESULT-20261005.md)

## Retomar o trabalho

1. Ler a [segunda reanálise e decisões de integração](research/consolidacao-20261123/README.md) e a [decisão de arquitetura](docs/architecture/0004-servico-exato-de-experts.md).
2. Reproduzir os cálculos sobre os recibos compactos da `main` com `python3 research/post-c320/analyse.py`. O passo seguinte, medir ocupação dos workers, requer os oito journals C317 identificados pelo comando.
3. Usar o [prompt de continuação para o Codex](research/consolidacao-20261123/PROMPT-CODEX.md) para o trabalho no portátil. Os [comparadores e a literatura](research/post-c320/literatura.md) fixam a fronteira dos claims.

## Onde trabalhar

| Área | Conteúdo |
|---|---|
| [tools](tools), [patches](patches), [workloads](workloads) | Runtime experimental, launcher, clientes, receitas e avaliadores do laboratório. Os binários e os pesos físicos têm proveniência própria. |
| [research](research), [results](results) | Protocolos, fechos e evidência compacta por campanha. Os FAILs e as qualificações parciais conservam o âmbito original. |
| [src/tesy](src/tesy), [native](native), [scripts](scripts), [tests](tests) | CLI de fundação, simuladores, tracer, operadores e testes sem modelo. [Estado de implementação](IMPLEMENTATION_STATUS.md) |
| [Documentação científica](docs/research-reports/README.md), [tese](docs/thesis/first-meeting-20261017/README.md) | Relatórios LaTeX, locks da evidência, política de publicação e materiais de apresentação. |
| [Modelos e locks](MODELOS_A_INSTALAR.md) | Identidade e função de cada artefacto. |
| [Inventário de branches original](research/consolidacao-20261123/branches.json) | Nomes e commits recuperáveis a partir da história da `main`. |

## Ambiente de desenvolvimento

A partir da raiz do repositório, num ambiente Python 3.11 ou posterior:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
tesy --help
```

O estado científico continua `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`. Uma contribuição estreita exige um efeito causal replicado ou um limite explicativo que sobreviva a comparadores fortes. O Ollama serve de comparação de experiência de utilização. [Reanálise e limites da evidência](research/post-c320/README.md)
