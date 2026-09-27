# Registo da reconstrução e revisão documental

Esta validação foi repetida no ambiente retomado; não reutiliza contagens ou hashes de artefactos que deixaram de estar disponíveis. Sete publicações foram reconstruídas e verificadas por tamanho, SHA-256 e Git blob SHA. O commit base e as árvores raiz/docs também coincidem nos Git object IDs; ver git-base.json. Não houve verificação GPG independente.

A resolução DNS deste sandbox impediu clone direto. O conector GitHub continuou utilizável. Não foi estabelecida a causa da falha DNS nem alterada a rede do utilizador.

O primeiro build R00 da reconstrução foi recusado: overfull hbox de 20,82497 pt no rótulo STATIC_NO_GO_PIN_FIT_CONFLICT. A quebra passou a usar path/xurl; o gate não foi relaxado. O diretório de build falhado permanece em _build, fora da publicação.

A revisão visual também acrescentou separação após tabelas e normalizou espaços entre modelos, números e unidades. Os valores e snapshots não foram alterados. Raws experimentais não foram lidos ou reanalisados. Testes negativos da ferramenta de publicação usam PDFs sintéticos claramente rotulados; não contam como compilação real dos relatórios. Os release manifests são a evidência dos builds reais.
