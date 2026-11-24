# Ponte numérica contemporânea do R0

A janela C55 dedicada r2 admitiu 18 GiB e recusou os 20 GiB operacionais. Para o diagnóstico E18 em 40 slots, a derivação da política atual passou a função do monitor com `limits={}`. O tuplo do ficheiro NVMe coincidiu com a observação contemporânea de C55. A entrada do cliente R0 C270, o pin do backend e as cinco bibliotecas numéricas partilhadas com C281 conferiram. A referência independente C127 ON passou o digest integral e a auditoria dos 1 500 payloads, cinco vetores e testemunhos. [Pré-registo](protocol.md) · [Inventário de inputs](inputs/receipt.json) · [Recibo da janela E18](r2_precheck.json)

A preparação aceita um dos perfis `E20_R0` e `E18_DIAGNOSTIC_ONLY`, cada um em nova identidade. Rejeita divergências do commit de medição, gold, ELFs, política, tuplo GGUF e cap. Produz protocolo e comandos privados para o monitor e o validador históricos. Com `--execute`, coordena um só serviço transitório, conserva os raws após qualquer falha e exige o resultado do gate numérico. O cap de E18 pertence exclusivamente à nova captura de diagnóstico com o mesmo cliente C269, P12/slots40/ub32. Uma conversa pelo servidor persistente C281 requer uma qualificação de serviço separada. [Preparador](prepare.py) · [Auditoria do braço](measure.py)

```sh
TESY_GATE=research/qualification-retake/nvme_r0_gate
python3 -B -m unittest discover -s "$TESY_GATE" -p test_selected.py
python3 -B "$TESY_GATE/prepare.py" \
  --measurement-commit "$TESY_MEASUREMENT_COMMIT" --envelope E18_DIAGNOSTIC_ONLY \
  --window "$TESY_C55_WINDOW" --placement "$TESY_PLACEMENT_RECEIPT" \
  --unit "$TESY_NEW_UNIT" --new-output-dir "$TESY_NEW_PRIVATE_ROOT"
```

Sem `--execute` o comando verifica o protocolo da unidade limpa e termina com `PREPARED_ONLY`. Para o braço admitido usar `--execute`, com outra unidade e diretório. O diretório `raw` armazena as ativações, os IDs e os logits e deve ficar privado. [Referência C127 e âmbito](../../../research/C127-SLOTS40-NUMERIC-RESULT-20260929.md)

**MEDIDO no portátil, E20_R0 PASS_SELECTED_C269_BRIDGE.** Uma nova janela C55 r3 admitiu 22 GiB e o processo abriu no seu cgroup de 20 GiB após 61 amostras de C118. Um único carregamento do 120B original completou a captura C270 em P12/slots40/ub32. Os 1 500 payloads de estados, as máscaras e os cinco vetores completos finitos igualaram C127 ON bit a bit. A auditoria de consumo verificou 996 componentes em 166 combinações. Os vetores correspondem ao fim do prefill e aos passos decode 0, 1, 7 e 31. O resultado é uma ponte numérica para as bibliotecas contemporâneas partilhadas com C281. A qualificação da conversa do servidor permanece M3 PARTIAL e M4 NOT_MET. E18 ficou por executar. [Recibo numérico](e20_measured/selected.json) · [Execução física](e20_measured/receipt.json)

O monitor mediu 37,319 s no processo. O intervalo incluindo C118, serviço e comparação durou 104,424 s. O pico do cgroup foi 15 933 677 568 B, a GPU atingiu 6 882 MiB ocupados, a CPU 70,25 °C, a GPU 52,07 °C e o NVMe 49,85 °C. O monitor observou swap zero e máximos de três FDs diretos e um buffered. A unidade systemd terminou com sucesso; a verificação posterior encontrou o PID e o cgroup encerrados. Os 89 013 034 B de dados locais ficaram privados na checkout persistente em `build/qualification-c269-r0-e20-20261124-r1/raw`. O recibo de execução tem SHA-256 `54d66b2e7e8578fd85db4a7e19faa80cae98c658497b7b4096025c40768064c2`. [Proveniência e encerramento](e20_measured/cleanup.json)
