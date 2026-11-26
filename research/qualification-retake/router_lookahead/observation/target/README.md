# A sonda +1 chega ao loader de C281 e reproduz os ranks arquivados

A DSO privada C291 passou as relocações e a seleção dos 24 providers de C281 e dos 18 de C292. O seu projetor C++ reproduziu, no próprio operando, os **3 400 quartetos ordenados** da captura C270. Ao prever a camada seguinte, as suas **3 303 previsões** coincidiram integralmente com o surrogate Python anterior. As comparações usaram os parâmetros autenticados e as ativações já guardadas. As larguras observadas foram 1, 29 e 32. A de 5 e a de 20 continuam por qualificar no caminho natural. [Recibo](result.json) · [Método](protocol.md) · [Calibração](calibrate.py)

| +1 contra routing oficial | Linhas | IDs presentes no top-4 oficial / IDs propostos |
| --- | ---: | ---: |
| Prefill CPU | 2 232 | 6 932 / 8 928 |
| Prefill CUDA | 931 | 2 826 / 3 724 |
| Decode CPU | 96 | 313 / 384 |
| Decode CUDA | 44 | 155 / 176 |

Duas unidades de compilação do C291 foram recompiladas na árvore limpa `442dff1f3b6407e58b1dec59e0bd518b522685e2`. A build demorou 14,621 s, pico de 508 792 832 B no cgroup e limite de swap zero. O teste de integração de interfaces usou tensores de teste e transportes em memória. Exercitou a coabitação com um callback existente, a ordem das linhas, seleção da última posição, mudança de gamma e falha com gamma zero. Esta etapa não lançou servidor, forward nem GPU. O resultado permite ensaiar neutralidade numérica no mesmo ELF. [Build](build.py) · [Controlos](controls.cpp)

No modo ON, o scheduler entrega o tensor ponderado já produzido para a camada fonte. O callback obtém uma cópia host das linhas da fonte, das duas gammas, da matriz de 2880×128 e do bias; o código lê os cinco buffers originais a cada local. A origem vem do buffer efetivo, incluindo o de uma vista. Os registos E35/E36 discriminam produtor, tier, bytes lógicos e intervalos de GET. E35 mede de ASK à entrada no callback DATA, incluindo o subgrafo produtor. E33 publica os ranks por posição no mutex das reservas, E34 observa a classificação autoritativa. O observador conserva o callback original e o seu pedido individual de dados. Em OFF, o caminho de submissão conserva o callback original. Os pesos só são lidos; os jobs de serviço continuam a ser comandados pelo target. [Sonda](profile.h) · [Custos do scheduler](../placement/README.md)

A primeira chamada natural de cinco tokens tem zero outputs da última camada. Nesta implementação a fonte 34 só é pedida quando a tile tem pelo menos um output; nesse caso obtém **toda** a tile e publica apenas as posições elegíveis. A passagem a callback positivo pode dividir e sincronizar a execução; a calibração de ranks não mede esse preço nem uma redução na espera. O potencial de antecipar uma leitura depende de a previsão anteceder uma falta e de os bytes poderem efetivamente ser entregues. [Fixture de reservas](../README.md)

Para reproduzir a calibração em diretório novo, definir uma thread de BLAS e OMP e executar `calibrate.py --part23 "$PART23" --bundle "$BUNDLE" --c7 "$C7" --new-output-dir "$NEW"` com o Python NumPy do projeto, sob o cap de 512 MiB. A build segue o comando do antecessor com `target/build.py`, o commit congelado, scope E2 e destino próprios. O receipt do build e o da calibração têm SHA exteriores no compacto. [Comando do build antecessor](../../../igpu_resident_rank/request_budget/device/pack_native/dso/README.md)
