# Projeto Reorganization Plan: Orfanizar Pastas e Arquivos

## Goal
Move all scattered root-level scripts and data files into organized subdirectories (`scripts/`, `data/`) while keeping installer/startup entry points at root. Update all path references so nothing breaks.

## Current Root Contents (28 items)

### Python scripts (19 scripts)
**Static checks:** `checar_cores.py`, `checar_abas.py`, `checar_colunas.py`, `checar_rotas.py`, `checar_imports.py`, `checar_st.py`, `checar_traducao.py`, `checar_navegacao.py`
**Tests:** `rodar_paginas.py` (imports `gerar_arquivos_teste`), `testar_interacoes.py` (imports `gerar_arquivos_teste`), `testar_fluxo.py`, `testar_filtros.py`, `verificar_dashboard.py`, `verificar_situacao.py`
**Generators:** `gerar_arquivos_teste.py`, `gerar_dados_teste.py`, `gerar_cenario.py`
**Maintenance:** `carregar_cenario.py`, `geolocalizar_escolas.py`, `mesclar_duplicadas.py`, `migrar_banco.py`, `importar_escolas.py`
**Installer:** `instalar.py`

### Batch/shell scripts (8 files)
`instalar.bat`, `instalar.sh`, `obter_python.bat`, `iniciar.bat`, `iniciar.sh`, `run_server.bat`, `restart_server.bat`, `run.bat`

### Data files (4 files)
`modelodowload.xlsx`, `modeloupload.xlsx`, `modeloupload_teste.xlsx`, `escolas.xlsx`

### Other (5 items)
`requirements.txt`, `.gitignore`, `.env.example`, `README.md`, `PYTHON_ENCONTRADO.txt`
Plus generated: `streamlit.log`, `streamlit.err`, `~$modeloupload.xlsx` (Excel lock file)

## Constraints (must not break)

1. **instalar.bat** calls `obter_python.bat` via `call "%~dp0obter_python.bat"` — must stay together at root
2. **restart_server.bat** calls `run_server.bat` via `cmd.exe /c "%~dp0run_server.bat"` — both at root
3. **iniciar.bat** references `venv\Scripts\python.exe` relative to `%~dp0` — stays at root
4. **rodar_paginas.py** and **testar_interacoes.py** do `from gerar_arquivos_teste import gerar, limpar` — no package prefix, rely on CWD being root
5. **gerar_arquivos_teste.py** sets `RAIZ = Path(__file__).parent` and writes `_testes_paginas/` to that — currently writes to root
6. **carregar_cenario.py** has `PLANILHA = "modeloupload_teste.xlsx"` — reads by CWD
7. **importar_escolas.py** reads `"escolas.xlsx"` — reads by CWD
8. **gerar_cenario.py** writes `"modeloupload_teste.xlsx"` — writes to CWD
9. **checar_cores.py** uses `Path("encaminhamento")` and `Path(".")` for file scanning
10. **checar_rotas.py** uses `pathlib.Path("encaminhamento/...")` and `importlib.import_module("encaminhamento...")`
11. **checar_imports.py** has hardcoded paths in `ALVOS` list like `"encaminhamento/services/..."`
12. **checar_navegacao.py** uses `pathlib.Path("encaminhamento/ui/pages")` and `pathlib.Path(f"encaminhamento/ui/pages/{nome}.py")`
13. **checar_abas.py** uses `pathlib.Path("encaminhamento/ui/pages")`
14. **checar_st.py** uses `pathlib.Path("encaminhamento/ui/pages")`
15. **checar_traducao.py** uses `pathlib.Path("encaminhamento/ui")`
16. **gerar_dados_teste.py** uses `sys.path.insert(0, str(Path(__file__).parent.parent))` — correct from root (parent.parent goes from `encaminhamento/tests/` wait no, this is at root level, so `parent.parent` = parent of root = `Users/User/`)
17. **_03_Escolas.py:23** mentions "rode importar_escolas.py" in a caption
18. **README.md** references all scripts by root-level path

