# DEC-017 E1.1 — Validar GLiNER2.5-multi-Decide com pesos reais

**Estado:** protocolo implementado; checkpoint e inferência reais **ainda não executados** neste ambiente devido à indisponibilidade da hospedagem dos pesos.

**Modelo oficial:** https://huggingface.co/fastino/GLiNER2.5-multi-Decide  
**Licença declarada:** Apache-2.0. **Parâmetros:** 287M. **Arquitetura:** boundary, mDeBERTa-v3-base. **Pesos originais:** cerca de 1,15 GB em Safetensors.  
**Contexto:** experimento E1.1 complementa o E1 integrado por PR #24, sem modificar a classificação de produção, coleta, direitos, rubrica, agente ou data card.

## O que a validação faz

1. Um comando separado adquire voluntariamente o checkpoint público do Hugging Face e resolve um SHA imutável. **Este é o único comando com acesso à rede.**
2. O checkpoint fica fora do Git; calcula SHA-256 de cada arquivo essencial e registra revisão/atestado local.
3. Um segundo comando roda **sem rede**, verifica configuração e pesos, carrega via gliner2.AutoExtractor, executa classify_text real e classifica somente quatro textos sintéticos do E1.
4. Compara com o baseline determinístico; registra latência de carregamento, inferência p50/p95, RSS de memória, versão de PyTorch/GLiNER2, hash dos pesos e contagem de abstenções.
5. Nunca imprime texto de entrada, não emite dados ao fornecedor e nunca cria revisão científica automática.

## Windows/Miniforge — instalação recomendada

GLiNER2 2.1.0 foi testado oficialmente em Python 3.10–3.12; usar um ambiente Python 3.11 isolado sem modificar o base. Reservar pelo menos 3 GB livres de armazenamento. CPU deve ser possível; velocidade e memória serão medidas.

~~~powershell
git switch main
git pull --ff-only origin main
git fetch origin
git switch --track origin/feat/dec017-e11-real-gliner-local-validation-20261104

conda create -n tapi-s1 python=3.11 -y
conda activate tapi-s1
python -m pip install -e ".[dev,system_one_local]"
python -m pytest -q tests/test_gliner25_real_validation.py tests/test_system_one_e1.py
~~~

## Recuperação de erro por falta de espaço (Windows / Miniforge)

Se a aquisição reportar `CHECKPOINT_DISK_SPACE_INSUFFICIENT`, **não execute** a validação ainda. O checkpoint não foi baixado e a etapa de inferência devolverá `LOCAL_CHECKPOINT_NOT_FOUND`, uma consequência, não uma segunda falha do modelo.

Para verificar o espaço nas unidades disponíveis:

~~~powershell
Get-PSDrive -PSProvider FileSystem |
  Select-Object Name,
    @{Name="LivreGB";Expression={[math]::Round($_.Free / 1GB, 2)}},
    @{Name="UsadoGB";Expression={[math]::Round($_.Used / 1GB, 2)}}
~~~

A verificação de segurança exige **3 bilhões de bytes livres** (aproximadamente 2,79 GiB); idealmente deixar 4–5 GB de margem. Se C: estiver cheio, prefira outra unidade autorizada com espaço, como D:. A partir deste PR, a checagem busca o ancestral existente do diretório informado e consulta o **volume real de destino**, mesmo quando as subpastas ainda não existem. O erro informa a unidade, espaço disponível e exigido. Não remova a margem apenas para contornar o bloqueio.

Exemplo com D: (somente se existir e apresentar espaço suficiente):

~~~powershell
python scripts/prepare_gliner25_local_checkpoint.py --model-dir "D:\Models\tapi\gliner25-multi-decide" --confirm-public-download
$env:TAPI_SYSTEM_ONE_ENABLED="1"
python scripts/validate_gliner25_real_e1.py --model-dir "D:\Models\tapi\gliner25-multi-decide" --input evidence/experiments/dec017_e1_synthetic_smoke.jsonl --output dec017_e11_real_report.json --warmup 1 --repeats 2
$env:TAPI_SYSTEM_ONE_ENABLED="0"
~~~

