# A11 — pré-liberação verificável e conservadora

> Registro operacional do incremento sobre a Base Atemporal v6.1. Não altera as 204 IMP, as 23 CAP, as 543 dependências nem as decisões normativas. **Não é autorização de produção.**

## Propósito

`scripts/a11_release_gate_preflight.py` complementa, sem substituir, `scripts/a11_focal_evidence_packet.py`. O primeiro lê recibos explícitos e valida integridade, escopo, autoridade e validade temporal; o segundo executa diagnósticos focais. Nem um nem outro concede direitos, cria gold científico, aciona publicação ou dispensa os critérios do aceite IMP-131.

O pré-verificador é **offline e read-only**. Nunca executa deploy, migrations, GitHub Actions, requests, aquisição, mídia, assinaturas ou provisionamento. Não produz artefatos que afirmem liberação de G0–G6.

## Operação

1. Validar e congelar o SHA exato do código candidato; executar as regressões integrais e os oráculos independentes do Plano Único, sem transferir PASS de outro SHA.
2. As autoridades reais devem provisionar os respectivos recibos e uma âncora de confiança **fora do repositório**, sem inserir chaves privadas no GitHub. Não usar as chaves efêmeras dos testes como prova real.
3. Cada recibo `evidence/gates/<GATE>.json` vincula `subject`, `status=PASS`, `git_head`, `evidence_path`, `evidence_sha256`, `evaluated_at`, `expires_at`, `signer_id` e `signature_b64`. A assinatura Ed25519 cobre o JSON canônico, sem o campo da assinatura. Os arquivos de prova vivem sob `evidence/gates/proofs/`; o caminho é confinado a essa árvore e o hash é verificado.
4. A autoridade de `IMP-131` deve ser diferente das autoridades dos gates e o arquivo de prova deve conter `gate_receipt_sha256` com os digests exatos dos sete recibos; também deve identificar o SHA candidato.
5. Executar o comando somente em checkout limpo, usando o trust bundle externo. O retorno do CLI **é sempre não zero**: sua saída jamais deve ser usada como sinal de deploy em pipelines.

```powershell
python -m pytest -q tests/test_a11_release_gate_preflight.py
git rev-parse HEAD
python -m scripts.a11_release_gate_preflight --expected-head <SHA-EXATO> --trust-bundle C:\Secure\stone\trust-anchors.json
```

O caminho `C:\Secure\stone\trust-anchors.json` é **exemplo**, não declara que o arquivo existe nem instrui a criar uma autoridade fictícia. A chave pública do trust bundle precisa de proveniência independente e política de rotação/segregação. O preflight rejeita bundles cujo caminho está dentro do checkout.

## Estados interpretáveis

- `NO_GO`: faltam evidências, validações, assinatura válida, prova imutável, SHA limpo, ou a base normativa está inconsistente.
- `SIGNED_RECEIPTS_COMPLETE_HUMAN_REVIEW_REQUIRED`: apenas integridade e vinculação dos recibos verificadas no escopo definido; **não significa** conformidade jurídica, qualidade científica, autorização de publicação, aprovação global ou deploy.
- `deploy_authorized`: sempre `false`. O código de saída é sempre `2`, inclusive no caso de recibos completos.

## Testes e limitações

`tests/test_a11_release_gate_preflight.py` usa exclusivamente chaves e provas **sintéticas descartáveis**. Verifica funcionamento criptográfico e negativas (prova alterada, assinatura com chave incorreta, SHA divergente, gate ausente, expiração, path traversal, bundle inadequado, aceite IMP-131 com hashes errados, alteração do checkout e inventário normativo incompleto).

A execução isolada desse arquivo foi **13 PASS** no ambiente de trabalho da análise, mas **ainda não foi feita a regressão A00/A11 no checkout integral do novo SHA**; os resultados do Windows anteriormente documentados não são atribuídos a essa mudança. Permissões efetivas, admissões científicas, avaliação independente, operação contínua, zero-spend e produção seguem dependentes de comprovação atual e dos gates correspondentes.
