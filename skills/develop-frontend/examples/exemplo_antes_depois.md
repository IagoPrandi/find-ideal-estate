# Exemplo — Correção típica (antes/depois)

## Sintoma
Cards em uma grade usam `justify-between`, criando “vazios” enormes e alturas diferentes. Em mobile, o texto estoura para fora.

## Causa comum
- `justify-between` em container vertical
- falta de `min-width: 0` em itens flex
- alturas fixas e imagens sem tamanho definido

## Correção (conceito)
- Trocar por layout com `gap` e alinhamento consistente
- Remover alturas fixas, usar `aspect-ratio`/dimensões explícitas
- Garantir quebra de texto com `min-width: 0` e `overflow-wrap`

## Resultado esperado
- Cards com alturas previsíveis
- Conteúdo com quebra correta
- Sem overflow horizontal e com responsividade suave