Na sessão em que o checkpoint faltou, a suíte geral teve **264 testes PASS, 1 warning**, os 28 testes específicos PASS, Gate 0 PASS e verificação de custo zero PASS, reportados pelo operador. Esse resultado não constitui teste de inferência com pesos reais.

## Passo 1 — download público com autorização explícita

Esta etapa baixa cerca de 1,17 GB do Hugging Face e **não usa API de inferência paga**. O modelo/manifesto ficam fora do repositório, em pasta própria.

~~~powershell
python scripts/prepare_gliner25_local_checkpoint.py --model-dir "C:\Models\tapi\gliner25-multi-decide" --confirm-public-download
~~~

O comando fixa o commit SHA do repositório de pesos, baixa apenas arquivos necessários, verifica Safetensors e escreve tapi_e11_checkpoint_manifest.json com SHA-256 por arquivo. Além do hash local e do manifesto, confere os pesos contra o SHA-256 oficial publicado pelo Hugging Face (9efe0f88c99f2aa794452e9559dc60e98d60d9fa2bf1b60cf2710411b6da5b4e); se o fornecedor alterar os pesos em uma versão futura, a execução falha até que a revisão de segurança atualize o hash de referência. Não adicionar os pesos ao Git. Se o upstream mudar de revisão, usar outra pasta para evitar misturar versões.

## Passo 2 — inferência real inteiramente offline

~~~powershell
$env:TAPI_SYSTEM_ONE_ENABLED = "1"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_DATASETS_OFFLINE = "1"

python scripts/validate_gliner25_real_e1.py --model-dir "C:\Models\tapi\gliner25-multi-decide" --input evidence/experiments/dec017_e1_synthetic_smoke.jsonl --output dec017_e11_real_report.json --warmup 1 --repeats 2
~~~

O validador exige:
- arquivos completos e manifesto da revisão fixa com hashes correspondentes;
- config boundary / mDeBERTa-v3-base e pelo menos 100 tensores;
- a flag E1 explícita;
- preflight real de classify_text com um rótulo suportado;
- pelo menos uma classificação não-abstida;
- rubrica final com 20 campos intactos e sem informações audiovisuais inventadas.

O relatório contém status CHECKPOINT_LOADED_REAL_INFERENCE_EXECUTED **somente se a inferência com pesos reais tiver ocorrido sem exceções**. Inclui versão do modelo, hash, quantidade de inferências, latência, memória e benchmark sintético. Não contém exemplos de texto. Os testes com modelos falsos nunca substituem esse relatório.

## Passo 3 — verificações e encerramento do experimento

~~~powershell
python -m pytest -q
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
$env:TAPI_SYSTEM_ONE_ENABLED = "0"
~~~

Gate 0B deve continuar bloqueado. O experimento **não habilita** Meta Business Discovery, persistência de terceiros, contratação de APIs nem tratamento de dados pessoais. Mídia e posts reais exigem seus próprios direitos.

## Interpretação correta

- **PASS técnico:** SHA dos pesos e revisão conhecidos, carregamento real concluído, classify_text funcional, respostas dentro das categorias, conversão conservadora e medições de tempo/RAM.
- **INCONCLUSIVO:** pesos não baixados, incompatibilidade de dependências, falta de memória ou indisponibilidade da rede de download; **não** declarar inferência real.
- **FALHA:** pesos incompletos, resultados fora do contrato, violação de evidência, saída sempre abstida ou falha de runtime.
- **NÃO demonstrado pelo E1.1:** macro-F1 confiável em conteúdo MPE brasileiro, classificação de vídeos completos, generalização fora do domínio, ou superioridade sobre Jev/SubQ. Para isso, continuar a formação do gold set autorizado com divisão por criador.

## Referências

- https://huggingface.co/fastino/GLiNER2.5-multi-Decide
- https://pypi.org/project/gliner2/
- https://github.com/fastino-ai/GLiNER2

A revisão deste documento não constitui licença para conteúdo de terceiros nem homologa o experimento cientificamente.
