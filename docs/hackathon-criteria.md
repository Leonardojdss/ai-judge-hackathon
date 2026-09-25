# Critérios de avaliação do hackathon

Cada critério vale **até 10 pontos**, distribuídos em **cinco perguntas de 0 a 2 pontos**. A pontuação total máxima é de **90 pontos**.

- **2 pontos — Aderente**
- **1 ponto — Parcialmente aderente**
- **0 pontos — Não aderente**

No critério **Guardrails e segurança**, a transcrição original foi preservada: os números 1, 2 e 3 enumeram as alternativas, e a pontuação segue a escala 0/1/2 indicada ao final do critério. Na primeira pergunta desse critério, não há avaliação parcialmente aderente; portanto, a nota é 0 ou 2.

---

## 1. Arquitetura — Design e separação de responsabilidades

**Pontuação: 0 a 10**

### 1. A solução possui uma separação clara de responsabilidades entre seus componentes?

**2 — Aderente:** existem componentes/módulos distintos para responsabilidades diferentes, como frontend, backend, agentes, serviços, acesso a dados e integrações, sem concentração excessiva de responsabilidades em um único componente.  
**1 — Parcialmente aderente:** existe alguma separação, porém há componentes que concentram responsabilidades distintas ou apresentam fronteiras pouco claras.  
**0 — Não aderente:** a solução é majoritariamente monolítica ou mistura responsabilidades sem uma organização identificável.

### 2. O código apresenta organização, modularização e legibilidade adequadas?

**2 — Aderente:** o código está organizado em módulos/pacotes coerentes, com nomenclatura clara, responsabilidades identificáveis e estrutura que facilita manutenção e evolução.  
**1 — Parcialmente aderente:** existe organização, mas há inconsistências, duplicações ou módulos excessivamente grandes/difíceis de compreender.  
**0 — Não aderente:** o código apresenta baixa organização, forte acoplamento ou estrutura que dificulta significativamente sua compreensão e manutenção.

### 3. A solução apresenta baixo acoplamento entre seus principais componentes?

**2 — Aderente:** componentes possuem interfaces/fronteiras bem definidas e podem ser alterados ou substituídos com impacto limitado nos demais.  
**1 — Parcialmente aderente:** existe alguma separação, mas componentes importantes possuem dependências diretas ou conhecimento excessivo uns dos outros.  
**0 — Não aderente:** os componentes são fortemente acoplados e alterações locais tendem a exigir mudanças em várias partes da solução.

### 4. A arquitetura escolhida é coerente com o problema e com os requisitos da solução?

**2 — Aderente:** as decisões arquiteturais são compatíveis com volume de dados, usuários, integrações e complexidade do problema, sem complexidade desnecessária.  
**1 — Parcialmente aderente:** a arquitetura atende ao problema, mas apresenta decisões pouco justificadas, complexidade excessiva ou limitações relevantes.  
**0 — Não aderente:** a arquitetura é incompatível com requisitos importantes ou adiciona complexidade significativa sem necessidade.

### 5. A solução utiliza padrões de arquitetura/engenharia de forma consistente?

**2 — Aderente:** existem padrões claros e consistentes para organização, dependências, interfaces e comunicação entre componentes.  
**1 — Parcialmente aderente:** alguns padrões são utilizados, mas de maneira inconsistente ou incompleta.  
**0 — Não aderente:** não é possível identificar padrões consistentes de organização arquitetural.

**Máximo: 10 pontos**

---

## 2. Escalabilidade

**Pontuação: 0 a 10**

### 1. A solução permite aumento do volume de usuários/requisições sem reconstrução completa da arquitetura?

**2 — Aderente:** a arquitetura permite crescimento por meio de aumento ou replicação de recursos/componentes sem mudanças estruturais relevantes.  
**1 — Parcialmente aderente:** existe possibilidade de crescimento, mas determinados componentes exigiriam alterações significativas.  
**0 — Não aderente:** o crescimento exigiria reconstrução substancial da solução.

### 2. A solução permite escalar independentemente os componentes que possuem maior demanda?

**2 — Aderente:** componentes críticos podem ser dimensionados separadamente conforme carga ou necessidade.  
**1 — Parcialmente aderente:** alguns componentes podem ser escalados separadamente, mas existem dependências que limitam essa capacidade.  
**0 — Não aderente:** toda a aplicação precisa ser escalada como uma única unidade.

