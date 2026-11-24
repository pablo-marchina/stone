# Demonstração — pares editoriais exploratórios condicionados aos agregados

Base PR #89: 599d5252676e047d764fbcbf5e8299c185783fc0.

## Entrega
O launcher isolado expõe prévias de pares A/B para hipóteses textuais suportadas (tema e CTA), usando exclusivamente o relatório histórico projetado e templates autorais determinísticos. Controle: alternativa suportada mais frequente entre os demais posts, sem inferência causal. CTA: somente o texto do CTA muda. Tema: título e corpo mudam, formato, layout e CTA permanecem iguais. Formato continua plano de teste; não simular equivalência reels/carrossel. Não combinar fatores marginais. Não existe teste de eficácia realizado ou publicação autorizada.
As duas variantes são documentos Studio editáveis. Seleção exige hash da prévia recalculada, sessão admin/editor e loopback. Criação das duas versões iniciais e evento/outbox atômicos, com relatório SHA-256, hipótese, controle, identificação do par e hashes iniciais. Nenhuma referência externa individual ou texto de fonte é copiado. O editor recupera a versão atual, permite edição e exportação normal. O evento preserva as versões iniciais mesmo após edição, sem alegar controle experimental após mudança. Painel e HTML contam pares persistidos separadamente.

## Evidência
58 pytest PASS em 18,90 s; 10 focais PASS em 2,44 s (sobreposição). Testes incluem autenticação, prévia inválida, payload extra, igualdade prévia/documento, CTA único, persistência/evento/outbox, patch v2 e rollback se a segunda criação falhar. Chromium com ponte FastAPI em processo PASS: jornada anterior com MP4 e novo par CTA em fixture rotulada, export PNG A/B, download da proveniência e edição da variante B, sete versões totais. Primeira tentativa do ensaio falhou por seletor ambíguo, corrigido. Node syntax e zero-spend PASS. Seis blobs de código/teste correspondem aos arquivos testados.
Aplicação separada do gerador aos agregados anônimos fornecidos pelo operador (report SHA-256 befb7dc794f34a86612d14d58f87dac21a46da5fd1776d19815924e0b500b9c7) produziu dois pares: atendimento × marketing e comentar × seguir, quatro documentos de prévia. Não foi importado o arquivo privado original nesta sessão nem executado experimento real. PR #88 já confirmada pelo operador em Windows com relatório histórico e HTTP real. PR atual requer ensaio local do novo fluxo.

## Executar
Atualize a branch, mantenha PYTHONPATH=src e use os mesmos argumentos --video --av-report e --technical-report com os caminhos já validados. No painel Pesquisa, localize Da hipótese ao criativo: teste A/B, selecione Persistir variantes A/B e abra a variante A ou B. Exporte os PNGs e proveniência antes de desligar o banco temporário.

R$0, sem nova coleta, deploy público, merge, aceite científico ou promoção de gates.
