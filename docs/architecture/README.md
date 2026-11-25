# Mapa de arquitetura — roteiro arc42/C4

Visão de navegação da arquitetura pretendida, sem declaração de implementação. Fonte: [arquitetura unificada v6.1](../base_atemporal/07_Arquitetura_Unificada_Atemporal.md), [documento mestre](../base_atemporal/01_Documento_Mestre_Atemporal.md), referências integrais incorporadas e [matriz CAP](../../planning/base_atemporal/MATRIZ_CAPACIDADES.csv).

| Perspectiva arc42 | Fonte |
|---|---|
| Objetivos, escopo, restrições | Documento mestre, DEC-018, R$0 |
| Contexto/estratégia | Arquitetura unificada, contexto editorial |
| Blocos e runtime | Arquitetura unificada e System One |
| Implantação | Arquitetura, benchmark e DEC em aberto; não afirmar stack homologada |
| Conceitos transversais | Direitos, segurança, metodologia, contratos |
| Decisões | Matriz DEC e registro |
| Qualidade e riscos | U, CAP, ISO, CT, lacunas e gates do Plano Único |
| Glossário | Documento mestre e metodologia; normalização semântica integral pendente |

## C4 — contexto conceitual (alvo, não runtime observado)

```mermaid
flowchart LR
    U[Operador autorizado] --> S[TAPI Stone]
    F[Fontes com direitos efetivos] --> S
    S --> E[Análise e evidência]
    S --> C[Propostas e Studio editável]
    S -. controles por operação .-> X[Serviços externos condicionados]
```

## Fluxo lógico da jornada

```mermaid
flowchart LR
    A[Aquisição autorizada] --> B[Direitos e elegibilidade]
    B --> C[Evidência multimodal e rubrica]
    C --> D[Análise e retrieval]
    D --> E[Agente com controle de autoridade]
    E --> F[CreativeSpec e Studio]
    F --> G[Verificação e homologação integral]
```

Os blocos são conceitos da jornada, não serviços implantados nem lista de novos componentes. Diagramas C4 de containers/componentes e runtime efetivo devem ser vinculados a versões e validados contra código; não completar por suposição. Nenhum diagrama substitui a especificação de arquitetura original.