### 3. A solução considera crescimento do volume de dados?

**2 — Aderente:** existem estratégias identificáveis para lidar com crescimento dos dados, como paginação, processamento em lotes, filas, armazenamento adequado, cache ou mecanismos equivalentes quando aplicáveis.  
**1 — Parcialmente aderente:** existem mecanismos pontuais, mas sem tratamento consistente do crescimento.  
**0 — Não aderente:** não existe tratamento identificável para aumento significativo do volume de dados.

### 4. A solução evita gargalos evidentes de processamento?

**2 — Aderente:** operações custosas possuem estratégias adequadas, como paralelismo, processamento assíncrono, filas, cache ou controle de concorrência quando aplicáveis.  
**1 — Parcialmente aderente:** existem algumas otimizações, mas permanecem gargalos relevantes.  
**0 — Não aderente:** existem gargalos claros sem qualquer estratégia de mitigação.

### 5. Integrações e dependências externas são utilizadas de maneira compatível com aumento de escala?

**2 — Aderente:** chamadas externas possuem estratégias para concorrência, limites de requisição, processamento assíncrono ou mecanismos equivalentes quando necessários.  
**1 — Parcialmente aderente:** existe alguma preocupação com escala, porém incompleta.  
**0 — Não aderente:** dependências externas são utilizadas sem consideração identificável sobre aumento de carga.

**Máximo: 10 pontos**

---

## 3. Resiliência e disponibilidade

**Pontuação: 0 a 10**

### 1. A solução possui tratamento adequado de exceções e falhas?

**2 — Aderente:** falhas são capturadas e tratadas de forma específica, evitando interrupções desnecessárias e fornecendo comportamento controlado.  
**1 — Parcialmente aderente:** existe tratamento de exceções, mas de forma genérica ou incompleta.  
**0 — Não aderente:** falhas relevantes não possuem tratamento.

### 2. A solução implementa retry para operações sujeitas a falhas transitórias?

**2 — Aderente:** existem retries configurados de maneira controlada, preferencialmente com limite de tentativas e estratégia de espera/backoff.  
**1 — Parcialmente aderente:** existe retry, mas sem controles adequados ou aplicado apenas parcialmente.  
**0 — Não aderente:** operações sujeitas a falhas transitórias não possuem retry.

### 3. A solução utiliza timeout em chamadas externas ou operações potencialmente bloqueantes?

**2 — Aderente:** chamadas relevantes possuem timeout explicitamente configurado e tratamento para seu encerramento.  
**1 — Parcialmente aderente:** timeout existe apenas em parte das operações relevantes ou sem tratamento adequado.  
**0 — Não aderente:** chamadas externas relevantes podem aguardar indefinidamente.

### 4. A solução possui fallback ou comportamento degradado quando uma dependência fica indisponível?

**2 — Aderente:** existem estratégias explícitas de fallback, resposta controlada ou degradação funcional para dependências críticas.  
**1 — Parcialmente aderente:** existe tratamento de indisponibilidade, mas sem fallback consistente.  
**0 — Não aderente:** indisponibilidade de uma dependência crítica provoca falha não controlada da solução.

### 5. A solução considera idempotência ou prevenção de efeitos duplicados quando aplicável?

**2 — Aderente:** operações que podem ser repetidas possuem mecanismos para evitar processamento ou efeitos duplicados.  
**1 — Parcialmente aderente:** existe preocupação com duplicidade, mas sem cobertura consistente.  
**0 — Não aderente:** operações repetidas podem gerar efeitos duplicados sem qualquer controle.

**Máximo: 10 pontos**

---

## 4. Guardrails e segurança

**Pontuação: 0 a 10**

**1. O grupo fez um guardrail? Pode ser de bloqueio/liberação, ou pode ser integrado ao prompt do agente principal**
1. aderente: o grupo fez um guardrail em qualquer arquitetura. Ele deve bloquear interações maliciosas OU reescrever possíveis respostas problemáticas, servindo como proteção para o agente final.
2. parcialmente aderente: não existe parcialmente aderente para esta pergunta.
3. não aderente: o grupo não fez nenhum guardrail.

