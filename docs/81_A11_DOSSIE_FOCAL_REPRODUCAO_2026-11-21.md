# Stone — A11: dossiê focal de reprodução, direitos e não-aceite (21/11/2026)

**Natureza:** overlay de evidência para IMP-203/204, NÃO decisão normativa. Fonte oficial: Base Atemporal v6.1, Plano Único v5.2 e matrizes vigentes. Nenhum gate ou o aceite final IMP-131 foi liberado. PR #44 permanece Draft; teto de gastos R$0.

## 1. Corte comprovado pelo operador Windows

Os resultados abaixo pertencem exatamente ao HEAD **0b58c4d2c983b100b7d2bb8e638bbaa13b0755c0**, Conda tapi-s1-recovery:

| Verificação | Resultado observável |
|---|---|
| Python runner e CDP | 13 PASS, 0 FAIL, 0 SKIP — 1,03 s |
| Node exportação, HTML e timeline | 19 PASS, 0 FAIL, 0 SKIP — 433,985 ms |
| Chrome headless real | A073_BROWSER_PARITY_PASS 7/7 |
| Invariantes locais de gasto zero | PASS — invariantes locais de gasto zero e bloqueio externo |

No Chrome deste computador, a fixture sintética usou o exportador local real: comparação Canvas/PNG com limite médio de diferença <=2, JPEG com limite <=10, SVG renderizado com HTMLImageElement, marca de rascunho, XML escapado, versões e hashes, negação de direitos falsificados. Isso NÃO demonstra paridade interplataforma, confiança em fontes externas, direito de reutilização, autenticidade de contas, E2E do editor autenticado, mídia comercial ou publicação.

**Outro SHA e outro corte, sem somar como uma única execução:** a regressão focal A05/A06/A07 de 13 arquivos forneceu **114 PASS, 0 FAIL, 0 SKIP e um warning legado Starlette** no HEAD **96797a0d746c1bae6cd5dd917ad38e9e4cb74f71**. Ela não foi executada no mesmo SHA que os 13/19/7 acima. É preciso rerodá-la no SHA do pacote A11.

## 2. Gerador do pacote de evidências

O novo script scripts/a11_focal_evidence_packet.py é um **executor opt-in exclusivamente local**, não CI nem aprovação:

1. Confere Git HEAD completo, ausência de mudanças em arquivos rastreados e, opcionalmente, igualdade com o SHA exigido.
2. Calcula SHA-256 dos scripts, contratos e testes críticos; recusa fonte local ausente.
3. Executa PRIMEIRO scripts/verify_zero_spend.py. Se falhar, não inicia nenhum teste subsequente.
4. Executa 13 arquivos focais pytest A05/A06/A07 (114 casos no último corte, esperados), os dois arquivos CDP Python (13 esperados), três suítes Node (19 esperados) e as 7 verificações reais do Chrome. Um processo com exit 0 mas contagem parcial, skips ou DOM incompleto é rejeitado. Não baixa navegador nem bibliotecas, não usa pagamentos e não consulta serviços de terceiros.
5. Gera recibo JSON com schema tapi-a11-focal-evidence-packet.v1; inclui SHA, hash de arquivos e outputs, contagens, tempos, códigos de resultado e limitações. Não inclui os logs brutos, legendas, tokens ou imagens. O arquivo do recibo só pode ser criado: nunca sobrescreve outro.
6. Quando tudo passa, o status máximo é FOCAL_DIAGNOSTICS_VERIFIED_NO_GATE_RELEASE. O recibo SEMPRE mantém G0–G6 e IMP-131 em BLOCKED, além de production_approved=false, external_reference_rights_verified=false, science_approved=false e imp131_accepted=false.

A cobertura A00 full, a validação multimodal Strict, o gold independente, os CT-STUDIO completos, IMP-131 e os direitos externos operacionais **não** são verificados pelo pacote. Um recibo verde não se transfere para outro SHA. O Git check detecta arquivos rastreados modificados, mas não substitui uma revisão de todas as dependências e arquivos não rastreados de um ambiente comprometido.

