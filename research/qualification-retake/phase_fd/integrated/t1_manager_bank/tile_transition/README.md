# Restaurar o primário na mudança de tile

**PASS na fixture CPU do C291.** Depois de duas tiles e três preloads reais, a reposição entregou os mesmos 40 experts nos mesmos slots da referência, com os mesmos 120 hashes de componentes. O remap genuíno do primeiro decode recebeu [6,7,42,41] e devolveu [6,7,2,4] por hits. O leitor da última wave verificou as gerações antigas em dois slots usados tanto para procura como para parking. Ao deixar os quatro workers escrever primeiro, o leitor encontrou as duas gerações novas apesar de o primário terminal continuar igual. [Protocolo](protocol.md) · [Recibo sanitizado](receipt.json)

| Braço CPU | Novos claims | Preads do pack | SET | Publicações | Leitor de A |
|---|---:|---:|---:|---:|---|
| Reference, seleção original | 45 | 45 | 135 | 45 | Gerações antigas |
| Disk, reposição pelo pack | 51 | 47 | 153 | 51 | Gerações antigas |
| Bank, uma recuperação da RAM | 51 | 46 | 153 | 51 | Gerações antigas |
| Broken, sobrescrita antes do leitor | 51 | 46 | 153 | 51 | Gerações novas |

A referência evitou a reposição porque manteve a seleção original do manager. Nos outros braços a fixture mudou deliberadamente quatro destinos autorizados de reserva para obrigar a reconstituir o mesmo estado. Foram seis jobs de reposição, 18 SET e 79 315 200 B de payload para o primário. Quatro registos foram recolocados a partir de 52 876 800 B de scratch, incluindo a troca entre os slots 2 e 4. E7 veio do pack. Capturar os 13 219 200 B da geração de e6 antes da reserva de preload permitiu usar a RAM para e6 no braço Bank. Face a Disk a poupança isolada é uma janela lógica de pack de 13 221 888 B, com as mesmas capturas e permutações. Todos os destinos receberam gerações novas. As frequências, idades e números de geração da referência podem diferir. O resultado distingue exatidão do remap e dos payloads e a necessidade de terminar o leitor antigo. O FFN, KV, logits e custo da conversa não foram medidos nesta família.

**Custo e falhas.** R01 falhou no compilador aos 3,424 s antes de criar o pack ou iniciar qualquer braço. A ordenação automática dos headers punha a definição do store antes do tipo da camada. R02 usou a ordem de inclusão exigida pelo pin C291. Em checkout limpa `ed693945`, o build demorou 4,336 s. Os quatro processos nativos ocuparam 0,567–0,618 s cada e os sete comandos somaram 7,032 s. O pico do scope foi 778 424 320 B de 1 GiB, sem swap ou eventos de limite. O pack sintético de 79 552 512 B foi validado através do descritor de leitura e removido depois do último processo. A GPU e o modelo não participaram. A contraprova aponta para o teste do mesmo manager com os pesos primários na CUDA e o FFN em execução. [Protocolo CUDA](device/protocol.md)

A revisão independente confirmou os quatro raws contra o gerador sintético, os SHA-256 e o recibo da tentativa falhada. Duas execuções reproduziram SHA-256 `1db1f149bcd3c2703ff841b94d04fb68c621f82d4ada41a17662c55361cf2676`. No portátil, o runner requer um scope CPU de 1 GiB com swap zero, o pin C291 e dois destinos exclusivos. O verificador e os testes aceitam CPU sem GPU nem pesos.

```sh
unit=research/qualification-retake/phase_fd/integrated/t1_manager_bank/tile_transition
python3 -IB "$unit/test_review.py"
python3 -IB "$unit/compact.py" --failed "$R01" --passed "$R02" --new-output "$NEW"
cmp "$NEW/receipt.json" "$unit/receipt.json"
```
