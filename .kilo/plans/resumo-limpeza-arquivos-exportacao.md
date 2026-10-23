# Plano: Limpeza automática de arquivos de resumo e exportacao

## Contexto / Problema

`encaminhamento/ui/pages/_01_Dashboard.py:537` (`_exportar`) gera um novo arquivo `resumo_YYYYMMDD_HHMMSS.xlsx` em `DATA_DIR` a cada clique em "Exportar resumo", sem remover os anteriores. Com o uso repetido, a pasta enche de arquivos obsoletos.

O usuario relatou: "no montar resumo, sempre quando montar 2 novos deve apagar o primeiro, para nao encher de arquivos." e esclareceu que o foco e o "resumo" que cria varios arquivos. Tambem pediu para "pensar em melhorias".

## Decisoes

1. **Escopo principal (resumo):** apos gerar `resumo_*.xlsx` em `_exportar`, manter apenas os N mais recentes por data de modificacao e excluir os demais. N configuravel via `RESUMO_KEEP_N` (padrao 5).
2. **Melhoria (Excel + PDF export de alunos):** aplicar mesma retencao nos diretorios `EXCEL_EXPORT_DIR` e `PDF_EXPORT_DIR` (arquivos `encaminhamento_*.xlsx` e `encaminhamento_*.pdf`), preservando `modeloupload_template.xlsx`. N configuravel via `EXPORT_KEEP_N` (padrao 5).
3. **Utilitario:** adicionar `manter_arquivos_recentes(diretorio, padrao, manter_n)` em `encaminhamento/utils/arquivos.py`.
4. **Config:** adicionar `RESUMO_KEEP_N` e `EXPORT_KEEP_N` em `encaminhamento/config.py`.
5. **Limpeza inicial:** opcionalmente executar limpeza na inicializacao do app para remover orfaos acumulados antes da correcao.

## Arquivos afetados

- `encaminhamento/utils/arquivos.py` — novo utilitario de retentacao
- `encaminhamento/config.py` — constantes de retentacao
- `encaminhamento/ui/pages/_01_Dashboard.py` — `_exportar` chama retentacao apos salvar
- `encaminhamento/ui/pages/_02_Alunos.py` — `_aba_exportar` chama retentacao apos gerar Excel/PDF (melhoria)

## Tarefas (ordem)

1. Adicionar `manter_arquivos_recentes()` em `utils/arquivos.py` (lista arquivos por `padrao`, ordena por `st_mtime`, exclui excedentes mais antigos).
2. Adicionar `RESUMO_KEEP_N=5` e `EXPORT_KEEP_N=5` em `config.py`.
3. Em `_exportar` (`_01_Dashboard.py`), apos `exportar_resumo(...)`, chamar retentacao em `DATA_DIR` para `resumo_*.xlsx` usando `RESUMO_KEEP_N`.
4. (Melhoria) Em `_aba_exportar` (`_02_Alunos.py`), apos gerar Excel e PDF, chamar retentacao em `EXCEL_EXPORT_DIR` e `PDF_EXPORT_DIR` usando `EXPORT_KEEP_N`, preservando `modeloupload_template.xlsx`.
5. (Opcional) Limpeza na inicializacao do app para arquivos orfaos pre-existentes.
6. Teste de validacao: gerar N+1 arquivos e confirmar que restam apenas N.

## Validacao

- Executar `encaminhamento/tests/comprehensive_integration.py` (testes existentes).
- Teste manual: gerar 6 resumos e confirmar que restam exatamente 5 (ou N configurado).
- Confirmar que `modeloupload_template.xlsx` nao e excluido.

## Fora de escopo

- Exclusao automatica do banco de dados ou backups.
- Limpeza de arquivos de importacao (ativos em uso).
- Alteracao do formato/nome dos arquivos gerados.

## Perguntas resolvidas com o usuario

- Escopo confirmado: foco no `resumo`; melhoria opcional para Excel/PDF.