### Reprodução PowerShell

No checkout limpo da branch Draft:

1. Capturar o SHA com git rev-parse HEAD e verificar git status --short.
2. Executar python -m pytest -q -rs tests/test_a11_focal_evidence_packet.py (esperados **10 casos**, ainda não executados no Windows).
3. Executar o pacote com os argumentos --expected-head SHA e --output artifacts/a11/focal-SHA.json (SHA deve ser o HEAD completo do checkout, não um SHA histórico).
4. Verificar SHA-256 do JSON com Get-FileHash -Algorithm SHA256. Conservar o recibo sem sobrescrever. Se a execução falhar, o recibo continua BLOCKED e contém os motivos e outputs apenas por hash.

Exemplo de execução:

    $head = (git rev-parse HEAD).Trim()
    git status --short
    python -m pytest -q -rs tests/test_a11_focal_evidence_packet.py
    if ($LASTEXITCODE -ne 0) { throw "A11 tests falharam" }
    $output = "artifacts/a11/focal-$head.json"
    python scripts/a11_focal_evidence_packet.py --expected-head $head --output $output
    if ($LASTEXITCODE -ne 0) { throw "A11 focal ainda nao validado" }
    Get-FileHash -Algorithm SHA256 $output

**Os 10 testes A11 e os 5 comandos do pacote são novos e AINDA NÃO têm PASS do operador no HEAD atual.** As contagens 114/13/19/7 são oráculos focais baseados em resultados históricos, não resultados desse novo SHA nem substitutos para CT-STUDIO e A00.

## 3. Matriz de bloqueios preservados

| Gate vigente | Evidência local que já existe | Lacuna impeditiva e estado |
|---|---|---|
| G0-PERMISSIONS | Bloqueios de operação externa, contratos técnicos e de referência | Direitos de reutilização por origem/operação com autoridade efetiva, prazo e revogação verificados; **BLOCKED** |
| G1-CONTRACT | Schemas Studio, CreativeSpec, Ed25519 local e testes | Contratos operacionais completos, oráculos normativos e PEP por ação; **BLOCKED** |
| G2-REPRODUCIBILITY | HEAD, SHA, testes e pipeline focal local | A00 full no mesmo HEAD, ambiente/perfis e reprodução multimodal Strict; **BLOCKED** |
| G3-EVAL | Snapshot sintético, avaliação/retrieval local, abstenção | Gold independente, amostra elegível, CT-04 e validade de inferências; **BLOCKED** |
| G4-SECURITY | Tenant/RBAC/revogação sintéticos, deny por fonte e XSS/SVG | Segurança E2E dos pontos de uso, evidência externa e validação independente; **BLOCKED** |
| G5-OPS | Gasto zero e ausência de operação externa por padrão | Observabilidade e controles operacionais completos, direitos e revogação reais; **BLOCKED** |
| G6-ISO | Logs e documentação rastreável por SHA | Rastreabilidade integral, qualidade/ISO e revisão admissível por oráculos; **BLOCKED** |

A tabela não substitui os CSV normativos da Base Atemporal; IMP-131 continua único sink e requer provas admissíveis de todos os gates. A regra DEC-018 de dispensa da revisão humana para IMP-062/CAP-004 permanece **dispensada, não cumprida**, e não concede direitos criativos.

## 4. Fronteiras do próximo incremento

- Executar e guardar um pacote A11 focal no novo HEAD. Investigar, não ajustar artificialmente, qualquer contagem ou comportamento divergente.
- Executar A00 full separadamente no HEAD consolidado. Os 2 FAIL Strict historicamente conhecidos não devem ser apagados por skip ou troca de limiar.
- Conferir os CT-STUDIO 01–10 e oráculos da matriz antes de quaisquer promessas de aprovação, integração de direitos em runtime, merge/deploy ou publicação.
- Não executar serviços externos, mídia sem licença, ASR repetitivo, FFmpeg worker produtivo ou chamadas pagas para demonstrar um resultado sintético.
