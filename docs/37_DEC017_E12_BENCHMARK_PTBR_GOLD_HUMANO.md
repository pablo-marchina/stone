# DEC-017 E1.2 — Benchmark português e gold humano independente

**Estado:** infraestrutura experimental; não homologação de qualidade científica. O E1.1 já executou pesos reais do GLiNER2.5 em CPU, mas apenas em quatro casos artificiais.

## Hipótese e desenho

Comparar o baseline determinístico do TAPI com o GLiNER2.5-multi-Decide local, sob o **mesmo texto observado**, as mesmas sete perguntas E1 e as mesmas referências. E1.2 só analisa legenda/transcrição; **não observa** áudio, frames, cortes ou primeiros 3 segundos de vídeo.

São avaliados tema_principal, tom, tipo_hook, tem_cta, tipo_cta, oferta_ou_beneficio_explicito e mpe_targeted. Os seis primeiros são parte ou candidatos do subconjunto de texto dos 20 campos oficiais; mpe_targeted é um atributo experimental adicional, por publicação, e não supõe que o produtor seja uma empresa MPE.

- tipo_hook **sempre não observável** na avaliação apenas textual;
- sem CTA ou benefício na legenda **não significa** ausência no vídeo;
- o modelo pode abster-se sem imputar falso;
- classificações e gold usam a mesma evidência e localizador, verificável por SHA-256;
- nenhuma saída altera corpus_post_scientific_reviews ou contagens de elegibilidade científica.

## Componentes

| Artefato | Função |
|---|---|
| src/tapi_gate0/system_one_e12.py | Contratos ReferenceLabel, HumanReview, E12Case; resolução independente e avaliação por campo |
| scripts/build_e12_ptbr_smoke.py | Gerar 14 textos artificiais em português, contendo classes e casos ambíguos |
| scripts/benchmark_system_one_e12.py | Comparação pareada baseline / GLiNER local; somente relatório agregado |
| scripts/assemble_e12_human_gold.py | Montar referências reais duplamente revisadas, com adjudicação por terceiro e proteção de privacidade |
| tests/test_system_one_e12.py | Testes de contrato, baseline, métricas, abstenção, vazamento e CLI |
| tests/test_system_one_e12_assembly.py | Testes da montagem de revisões e proteção dos arquivos |
 
## Passo 1 — Sintéticos em português, sem downloads

Os 14 exemplos são inventados e não usam posts de redes sociais. Exercitam categorias de marketing, vendas, finanças, atendimento, gestão, maquininha, trajetória empreendedora e motivação; também ambiguidades, ausência de tópico e negação de CTA.

~~~powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_system_one_e12.py tests/test_system_one_e12_assembly.py
python scripts/build_e12_ptbr_smoke.py --output dec017_e12_ptbr_synthetic.jsonl
python scripts/benchmark_system_one_e12.py --input dec017_e12_ptbr_synthetic.jsonl --output dec017_e12_baseline_report.json --model baseline
~~~

Opcionalmente, comparar com o GLiNER **já baixado e íntegro na etapa E1.1**, sem nova transferência:

~~~powershell
$env:TAPI_SYSTEM_ONE_ENABLED = "1"
try {
    python scripts/benchmark_system_one_e12.py --input dec017_e12_ptbr_synthetic.jsonl --output dec017_e12_both_report.json --model both --model-dir "C:\Models\tapi\gliner25-multi-decide"
}
finally {
    $env:TAPI_SYSTEM_ONE_ENABLED = "0"
}
~~~

O runner confere o manifesto SHA-pinned do E1.1, verifica o hash do checkpoint antes de usá-lo, impõe execução offline e calcula todas as métricas sobre os mesmos exemplos. Não imprime as legendas.

**Os resultados sintéticos NÃO são estimativas válidas de desempenho em publicações reais.** Mesmo que um modelo apresente F1 maior, nenhum vencedor pode ser declarado nesta fase.

## Passo 2 — Gold humano real, privado e independente

A formação do gold set depende de permissão institucional, termos de plataformas e comprovação do direito de processar **a legenda ou transcrição efetivamente observada**. A autorização de metadados obtida via Business Discovery **não** autoriza copiar, transcrever ou classificar o vídeo de terceiros. Gate 0B permanece bloqueado até autorização efetiva.

Cada registro é EvidenceBundle com origem approved_local, referência documental, escopo offline_classification, tenant, criador, postagem e texto (caption/transcript) com hash e localizador. Campos declarados pelo operador **não provam juridicamente** direitos de uso: conservar evidências externas de autorização.

