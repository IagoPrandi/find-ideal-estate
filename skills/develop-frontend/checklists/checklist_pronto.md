# Checklist de qualidade — Frontend gerado por IA

## Visual
- [ ] Não há overflow horizontal (exceto carrossel intencional)
- [ ] Espaçamentos seguem escala (ex.: 4/8/12/16/24/32)
- [ ] Alinhamentos consistentes (grid/baseline)
- [ ] Tipografia consistente (escala de títulos + line-height)
- [ ] Contraste adequado em texto/ícones/bordas/estados

## Responsividade
- [ ] 320–360px ok
- [ ] 390–430px ok
- [ ] 768px ok
- [ ] 1024px ok
- [ ] 1440px ok
- [ ] Modais e menus cabem na viewport

## Acessibilidade
- [ ] Elementos clicáveis são `button`/`a`
- [ ] Foco visível e tab order correto
- [ ] Inputs com label e mensagens de erro associadas
- [ ] Componentes têm nome acessível (aria-label quando necessário)

## Estados de UI
- [ ] Loading
- [ ] Empty
- [ ] Error
- [ ] Success
- [ ] Disabled

## Código
- [ ] Sem classes contraditórias / valores mágicos (`mt-[13px]` etc.)
- [ ] Sem duplicação grosseira de componentes
- [ ] Sem imports/bibliotecas “inventadas”
- [ ] Componentes com responsabilidade clara (não gigantes)

