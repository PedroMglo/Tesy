# Dois turnos C281 com o perfil de driver autenticado

A preparação usa o recibo privado da resolução estática e o recibo físico C270 E20 que o operador indicar por SHA-256. A saída de um ensaio E18, de um C270 anterior com outra identidade de runtime ou de um C270 sem os cinco vetores e os 1 500 payloads fecha a preparação. O perfil compara ainda o mapa, o módulo, a origem dos auxiliares, os manifests de execução, o diário do próprio PID e a seleção numérica contra os ficheiros privados autenticados. A janela C55 do serviço tem identidade própria. [Protocolo físico](../../nvme_r0_gate/driver_pair/server_startup/physical-protocol.md)

A sessão mantém o comando do servidor, os dois POST, o orçamento, os relógios de cliente e os validadores de C281. O cliente confirma os 2 043 e 2 197 IDs de entrada e o retorno de 2 044 posições em cache no segundo turno. O perfil verifica o processo e as suas VMAs em READY e no fecho do segundo pedido. Preserva a contabilidade de uso e o comportamento de streaming legado. Os IDs completos de saída exigem uma testemunha própria. [Par histórico e fases](../README.md)

Para preparar sem iniciar um servidor, usar a checkout de medição limpa e um destino privado novo. O modo de execução exige `--execute` e outro destino exclusivo. Cada modo gera o seu próprio recibo.

```sh
entry=research/qualification-retake/nvme_conversation/postupdate/profile.py
python3 -IB "$TESY_CHECKOUT/$entry" --repo "$TESY_CHECKOUT" \
  --commit "$TESY_MEASUREMENT_COMMIT" --unit "$TESY_NEW_C281_UNIT" \
  --window "$TESY_C55" --window-sha256 "$TESY_C55_SHA" \
  --placement "$TESY_PLACEMENT" --c270 "$TESY_C270/receipt.json" --c270-sha256 "$TESY_C270_SHA" \
  --preflight-dir "$TESY_STATIC" --preflight-sha256 "$TESY_STATIC_SHA" \
  --new-output-dir "$NOVO_RESULTADO_PRIVADO"
```

A versão de preparação foi ensaiada com quatro testes CPU, incluindo recusa de E18, SHA do preflight divergente, mapa do primeiro cliente incompleto, loader anterior adulterado e variáveis de processo cruzadas. A leitura da seleção estática R01 e dos dois inputs históricos permitiu verificar o digest completo da nova seleção, `f11c3f000fb4a0b9778c2fb465d94f9c228b91f0e8d69d47e7bd6c6e7adefbdc`. Recolocar apenas o nome histórico do ficheiro de libcuda reproduziu exatamente o digest das entradas C281 anteriores, `3351fcc91bcb8a82029b13ea3e48630880b54d415b76371e56fa0c4c9e1b0bfe`. Os argumentos de atividade do modelo, os SHA de todos os ELF, a data do template e os hashes dos prompts fazem parte dessa comparação. A confirmação estática usou zero forwards. A medição futura usa sempre os caminhos realmente selecionados no novo perfil.

A execução física de 25 de novembro completou e validou os dois turnos. [Resultados, relógios e encerramento](physical-result.md)

## Repetir o par a partir da checkout de medição

No portátil com o mesmo módulo NVIDIA, os builds históricos, os dados de referência C127/C281 e o recibo de colocação já verificado, o exemplo seguinte prepara uma nova identidade por fase, por baixo de um diretório privado em tmpfs. Executar na raiz limpa da checkout física `14b409d75eaa0e6a976fd9b6ebb4b80396ee1df3`. O cap de 20 GiB, a reserva, as temperaturas e a origem do modelo continuam a ser validados pelos programas. Cada execução completa carrega o modelo uma vez para C270 e uma vez para o par C281.

```bash
set -eu
umask 077
repo=$(git rev-parse --show-toplevel)
measurement_commit=$(git rev-parse HEAD)
test "$measurement_commit" = 14b409d75eaa0e6a976fd9b6ebb4b80396ee1df3
study="$repo/research/qualification-retake"
gguf=/home/pmglo/models/tesy-gpt-oss-120b-nvme/gpt-oss-120b-MXFP4.gguf
placement="${TESY_PLACEMENT:?indicar o receipt.json privado de colocação verificada do GGUF}"
root=$(mktemp -d /tmp/tesy-e20-XXXXXXXX)
tag=$(basename "$root" | tr '[:upper:]' '[:lower:]')
digest() { sha256sum "$1" | cut -d' ' -f1; }

python3 -IB "$study/nvme_r0_gate/driver_pair/server_startup/screen.py" \
    --repo "$repo" --new-output-dir "$root/static"
env LD_LIBRARY_PATH="$root/static/monitor" python3 -B "$study/nvme_admission/window.py" \
    --nvme-model "$gguf" --new-output-dir "$root/c55"
common=(--preflight-dir "$root/static" --preflight-sha256 "$(digest "$root/static/receipt.json")"
        --window "$root/c55" --window-sha256 "$(digest "$root/c55/receipt.json")" --placement "$placement")
python3 -IB "$study/nvme_r0_gate/qualified_profile/profile.py" --checkout "$repo" \
    --measurement-commit "$measurement_commit" --unit "tesy-c270-$tag" "${common[@]}" \
    --new-output-dir "$root/num" --execute
python3 -IB "$study/nvme_conversation/postupdate/profile.py" --repo "$repo" --commit "$measurement_commit" \
    --unit "tesy-c281-nvme-$tag" "${common[@]}" --c270 "$root/num/receipt.json" \
    --c270-sha256 "$(digest "$root/num/receipt.json")" --new-output-dir "$root/chat" --execute
```

O último comando inicia o servidor em loopback, envia os dois pedidos, valida o histórico e encerra o próprio serviço. O recibo de `chat` distingue as metas nominais e o encerramento. Os ficheiros em `chat/raw` contêm dados de conversa e ficam no arquivo privado. A execução de novembro usou o recibo de colocação SHA-256 `50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7`. [Colocação e reprodução](../../nvme_placement/README.md)
