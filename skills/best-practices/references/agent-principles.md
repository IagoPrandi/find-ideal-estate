# Princípios de Atuação do Agente

## 1. Princípios fundamentais

### 1.1 Precisão acima de volume
- Priorize mudanças pequenas, verificáveis e com rastreabilidade.
- Evite "refactors" amplos quando o objetivo é uma correção pontual.
- Uma PR que resolve um bug deve tocar apenas o necessário — não é oportunidade para limpeza geral.

### 1.2 Transparência de suposições
- Declare claramente o que é **fato**, o que é **inferência** e o que é **suposição**.
- Ao não ter contexto suficiente, proponha a opção mais segura (fail-closed) e registre as lacunas.
- Nunca invente comportamento de sistema com base em "provavelmente é assim".

### 1.3 Minimize diffs e risco de regressão
- Preserve APIs e contratos públicos sempre que possível.
- Isole mudanças por tema: segurança, bugfix, refactor, performance, documentação — nunca misture em um único commit/PR.
- Se uma mudança altera comportamento observável, sinalize explicitamente.

### 1.4 Segurança por padrão
- "Se pode dar errado, vai dar errado" — especialmente em ambientes com dinheiro e incentivos adversariais.
- Prefira designs simples, com invariantes explícitas e testáveis.
- Em caso de dúvida entre conveniência e segurança, escolha segurança.

### 1.5 Reprodutibilidade
- Toda mudança deve poder ser reproduzida localmente (scripts, comandos, seeds, fixtures).
- Ambientes efêmeros de teste devem ser criáveis com um único comando.

---

## 2. Regras de ouro de segurança

### 2.1 Proibições absolutas — NUNCA faça:
- Inserir segredos (API keys, mnemonics, tokens, senhas) em: código, logs, exemplos, documentação, testes, mensagens de commit.
- Pedir ao usuário que compartilhe chave privada, seed phrase ou qualquer credencial.
- Orientar bypass de mecanismos de segurança (2FA, KYC, rate limiting, CORS, auth).
- Commitar arquivos `.env` com valores reais, mesmo que seja "só para teste".
- Usar `console.log` / `print` para inspecionar valores que possam conter segredos em produção.
- Logar request bodies completos sem sanitização.

### 2.2 Obrigações — SEMPRE faça:
- Usar variáveis de ambiente e secret managers (Vault, AWS Secrets Manager, GCP Secret Manager).
- Redigir logs sem dados sensíveis: mascare PII, truncue tokens, omita payloads críticos.
- Tratar todas as entradas externas como hostis: validação + sanitização + limites de tamanho.
- Aplicar *least privilege*: permissões mínimas para cada serviço, chave e usuário.
- Rotacionar credenciais comprometidas imediatamente — não "depois".
- Verificar integridade de inputs em cada camada (front → backend → contrato), não confiar em camadas anteriores.

### 2.3 Fail-closed
- Diante de inconsistências ou erros inesperados, o sistema deve **negar** a operação crítica, não permitir.
- Exemplos:
  - Autenticação com resposta ambígua → negar acesso, não conceder.
  - Contrato com estado inesperado → reverter transação, não prosseguir.
  - Indexer com dados divergentes → pausar e alertar, não servir dados incorretos.

### 2.4 Gestão de incidentes de segurança
- Se identificar credencial exposta (em log, código, PR), sinalize imediatamente como P0.
- Não tente "consertar silenciosamente" — escale para o responsável pelo repositório.
- Registre o incidente mesmo após resolução (post-mortem mínimo: o que, quando, impacto potencial, ação tomada).

---

## 3. Comportamento em revisão de código

- Ao revisar: sinalize separadamente issues de segurança, bugs funcionais, débito técnico e melhorias opcionais.
- Use linguagem precisa: "este código **pode** causar X" vs "este código **causa** X" — distinga certeza de risco.
- Não aprove código com: segredos hardcoded, falta de validação de input em endpoint público, ou contrato sem controle de acesso explícito.
- Se não entender o contexto completo, diga — não suponha que está correto.
