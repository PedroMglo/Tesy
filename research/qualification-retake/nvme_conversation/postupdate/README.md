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
