# C321 — Publicação autorizada e handoff para desligar

## Estado

O owner pediu «faz o push e prepara tudo para eu desligar o pc». O fecho C320, commit `d3fe39229d7451be070317de3f48b42874483a7a`, foi publicado e confirmado por `git ls-remote` na branch `campaign/120b-exact-expert-service-20261006T194311Z`. Este handoff é administração posterior ao fecho; não abre experiência nem transfere saldos. O registo histórico C320 LOCAL_ONLY permanece intacto. Main mantém `7a7d3dcbd1ff8e594ac57459c3db06306083c3ca`.

## Evidência e persistência

MEDIDO_NO_TARGET: scopes de utilizador C318/C319 inactive/dead/MainPID0, sem processos de compute na GPU; portas observadas no recibo. Ollama habitual continua active/running e não foi modificado. Não houve nova inferência nem processos alheios terminados.

SOURCE_AUDITED: o binário persistente R0 foi novamente conferido por SHA256; o GGUF conserva o stat da cadeia anterior, sem novo rehash integral. C281 conserva a sua cobertura real prepare/start/health/reuse/stop; C321 não repete nem amplia essa cobertura. O perfil utilizável continua `slots40-persistent`, M3 parcial, M4 NOT_MET, sem novo preset promovido.

`results/c321-publication-shutdown-handoff-20261007/handoff.json` enumera assets persistentes e identidades. O índice raw integral permanece em `results/c320-exact-expert-service-closure-20261007/raw/epoch-raw-index.json`. Builds, pesos, raw e pack lossless ficam no disco local; não constituem backup remoto. Nenhum foi apagado. As receitas e patches compactos acompanham a branch. O fecho e todos os negativos permanecem preservados.

## Depois do reboot

A época está CLOSED; não retomar física com saldo histórico. Consultar C320 e este handoff antes de nova investigação. Para utilizar R0, escolher explicitamente `slots40-persistent`; o launcher exige inventário fresco, AC/performance, recursos e identidades admissíveis. Não iniciar automaticamente inferência no reboot, reconstruir silenciosamente artefactos ou usar os presets antigos com paths /tmp ausentes.

A partir da raiz Git, com nova pasta de sessão e porta livre:

```sh
tesy_session="$PWD/results/manual-r0-$(date -u +%Y%m%dT%H%M%SZ)"
python tools/c143_slots40_optin.py prepare --profile slots40-persistent --cap-bytes 21474836480 --root "$tesy_session" --port 18442 --duration-s 600
python tools/c143_slots40_optin.py command --root "$tesy_session"
python tools/c143_slots40_optin.py start --root "$tesy_session"
# health e pedidos da sessão
python tools/c143_slots40_optin.py stop --root "$tesy_session"
```

E20 é sujeito à admissão live. Estes comandos são instruções de utilização futura, não executados em C321. Nenhum novo mecanismo foi qualificado nesta administração. A sincronização final do filesystem e a igualdade HEAD/remoto serão verificadas após publicar o handoff, sem inserir um hash circular no seu próprio commit.
