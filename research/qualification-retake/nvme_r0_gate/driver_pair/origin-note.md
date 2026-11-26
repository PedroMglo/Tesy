# Origem dos auxiliares da fixture C269

**REPRODUZIDO em leitura.** O log glibc de um único PID da R01 contém 21 nomes procurados e 20 ELF inicializados. O preflight identificava 18 dependências ligadas. Os dois auxiliares inicializados depois do startup vieram da instalação Fedora 620.73.04. O módulo ativo reporta 620.70.06 com Build ID `806934c7f3b3ed1f6b1442add8db04da5874cf75`. O pacote Flatpak fornece bibliotecas de utilizador. A identidade do módulo foi lida separadamente em sysfs.

| SONAME | R01 | Objeto no deployment de 620.70.06 | Identificação |
|---|---|---|---|
| libnvidia-ptxjitcompiler.so.1 | Init, SHA `15cedf46…33c5` | SHA `f8c1ea8b…ce44`, Build ID `d5d44f2abc34d27ee11d51b4eb5ea943b4dd7604` | O ELF do RPM 620.73.04 tem Build ID `69616cda302cab501ef74ace64c26fca28be79c9`. |
| libnvidia-nvvm70.so.4 | Init, SHA `64e62bd2…6acd` | Mesmo SHA e Build ID `42f57b5f81d06b331aa649ce72ae0a703e77f170` | Este SONAME estável tem bytes idênticos nas duas instalações. |
| libnvidia-gpucomp.so.620.70.06 | Busca sem init | SHA `c3ed1135…3e1d`, Build ID `476b3f9c9d5e68c1f31040848c1482a8468fea31` | O objeto existe no deployment. O seu uso por um novo processo exige observação. |
| libnvcuextend.so.620.70.06 | Busca sem init | Ausente da árvore assinada | Preservar a ausência. |

O commit OSTree `08d80c49344008a789e2084d3ed620a1d221321a9be5285153d647266c136cc4` corresponde à ref Flathub `runtime/org.freedesktop.Platform.GL.nvidia-620-70-06/x86_64/1.4`. A validação GPG pela remote configurada devolveu assinatura boa, chave `562702E9E3ED7EE8`. Em cada um dos cinco ELF auditados, o caminho instalado é um hardlink ao objeto identificado pela árvore assinada. O checksum OSTree normalizado, o SHA-256 dos bytes, SONAME, Build ID e DT_NEEDED foram verificados separadamente. Os auxiliares ligam a bibliotecas de sistema e não têm RPATH/RUNPATH incorporados. O manifesto do pacote identifica o SHA do instalador NVIDIA usado na construção. A auditoria usou exclusivamente os ficheiros locais. [Identidades integrais](driver_origin.json)

O FAIL da R01 continua preservado. O PTX JIT distinto e verificável constitui a nova premissa para uma única confirmação. O teste R02 requer o mesmo grafo e resultados, as quatro referências privadas de driver pré-fixadas, fecho de todas as buscas, C55/C118 e a verificação dos restantes ELF. Uma confirmação permitiria usar apenas este caminho da fixture mista. [Protocolo](homogeneous-protocol.md) · [Busca opcional](absent-query.md)

```sh
python3 -IB driver_origin.py --r01 "$R01" --new-receipt "$NOVA_PROVA"
```