**2. O agente tem alguma proteção contra ataques comuns (prompt injection, jailbreak, coding)?**
1. aderente: o guardrail descreve especificamente tipos de ataques comuns e dá exemplos específicos ao contexto bancário
2. parcialmente aderente: o guardrail descreve os ataques comuns de forma genérica e não detalhada ou sem exemplos
3. não aderente: o guardrail não aborda nenhum tipo de ataque comum

**3. O agente tem alguma proteção contra ataques de engenharia social (persona, motivo nobre, apelo emocional)?**
1. aderente: o guardrail descreve especificamente ataques de engenharia social e dá exemplos específicos ao contexto bancário
2. parcialmente aderente: o guardrail descreve ataques de engenharia social de forma genérica e não detalhada ou sem exemplos
3. não aderente: o guardrail não aborda nenhum tipo de ataque de engenharia social

**4. O grupo tentou mitigar vieses na resposta do agente? (viés de gênero, racial, etc)**
1. aderente: o guardrail descreve especificamente os tipos de viés e dá exemplos específicos ao contexto bancário
2. parcialmente aderente: o guardrail descreve o que é viés de forma genérica ou sem exemplos
3. não aderente: o guardrail não aborda nenhum tipo de viés

**5. O grupo fez algum tratamento da resposta quando a temas sensíveis como saúde, apostas, religião e política?**
1. aderente: o guardrail descreve especificamente os tipos de dados sensíveis e dá exemplos específicos ao contexto bancário
2. parcialmente aderente: o guardrail descreve dados sensíveis de forma genérica ou sem exemplos
3. não aderente: o guardrail não aborda nenhum tipo de dado sensível

**Pontuação por pergunta:**  
0: não aderente → 1: parcialmente aderente → 2: aderente

**Máximo: 10 pontos**

---

## 5. Design da solução GenAI

**Pontuação: 0 a 10**

### 1. A abordagem de GenAI escolhida é adequada ao problema?

**2 — Aderente:** existe uma justificativa técnica coerente para uso de prompting, RAG, agentes, tools/function calling, fine-tuning ou outras abordagens utilizadas.  
**1 — Parcialmente aderente:** a abordagem funciona, mas sua escolha não está claramente justificada ou existem componentes GenAI desnecessários.  
**0 — Não aderente:** a abordagem utilizada é incompatível com o problema ou adiciona complexidade sem benefício identificável.

### 2. O modelo de IA utilizado é adequado à tarefa?

**2 — Aderente:** a escolha do modelo considera requisitos como capacidade, contexto, modalidade, latência e/ou custo.  
**1 — Parcialmente aderente:** o modelo executa a tarefa, mas não existem evidências ou justificativas claras para sua escolha.  
**0 — Não aderente:** o modelo escolhido apresenta limitações evidentes para a tarefa sem estratégia de compensação.

### 3. Os prompts/instruções dos modelos estão estruturados adequadamente?

**2 — Aderente:** prompts possuem objetivo, contexto, regras e formato de saída claramente definidos quando aplicável.  
**1 — Parcialmente aderente:** existem instruções funcionais, porém genéricas, ambíguas ou pouco estruturadas.  
**0 — Não aderente:** prompts são insuficientes ou não estabelecem adequadamente o comportamento esperado.

### 4. Quando existem agentes ou ferramentas, suas responsabilidades estão claramente definidas?

**2 — Aderente:** agentes/tools possuem responsabilidades específicas, critérios claros de utilização e fluxo coerente de execução.  
**1 — Parcialmente aderente:** existe divisão de responsabilidades, mas há sobreposição ou decisões pouco claras.  
**0 — Não aderente:** agentes/tools são utilizados sem responsabilidades ou critérios de execução identificáveis.

### 5. O fluxo GenAI possui mecanismos para controlar e validar suas saídas?

**2 — Aderente:** existem mecanismos como structured output, schemas, validações, parsers ou verificações equivalentes adequadas ao caso.  
**1 — Parcialmente aderente:** existe algum controle de saída, mas incompleto ou aplicado apenas em partes do fluxo.  
**0 — Não aderente:** a saída do modelo é utilizada diretamente sem validação quando ela seria necessária.

**Máximo: 10 pontos**

---

## 6. Qualidade e preparação dos dados

**Pontuação: 0 a 10**

### 1. As fontes de dados utilizadas são adequadas ao problema?

