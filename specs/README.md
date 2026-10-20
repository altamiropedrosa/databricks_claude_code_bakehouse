# Especificações

Funcionalidades novas começam por uma especificação, revisada e aprovada **antes** do código
(Spec-Driven Development). A implementação referencia a spec, e os testes nascem dos critérios de aceite.

## Fluxo

1. **Proposta:** a spec é escrita em `specs/NNN-nome.md` com status *Proposta* e aberta num pull request
   próprio, sem código.
2. **Revisão:** as questões em aberto são respondidas no PR e registradas na spec como decisões. Com elas,
   o status vira *Aprovada*, e o merge do PR marca a aprovação.
3. **Implementação:** em outro PR, que cita a spec. Cada critério de aceite vira teste automatizado ou
   verificação registrada.
4. **Entrega:** a seção *Resultado* da spec é preenchida com o que foi medido, e o status vira *Entregue*.

Mudar o que foi aprovado exige atualizar a spec no mesmo PR da mudança.

## Índice

| Nº | Spec | Status |
|---|---|---|
| 000 | [Pipeline medalhão e dashboard](000-pipeline-medalhao.md) | Entregue |
| 001 | [Opiniões por produto nas avaliações](001-opinioes-por-produto.md) | Entregue |
| 002 | [Servidor MCP da camada governada](002-servidor-mcp.md) | Entregue |