## Target Structure
```
project-root/
├── data/                     # xlsx data files
│   ├── modelodowload.xlsx
│   ├── modeloupload.xlsx
│   ├── modeloupload_teste.xlsx
│   └── escolas.xlsx
├── scripts/
│   ├── checks/               # static verification scripts
│   │   ├── checar_cores.py
│   │   ├── checar_abas.py
│   │   ├── checar_colunas.py
│   │   ├── checar_rotas.py
│   │   ├── checar_imports.py
│   │   ├── checar_st.py
│   │   ├── checar_traducao.py
│   │   └── checar_navegacao.py
│   ├── tests/                # AppTest-based scripts + helpers
│   │   ├── rodar_paginas.py
│   │   ├── testar_interacoes.py
│   │   ├── testar_fluxo.py
│   │   ├── testar_filtros.py
│   │   ├── verificar_dashboard.py
│   │   ├── verificar_situacao.py
│   │   └── gerar_arquivos_teste.py
│   └── tools/                # data/maintenance scripts
│       ├── gerar_dados_teste.py
│       ├── gerar_cenario.py
│       ├── carregar_cenario.py
│       ├── geolocalizar_escolas.py
│       ├── mesclar_duplicadas.py
│       ├── migrar_banco.py
│       └── importar_escolas.py
├── instalar.py               # KEEP — uses Path(__file__).parent
├── instalar.bat / .sh        # KEEP
├── obter_python.bat          # KEEP
├── iniciar.bat / .sh         # KEEP
├── run_server.bat            # KEEP
├── restart_server.bat        # KEEP
├── run.bat                   # KEEP (deprecated wrapper)
├── requirements.txt          # KEEP
├── .gitignore                # UPDATE
├── .env.example              # KEEP
├── README.md                 # UPDATE
└── .kilo/                    # KEEP
```

## Implementation Steps

### Step 1: Create directories
```
mkdir -p data scripts/checks scripts/tests scripts/tools
```

### Step 2: Move data files to `data/`
```
mv modelodowload.xlsx modeloupload.xlsx modeloupload_teste.xlsx escolas.xlsx data/
```
Remove temp file: `rm ~$modeloupload.xlsx`

### Step 3: Move static check scripts to `scripts/checks/`
Move 8 `checar_*.py` files.

For each, add at the top (replacing any existing `sys.path` insert or after imports):
```python
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
```

Then fix relative path references:

- **checar_cores.py**: `Path("encaminhamento")` → `RAIZ / "encaminhamento"`, `Path(".")` → `RAIZ`
- **checar_abas.py**: `Path("encaminhamento/ui/pages")` → `RAIZ / "encaminhamento/ui/pages"`
- **checar_colunas.py**: Already has `sys.path.insert(0, str(Path(__file__).parent))` — replace with `sys.path.insert(0, str(RAIZ))`
- **checar_rotas.py**: All `pathlib.Path("encaminhamento/...")` → `RAIZ / "encaminhamento/..."`. Add `sys.path` anchor for `importlib.import_module` calls.
- **checar_imports.py**: In `ALVOS` list, prefix each path with `RAIZ /`. Or change the loop to prepend `RAIZ /` when reading.
- **checar_st.py**: `Path("encaminhamento/ui/pages")` → `RAIZ / "encaminhamento/ui/pages"`
- **checar_traducao.py**: `Path("encaminhamento/ui")` → `RAIZ / "encaminhamento/ui"`
- **checar_navegacao.py**: `pathlib.Path("encaminhamento/ui/pages")` → `RAIZ / "encaminhamento/ui/pages"`, and `pathlib.Path(f"encaminhamento/ui/pages/{nome}.py")` → `RAIZ / f"encaminhamento/ui/pages/{nome}.py"`

### Step 4: Move test scripts to `scripts/tests/`
Move: `rodar_paginas.py`, `testar_interacoes.py`, `testar_fluxo.py`, `testar_filtros.py`, `verificar_dashboard.py`, `verificar_situacao.py`, `gerar_arquivos_teste.py`

For each, add path anchor:
```python
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
```

Fixes per file:

- **rodar_paginas.py**: Add `sys.path.insert(0, str(Path(__file__).parent))` so `from gerar_arquivos_teste import` works. Also change `AppTest.from_file(str(arquivos[atalho]))` — the generated files are in `_testes_paginas/` at root, so use `RAIZ / "_testes_paginas"`.

- **testar_interacoes.py**: Same as rodar_paginas.py — add sibling directory to path. Change `AppTest.from_file` references.

- **gerar_arquivos_teste.py**: Change `RAIZ = Path(__file__).parent` → `RAIZ = Path(__file__).resolve().parent.parent.parent` (project root). Change `PASTA = RAIZ / "_testes_paginas"` — this will now be at project root. The generated test files reference `encaminhamento` via `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` which goes from `_testes_paginas/` to root — should still work.

- **verificar_dashboard.py**: Change `AppTest.from_file("encaminhamento/app.py", ...)` → `AppTest.from_file(str(RAIZ / "encaminhamento/app.py"), ...)`

- **verificar_situacao.py**: Same AppTest path fix.

