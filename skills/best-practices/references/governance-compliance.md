# Governança, Compliance e Privacidade

## 1. Architecture Decision Records (ADR)

### 1.1 O que é e quando usar
- ADR documenta decisões arquiteturais significativas: o contexto, as opções consideradas, a decisão e as consequências.
- Escreva um ADR para: escolha de tecnologia, padrão de design importante, mudança de abordagem, trade-off relevante.
- Não escreva ADR para: decisões reversíveis triviais, convenções de código (essas ficam no styleguide).

### 1.2 Template de ADR
```markdown
# ADR-XXX: [Título curto e descritivo]

**Data**: YYYY-MM-DD  
**Status**: [Proposta | Aceita | Depreciada | Substituída por ADR-YYY]  
**Autores**: [nomes]

## Contexto
O que motivou esta decisão? Qual problema estamos resolvendo?

## Opções consideradas
1. **Opção A**: descrição + prós e contras
2. **Opção B**: descrição + prós e contras
3. **Opção C**: descrição + prós e contras

## Decisão
Qual opção foi escolhida e por quê.

## Consequências
- O que fica mais fácil com esta decisão?
- O que fica mais difícil ou mais caro?
- Quais riscos foram aceitos?

## Revisão
Quando esta decisão deve ser revisada? (ex: após X usuários, após Y meses, se Z acontecer)
```

### 1.3 Boas práticas de ADR
- Guarde ADRs no repositório junto ao código (`docs/adr/`).
- Numere sequencialmente — nunca renumere ou delete.
- ADRs obsoletas: marque como "Depreciada" ou "Substituída", não delete.
- Reescritas totais de sistema exigem ADR específico justificando a inviabilidade do incremental.

---

## 2. Gestão de papéis administrativos

### 2.1 Documentação obrigatória
Para cada papel administrativo (on-chain e off-chain), documente:
- Quem tem acesso (pessoas e sistemas).
- O que pode fazer com esse acesso.
- Qual o processo para exercer esse acesso (aprovações necessárias).
- Como revogar o acesso.
- Quando foi o último uso e para quê.

### 2.2 Multisig para operações críticas on-chain
- Toda operação administrativa em contrato de produção deve exigir multisig (ex.: Gnosis Safe).
- Defina: quórum mínimo, lista de signatários, processo para mudança de signatários.
- Timelock para upgrades e operações de alto impacto — dê aos usuários tempo para reagir.
- Teste o processo de multisig em staging antes de precisar em produção.

### 2.3 Rotação de credenciais
- Defina política de rotação: API keys a cada 90 dias, chaves de deploy após uso significativo.
- Processo documentado para rotação de emergência (credencial comprometida).
- Nunca compartilhe credenciais entre ambientes.

---

## 3. Privacidade e proteção de dados

### 3.1 Princípios básicos
- Colete apenas dados necessários para a operação — "just in case" não é justificativa.
- Defina retenção para cada tipo de dado e implemente a deleção.
- Separe dados de produção de dados de desenvolvimento e análise.

### 3.2 PII (Personally Identifiable Information)
- Identifique quais dados são PII no seu sistema: email, endereço físico, documentos, IP, etc.
- Endereços de carteira on-chain: são pseudônimos, não anônimos — trate com cuidado.
- Logs: nunca logue PII sem necessidade operacional clara.
- Analytics: anonimize ou pseudonimize antes de usar em análises.

### 3.3 On-chain e privacidade
- Dados na blockchain são públicos e permanentes — nunca coloque PII on-chain.
- Mesmo dados "criptografados" on-chain podem ser revelados se a chave vazar.
- Para dados privados: armazene off-chain, mantenha apenas hash ou commitments on-chain.

---

## 4. Licenças de código

### 4.1 Verificação de dependências
- Antes de adicionar dependência, verifique a licença.
- Licenças permissivas (MIT, Apache 2.0, BSD): geralmente OK para uso comercial.
- Licenças copyleft (GPL, AGPL): podem exigir open-source do seu código — consulte jurídico.
- Licenças comerciais: verifique termos de redistribuição e uso em produto.

### 4.2 Licença do próprio projeto
- Defina explicitamente a licença do projeto no `LICENSE` file.
- Para contratos com componentes OpenZeppelin: respeite a licença deles (MIT para a maioria).
- Documente qualquer exceção de licença no header dos arquivos relevantes.

---

## 5. Compliance e auditoria

### 5.1 Trilha de auditoria
- Mantenha log imutável de operações críticas: quem fez, quando, o quê, resultado.
- Inclua: mudanças de permissão, operações financeiras, acesso a dados sensíveis, deploys.
- Retenção mínima: 1 ano para operações financeiras, conforme regulamentação aplicável.

### 5.2 Auditoria de contratos
- Contratos com valor significativo em risco devem passar por auditoria externa antes do mainnet.
- Escopo mínimo de auditoria: lógica de negócio, controle de acesso, segurança de funds, integração com dependências.
- Após auditoria: documente os findings, as correções aplicadas, e os findings aceitos com justificativa.
- Publique o relatório de auditoria — transparência constrói confiança.
