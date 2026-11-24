# Recuperação das evidências locais

O arquivo privado do projeto tem a identidade `qualification-20261124-nvme-01`. Cada lote foi publicado sob um nome exclusivo depois de conferir os tamanhos e SHA-256 de todos os ficheiros contra a origem e reler as cópias. A raiz tem permissões 0700 e os ficheiros 0600. O índice com os caminhos das origens permanece dentro do arquivo local.

| Lote | Evidência incluída | Ficheiros | Bytes |
|---|---|---:|---:|
| part-01 | C266 CUDA35 e rows153 com todas as tentativas, colocação, C55 R1, ABBA, canário32 e logs/recibos stock até start R2 | 103 | 687 116 |
| part-02 | Canário28, logs do build, pré-admissão e FAIL R1 antes do spawn | 30 | 122 446 |

Os [recibos do primeiro lote](part-01.json) e [do segundo lote](part-02.json) contêm o hash do manifesto privado e a contagem por unidade. Na estação que tem o arquivo, apontar `TESY_PRIVATE_ARCHIVE` para o diretório que termina no nome da sua identidade e verificar os lotes.

```sh
python3 -B research/qualification-retake/private_archive/verify.py "$TESY_PRIVATE_ARCHIVE" research/qualification-retake/private_archive/part-01.json
python3 -B research/qualification-retake/private_archive/verify.py "$TESY_PRIVATE_ARCHIVE" research/qualification-retake/private_archive/part-02.json
```

Cada entrada do manifesto é um caminho relativo ao lote. O verificador confere a identidade do manifesto antes dos dados e deteta divergências em ficheiros e diretórios. Os raws, o mapeamento dos caminhos pessoais e o registo de reposição da sessão permanecem privados. Os índices públicos não contêm prompts. Os raws de campanhas posteriores recebem lotes novos.