- **testar_fluxo.py**: Add path anchor. Uses `from encaminhamento...` imports — will work with sys.path anchor.

- **testar_filtros.py**: Add path anchor. Uses `AppTest.from_file("encaminhamento/ui/pages/_05_Batch_Management.py", ...)` → fix path.

### Step 5: Move maintenance scripts to `scripts/tools/`
Move: `gerar_dados_teste.py`, `gerar_cenario.py`, `carregar_cenario.py`, `geolocalizar_escolas.py`, `mesclar_duplicadas.py`, `migrar_banco.py`, `importar_escolas.py`

For each, fix `sys.path` to point to project root:
- **gerar_dados_teste.py**: Change `sys.path.insert(0, str(Path(__file__).parent.parent))` → `str(Path(__file__).resolve().parent.parent.parent)`
- **carregar_cenario.py**: Change `sys.path.insert(0, str(Path(__file__).parent))` → `str(Path(__file__).resolve().parent.parent.parent)`. Change `PLANILHA = "modeloupload_teste.xlsx"` → `str(RAIZ / "data" / "modeloupload_teste.xlsx")`
- **geolocalizar_escolas.py**: Change `sys.path.insert(0, str(Path(__file__).parent))` → `str(Path(__file__).resolve().parent.parent.parent)`
- **mesclar_duplicadas.py**: Change `sys.path.insert(0, str(Path(__file__).parent))` → `str(Path(__file__).resolve().parent.parent.parent)`
- **migrar_banco.py**: Change `sys.path.insert(0, str(Path(__file__).parent))` → `str(Path(__file__).resolve().parent.parent.parent)`
- **importar_escolas.py**: Change `sys.path.insert(0, str(Path(__file__).parent))` → `str(Path(__file__).resolve().parent.parent.parent)`. Change `"escolas.xlsx"` → `str(RAIZ / "data/escolas.xlsx")`
- **gerar_cenario.py**: No `sys.path` insert currently (only imports openpyxl). Add path anchor for potential `encaminhamento` imports. Change `destino` from `"modeloupload_teste.xlsx"` to `str(RAIZ / "data/modeloupload_teste.xlsx")`

### Step 6: Update `.gitignore`
Add:
```
# Generated/temp files
streamlit.log
streamlit.err
~$*.xlsx
PYTHON_ENCONTRADO.txt
_test_tmp/
_testes_paginas/
```
Remove `verificar_dashboard.py` and `verificar_situacao.py` from git (they're temp verification scripts from the previous task — move them to `scripts/tests/` instead of deleting).

### Step 7: Update `_03_Escolas.py` line 23
Change: `"para trazer o arquivo escolas.xlsx de volta, rode importar_escolas.py."`
→ `"para trazer o arquivo escolas.xlsx de volta, rode scripts/tools/importar_escolas.py."`

### Step 8: Update README.md
- Update "Manutenção" table: all scripts → `scripts/tools/<name>.py`
- Update "Testes" section: scripts → `scripts/tests/<name>.py`
- Update "Verificações estáticas" section: scripts → `scripts/checks/<name>.py`
- Update structure section to show new `data/` and `scripts/` directories

### Step 9: Create `scripts/__init__.py`
Empty file so `scripts` is a proper package (allows `from scripts.checks...` imports if needed).

### Step 10: Verify
1. Run `scripts/checks/checar_colunas.py` — should find no invalid attributes
2. Run `scripts/checks/checar_rotas.py` — all routes close
3. Run `scripts/checks/checar_abas.py` — tabs OK
4. Run `scripts/checks/checar_st.py` — Streamlit API compat
5. Run `scripts/checks/checar_traducao.py` — no English status labels
6. Run `scripts/checks/checar_cores.py` — color scan
7. Run `scripts/checks/checar_navegacao.py` — import + routes
8. Run `scripts/checks/checar_imports.py` — unused imports
9. Run `scripts/tests/rodar_paginas.py` — all pages load
10. Run `scripts/tests/testar_interacoes.py` — interactions OK
11. Run `scripts/tests/verificar_dashboard.py` — 4 cards present
12. Run integration test (`encaminhamento/tests/comprehensive_integration.py`)
13. AppTest: dashboard loads with correct counts (107 alunos, 71 encaminhados, 36 pendentes, 9 info_pendente)

## Risks
- Any script run from a different CWD than project root will fail if it uses relative paths — the path anchors fix this
- `gerar_arquivos_teste.py` generates temp files that need to be cleaned up — already in `.gitignore`
- `checar_roters.py` and `checar_navegacao.py` use `importlib.import_module` which requires project root on `sys.path` — the anchors handle this