### Revisão independente

Dois revisores distintos anotam os **sete campos**, cegos para as predições dos modelos. Para cada campo, registram status observed/not_observable/not_applicable, rótulo somente quando observado, justificativa e localizador igual ao texto. HumanReview exige ID do revisor, timestamp com fuso e o fingerprint do EvidenceBundle.

Divergências entre os dois revisores quanto a status, rótulo ou evidência exigem um **terceiro revisor independente** para o campo divergente. Sem adjudicação a montagem falha. O programa impede dois IDs iguais, mas não verifica identidades humanas; uma equipe responsável deverá registrar assinaturas ou outros meios de autoria e independência.

Separar a amostra por **criador**, não por publicação, e congelar os conjuntos dev/test antes de ajustar rótulos, regras, prompts ou limiares. O software rejeita autores iguais e textos exatamente duplicados entre os conjuntos. Clones/paráfrases e campanhas relacionadas ainda exigem revisão manual. A meta mínima institucional de 50 revisões é ponto de partida, não garantia de potência estatística nem cobertura por classe.

### Arquivos privados

Todos os arquivos abaixo devem ficar **fora do checkout Git**, por exemplo em C:\TAPI-Private\E12:

- evidence.jsonl: cada linha um EvidenceBundle com texto autorizado e hash verificado;
- splits.jsonl: uma linha SplitAssignment (evidence_fingerprint, split dev/test e gold_reference) por publicação;
- review_a.jsonl e review_b.jsonl: cada linha HumanReview com 7 ReferenceLabels e fingerprint;
- adjudication.jsonl: opcional, apenas publicações com discordância e terceiro revisor único;
- gold_e12_v1.jsonl: resultado congelado, escrito sem sobrescrever o anterior.

Montagem, após as duas revisões independentes e os direitos verificados:

~~~powershell
python scripts/assemble_e12_human_gold.py --evidence "C:\TAPI-Private\E12\evidence.jsonl" --splits "C:\TAPI-Private\E12\splits.jsonl" --review-a "C:\TAPI-Private\E12\review_a.jsonl" --review-b "C:\TAPI-Private\E12\review_b.jsonl" --adjudication "C:\TAPI-Private\E12\adjudication.jsonl" --output "C:\TAPI-Private\E12\gold_e12_v1.jsonl"
~~~

Se não houver divergências, omitir --adjudication. Não versionar arquivos com texto real ou identificação de revisores.

Benchmark privado, apenas depois da montagem. Quando houver dev e test no mesmo arquivo, selecionar explicitamente apenas um split para evitar contaminação de métricas:

~~~powershell
$env:TAPI_SYSTEM_ONE_ENABLED = "1"
try {
    python scripts/benchmark_system_one_e12.py --input "C:\TAPI-Private\E12\gold_e12_v1.jsonl" --output "C:\TAPI-Private\E12\report_e12_test_v1.json" --model both --split test --model-dir "C:\Models\tapi\gliner25-multi-decide"
}
finally {
    $env:TAPI_SYSTEM_ONE_ENABLED = "0"
}
~~~

Métricas agregadas com poucos casos ou categorias raras também podem revelar informações; o relatório real deve permanecer privado e sujeito às políticas de divulgação.

## Métricas e limites

Para cada campo e classe presente no gold: suporte, precisão, recall, F1, macro-F1 que penaliza abstenções, cobertura, acurácia geral e apenas nas respostas; número de declarações em campos sem evidência humana; latências p50/p95 por modelo. São reportados acordo bruto entre revisores e total de arbitragens. Suporte zero produz null, nunca desempenho fictício.

O relatório preserva **scientifically_validated=false** inclusive com revisões declaradas: nem identidade dos anotadores nem direitos podem ser comprovados somente pelos campos JSON. O próximo gate científico depende de gold independente congelado, critérios institucionais e avaliação representativa.

## Critérios de aceite do PR

- Testes dos contratos, abstenção, adjudicação, controles por criador/texto e privacidade passam;
- baseline e CLI sintético PT-BR executam sem rede; GLiNER real é opt-in e usa checkpoint já validado;
- suíte geral, check_gate0 e verify_zero_spend passam;
- nenhuma alteração em domain.py, motor oficial de ingestão, Gate 0B, ciência do corpus ou agente principal.

**Fundamentação:** Metodologia Científica v2, Plano Único v5.2, DEC-016 e DEC-017 E1/E1.1. Evidência textual não equivale à observação do vídeo completo.
