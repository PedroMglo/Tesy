# R0 E20 depois da atualização do driver

**PASS da ponte numérica C270.** O processo com o capture C269, P12, 40 slots e ub32 reproduziu os **1 500 payloads**, as máscaras e os **cinco vetores completos de logits** de C127. O verificador observou 996 componentes em 166 combinações de consumo. Os cinco vetores correspondem ao fim do prefill e aos passos de decode 0, 1, 7 e 31. A comparação offline voltou a abrir a captura e a referência C127 autenticada, com o mesmo resultado do verificador original. O SHA-256 de `selected.json` permanece `786b6911b7d56a78fc59a6c23d67f748e8dad8c6dd08da6c8608fd80b37681f3`. A ponte admite a qualificação separada do servidor C281. M3 continua PARTIAL e M4 NOT_MET. [Recibo compacto](evidence/receipt.json) · [Referência antes da atualização](../e20_measured/selected.json)

| Etapa | Observação |
|---|---|
| Preparação | Zero lançamentos. O preflight estático ligou a identidade do capture e as 18 dependências iniciais ao perfil C270. |
| Admissão | C55 admitiu 20 GiB. C118 reuniu 61 amostras em 60,142 s. A última amostra antecedeu o spawn em 42,956 ms. |
| Execução física | Um processo de 35,847 s entre 08:25:13 e 08:25:48 UTC de 25 de novembro de 2026. A telemetria do filho contém 52 amostras. |
| Bibliotecas | Em 137 inspeções dos mapeamentos do PID, o supervisor verificou as identidades dos objetos. O journal do loader regista 21 nomes procurados e 21 objetos inicializados. Os quatro fornecedores de CUDA autorizados vieram do deployment 620.70.06. A busca opcional de `libnvcuextend` terminou sem fornecedor. A NVML do monitor foi validada em separado. |
| Recursos e encerramento | Pico do cgroup de 15 859 171 328 B, RSS de 15 979 229 184 B e uso global máximo de GPU de 6 882 MiB. Máximos de 70,875 °C na CPU, 52,38 °C na GPU e 44,85 °C no NVMe. Zero swap e zero incrementos nos contadores do cgroup. O perfil confirmou o fim do filho e do serviço. |
| Relógios | A janela de 96,551 s inclui C118, execução e encerramento do scope. A auditoria dos ficheiros e a comparação numérica decorrem depois. A sua duração individual ficou por medir. |

O recibo privado da execução tem SHA-256 `1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6`. A checkout medida foi `14b409d75eaa0e6a976fd9b6ebb4b80396ee1df3`. O diretório raw ocupou 89 039 477 bytes. O resultado aplica-se aos pesos e aos passos observados. O número individual de chamadas ao grafo, a qualidade de uma resposta natural e os relógios cliente exigem observações próprias.

Para reproduzir o compacto após mover o arquivo, indicar separadamente a execução fechada, o seu pré-voo sem modelo, a pasta do preflight estático que contém o mapa privado, e o diretório de gold C127 com os 3 266 ficheiros originais. Os nomes absolutos gravados no journal são ligados às entradas do manifesto da época. A verificação conserva os FAILs e as contagens de processos realmente lançados.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -IB compact.py \
  --checkout "$TESY_CHECKOUT" --closed-run "$C270_RUN" \
  --preparation-dir "$C270_PRECHECK" --environment-dir "$DRIVER_PREFLIGHT" \
  --gold-dir "$C127_GOLD" | cmp - evidence/receipt.json
```
