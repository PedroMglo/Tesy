# C281 — R0 persistente disponível por seleção explícita

**R0_PERSISTENT_LAUNCHER_TWO_REQUEST_PASS**, MEDIDO_NO_TARGET. Measurement HEAD `a316109`. Freeze,18 testes dirigidos e receita são anteriores ao modelo. Ciclo completo237,101021s, incluindo prepare/inventário60s, start/inventário60s, health, duas respostas com histórico real e stop. Readiness4,041968s apósPopen; nenhum serviço permanente/default alterado.

|Pedido|IDs oficiais|cache/new|outputs reportados|finish|final|prefill|decode|first-final|completion wall|
|---|---:|---:|---:|---|---|---:|---:|---:|---:|
|c112-code|2043|0/2043|78|stop|48327|62,591810s|20,476098s|82,635763s|83,076003s|
|c112-repeat|2197|2044/153|47|stop|48327|11,133648s|10,229705s|21,090541s|21,372010s|

Ambos funcionais e prefix/accounting PASS. O segundo inclui o assistant realmente gerado; não é transcript fixo A/B. `code` é cinco dígitos, não teste de programação. Mensagens/reasoning, render/template, arrays oficiais, watchdog e respostas integrais permanecem no raw local com hashes. OutputIDs continuam NOT_EXPOSED_EMPTY_OR_ABSENT; não houve retokenização ou conversão de usage em forward calls. Tempos HTTP são descritivos, sem atribuição causal ou nova qualificação M4.

Cap20GiB/high=max,swap0; cgroup peak15.784.923.136B, sampled memory.current máximo15.763.701.760B, GPU total6860MiB. CPU Tctl95,375°C é warning válido, não FAIL; GPU62°C, NVMe52,85°C. OOM/high/max/swap/PSI zero observados. Clocks/energia UNKNOWN. FDs do modelo observados direct, buffered0; nenhum contador lógico/read_bytes é rotulado tráfego físico NVMe. Bibliotecas numéricas mapeadas coincidem; libgomp/OMP/GOMP/KMP e dependências externas conferidos no processo verdadeiro. `INTERRUPTED_BY_OWNER` no recibo do monitor é o stop programado depois de ambos os pedidos, returncode0; não uma interrupção dos pedidos ou um resource stop.

O novo servidor/mtmd tem identidade própria e source maduro; importa os mesmos DLLs numéricos C269/C270, sem recompilação numérica. Receita e runtime-manifest persistentes; desaparecimento/mudança de binário/libs/GGUF/env falha no preflight, sem auto-rebuild. Default CLI histórico `slots40` e C35 ainda apontam para os /tmp históricos ausentes: não os anunciar prontos. A seleção **slots40-persistent** é o caminho restaurado explicitamente utilizável no portátil atual. M3 PARTIAL, M4 NOT_MET; esta verificação não repete qualidade12/sessão83min ou amplia cobertura full8K.

## Invocação explícita

A partir da raiz Git física, escolher um root **novo** e porta livre. O prepare faz inventário/admissão correntes; start volta a recolher60s e só depois permitePopen. Os valores/unset OMP/GOMP/KMP têm de coincidir com o manifesto; não exportar GOMP0. API em127.0.0.1, medium, template/data de sessão e contexto8192. Para o âmbito testado, requests com temperature0/seed42/cap256.

```sh
tesy_session="$PWD/results/manual-r0-$(date -u +%Y%m%dT%H%M%SZ)"
python tools/c143_slots40_optin.py prepare --profile slots40-persistent --cap-bytes 21474836480 --root "$tesy_session" --port 18442 --duration-s 600
python tools/c143_slots40_optin.py command --root "$tesy_session"
python tools/c143_slots40_optin.py start --root "$tesy_session"
# Depois do health e dos pedidos, terminar apenas este processo:
python tools/c143_slots40_optin.py stop --root "$tesy_session"
```

Prepare não inicia inferência; start é uma escolha explícita, bounded, sem serviço habitual. Health é `http://127.0.0.1:18442/health`; não assumir pronto antes de ok. O processo também termina pelo timeout congelado. Em falha de admissão, diagnosticar; não reduzir contexto/KV ou trocar perfil no mesmo histórico. Não transferir KV entre identidades. Paths persistentes são locais, não uma distribuição portátil. Rebuild futuro requer identidade/bridge próprios; ver `runtime-manifest.json`, `configure-receipt.json` e CMake pinado em `tools/persistent_server_build`.
