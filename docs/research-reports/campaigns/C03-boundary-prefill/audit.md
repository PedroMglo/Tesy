# Auditoria C3

Revisão de autoria das oito afirmações de `evidence-spec.json` face ao fecho C3, ao resultado broad e aos quatro resumos compactos. Os valores extraídos e unidades foram confrontados com as fontes congeladas. A paridade bitwise fica restrita às ativações capturadas; as séries de prefill têm três pares por prompt; o serviço sustentado é um conjunto fixo de 20 pedidos; o diagnóstico stock20B cap3072 é selecionado após C2. A divergência histórica no texto de reasoning continua sem causa numérica identificada. O default permanece o de C2.

O PDF de seis páginas foi renderizado e inspecionado visualmente: capa e tabela, contrato, resultados, decisões, apêndice, índice de fontes, margens, fontes, cabeçalhos, rodapés e quebras. O build passou o gate de referências/layout e a compilação byte a byte reprodutível no ambiente registado. Não houve execução de modelos, acesso a raws ou validação física independente. `audit.json` fixa os bytes finais efetivamente revistos.