**2 — Aderente:** as fontes possuem relação clara com o objetivo da solução e há evidência de critérios para sua seleção.  
**1 — Parcialmente aderente:** os dados são relacionados ao problema, mas sua seleção é pouco justificada ou limitada.  
**0 — Não aderente:** as fontes não apresentam relação suficiente com o problema ou não podem ser identificadas.

### 2. Existe tratamento de qualidade e limpeza dos dados?

**2 — Aderente:** existem mecanismos para tratar dados inválidos, ausentes, duplicados, inconsistentes ou inadequados conforme o contexto.  
**1 — Parcialmente aderente:** existe limpeza básica, mas problemas relevantes permanecem sem tratamento.  
**0 — Não aderente:** os dados são utilizados sem tratamento de qualidade identificável.

### 3. A representatividade dos dados foi considerada?

**2 — Aderente:** existem verificações ou justificativas sobre cobertura, distribuição e representatividade dos dados utilizados.  
**1 — Parcialmente aderente:** existe preocupação com representatividade, porém sem análise suficiente.  
**0 — Não aderente:** não há evidência de análise sobre representatividade.

### 4. A solução considera possíveis vieses presentes nos dados?

**2 — Aderente:** possíveis vieses são identificados e existem estratégias de avaliação ou mitigação quando aplicáveis.  
**1 — Parcialmente aderente:** vieses são reconhecidos, mas não são avaliados ou tratados adequadamente.  
**0 — Não aderente:** não existe consideração identificável sobre vieses nos dados.

### 5. A solução evita data leakage ou utilização indevida de informações?

**2 — Aderente:** existem mecanismos ou decisões explícitas para impedir vazamento entre conjuntos, etapas ou informações que não deveriam estar disponíveis ao modelo.  
**1 — Parcialmente aderente:** existe preocupação, mas os controles são incompletos.  
**0 — Não aderente:** há risco evidente de leakage sem tratamento.

**Máximo: 10 pontos**

---

## 7. Métricas e avaliação

**Pontuação: 0 a 10**

### 1. A solução possui métricas objetivas para avaliar seu desempenho?

**2 — Aderente:** existem métricas claramente definidas e relacionadas ao objetivo da solução.  
**1 — Parcialmente aderente:** existem métricas, mas cobrem apenas parte do comportamento esperado.  
**0 — Não aderente:** não existem métricas objetivas de avaliação.

### 2. As métricas escolhidas são coerentes com o problema?

**2 — Aderente:** as métricas medem características relevantes da solução e sua escolha possui justificativa técnica.  
**1 — Parcialmente aderente:** as métricas possuem alguma relação com o problema, mas são insuficientes ou pouco justificadas.  
**0 — Não aderente:** as métricas utilizadas não representam adequadamente o objetivo da solução.

### 3. Existe um processo reproduzível de avaliação?

**2 — Aderente:** existem dataset/casos de teste, critérios e processo que permitem repetir a avaliação e comparar resultados.  
**1 — Parcialmente aderente:** existe avaliação, mas depende significativamente de análise manual ou não é totalmente reproduzível.  
**0 — Não aderente:** a avaliação ocorre apenas de maneira informal ou subjetiva.

### 4. Os resultados das métricas são interpretados adequadamente?

**2 — Aderente:** além dos valores, a solução apresenta análise sobre o significado dos resultados, limitações e impactos.  
**1 — Parcialmente aderente:** métricas são apresentadas com interpretação limitada.  
**0 — Não aderente:** apenas números são apresentados sem interpretação.

### 5. A avaliação considera diferentes cenários relevantes da solução?

**2 — Aderente:** são avaliados cenários normais, casos extremos, falhas ou diferentes tipos de entrada relevantes ao problema.  
**1 — Parcialmente aderente:** existem múltiplos testes, mas a cobertura de cenários é limitada.  
**0 — Não aderente:** a avaliação utiliza apenas casos básicos ou isolados.

**Máximo: 10 pontos**

---

## 8. Eficiência e custo

**Pontuação: 0 a 10**

### 1. A escolha dos modelos considera a relação entre capacidade e custo?

**2 — Aderente:** existe uma escolha consciente do modelo considerando necessidade da tarefa, custo e capacidade.  
**1 — Parcialmente aderente:** a escolha funciona, mas não há otimização ou justificativa clara de custo.  
**0 — Não aderente:** são utilizados modelos evidentemente superdimensionados ou sem qualquer consideração de custo.

