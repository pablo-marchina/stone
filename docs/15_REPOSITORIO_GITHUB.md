# Repositório remoto GitHub — comprovado

- URL: https://github.com/pablo-marchina/stone
- Proprietário: `pablo-marchina`; nome: `stone`.
- Visibilidade: **privada** (verificada com o conector GitHub).
- Permissão do conector: escrita e administração disponíveis no momento da conferência.
- Criação: realizada pelo responsável do projeto; esta preparação apenas publica os arquivos.
- CI: executar **localmente** com `bash scripts/ci_local.sh`; não ativar GitHub Actions automaticamente.
- Custos: **R$ 0** de desembolso, qualquer gasto pago é bloqueado.
- Dados: não subir datasets externos, tokens ou mídia não autorizada.
- As políticas de orçamento e de acesso permanecem em `config/`.

## Comandos locais

```bash
git clone https://github.com/pablo-marchina/stone.git
cd stone
python -m pip install -e '.[dev]'
bash scripts/ci_local.sh
```

Este é um bootstrap de engenharia, não uma homologação de produto em produção.