### 2. A solução evita chamadas desnecessárias aos modelos ou serviços externos?

**2 — Aderente:** o fluxo minimiza chamadas redundantes e utiliza estratégias como cache, roteamento, batching ou reutilização quando aplicáveis.  
**1 — Parcialmente aderente:** existem algumas otimizações, mas ainda ocorrem chamadas evitáveis.  
**0 — Não aderente:** existem chamadas redundantes ou desnecessárias sem controle.

### 3. Existe preocupação com consumo de tokens/contexto?

**2 — Aderente:** prompts, histórico, documentos e contexto são selecionados ou reduzidos de maneira consciente.  
**1 — Parcialmente aderente:** existe alguma otimização, mas grandes volumes de contexto ainda são enviados sem necessidade.  
**0 — Não aderente:** não existe controle identificável sobre consumo de tokens/contexto.

### 4. A solução considera latência no desenho do fluxo?

**2 — Aderente:** existem mecanismos como paralelização, cache, streaming ou redução de etapas quando adequados ao caso.  
**1 — Parcialmente aderente:** existe preocupação com latência, mas com poucas otimizações concretas.  
**0 — Não aderente:** o fluxo possui etapas custosas ou sequenciais desnecessárias sem consideração de latência.

### 5. Existe uma relação coerente entre custo computacional e benefício entregue?

**2 — Aderente:** componentes e chamadas possuem finalidade clara e o custo adicional está associado a ganho funcional ou de qualidade identificável.  
**1 — Parcialmente aderente:** parte da complexidade/custo possui benefício pouco demonstrado.  
**0 — Não aderente:** há complexidade ou consumo significativo sem benefício identificável para a solução.

**Máximo: 10 pontos**

---

## 9. Inovação técnica

Aqui eu faria uma pequena adaptação em relação aos demais. **Inovação não deveria significar simplesmente usar uma tecnologia nova**, exatamente como o slide indica. O foco deve estar no **uso criativo e tecnicamente justificável**.

**Pontuação: 0 a 10**

### 1. A solução apresenta uma abordagem técnica diferenciada para resolver o problema?

**2 — Aderente:** existe uma abordagem não trivial que contribui concretamente para resolver o problema.  
**1 — Parcialmente aderente:** existe alguma diferenciação, mas seu impacto é limitado ou pouco demonstrado.  
**0 — Não aderente:** a solução utiliza apenas abordagens convencionais sem adaptação relevante ao problema.

### 2. Existe combinação criativa de tecnologias ou técnicas?

**2 — Aderente:** diferentes técnicas são combinadas de maneira coerente e essa combinação gera benefício identificável.  
**1 — Parcialmente aderente:** existe combinação de tecnologias, mas sem benefício claramente demonstrado.  
**0 — Não aderente:** não existe combinação diferenciada ou ela é puramente incidental.

### 3. A inovação apresentada possui justificativa técnica?

**2 — Aderente:** é possível identificar qual problema a abordagem diferenciada resolve e por que ela foi escolhida.  
**1 — Parcialmente aderente:** existe justificativa, porém genérica ou sem evidências.  
**0 — Não aderente:** tecnologias ou técnicas são utilizadas apenas por novidade, sem justificativa relacionada ao problema.

### 4. A inovação gera benefício mensurável ou demonstrável para a solução?

**2 — Aderente:** existe evidência de melhoria em qualidade, eficiência, experiência, custo, precisão ou outra dimensão relevante.  
**1 — Parcialmente aderente:** o benefício é plausível e demonstrado qualitativamente, mas não possui evidências suficientes.  
**0 — Não aderente:** não é possível identificar benefício concreto decorrente da inovação.

### 5. A solução possui implementação técnica própria relevante além da simples integração de componentes prontos?

**2 — Aderente:** existe desenvolvimento técnico relevante, como lógica própria, orquestração, algoritmos, mecanismos ou adaptações específicas para o problema.  
**1 — Parcialmente aderente:** existe alguma implementação própria, mas a maior parte da solução depende diretamente de componentes prontos.  
**0 — Não aderente:** a solução consiste essencialmente na conexão/configuração de ferramentas prontas sem implementação técnica relevante.

**Máximo: 10 pontos**

