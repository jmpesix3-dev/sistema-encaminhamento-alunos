# Encaminhamento Escolar de Alunos

Sistema web para gerenciar o encaminhamento de alunos entre escolas, em
substituição às planilhas manuais.

## Instalação

Copie a pasta para o computador e, na primeira vez, rode o instalador
correspondente ao sistema operacional:

| Sistema | Comando |
|---|---|
| **Windows** | clique duas vezes em `instalar.bat` |
| **Mac / Linux** | clique duas vezes em `instalar.sh` (ou `bash instalar.sh`) |

Precisa de **Python 3.10 ou mais novo**.

### No Windows, o instalador cuida do Python sozinho

Se o computador não tiver Python, o `instalar.bat` tenta duas coisas, nesta
ordem:

1. **winget** — se existir (Windows 10 ou mais novo)
2. **Instalador do python.org em modo usuário** — baixa e instala **sem
   pedir permissão de administrador**, gravando na pasta do seu usuário

Só se as duas falharem é que aparece o link para instalar manualmente.

### No Mac e Linux, o Python precisa vir antes

A instalação automática nesses sistemas pede a senha de administrador, então
o script apenas detecta o que falta e mostra o comando exato:

```bash
brew install python                          # Mac
sudo apt install python3 python3-venv         # Ubuntu/Debian
sudo dnf install python3                     # Fedora/RHEL
```

Depois de instalado o Python, rode o `instalar.sh` de novo.

Depois da instalação, para iniciar em uso direto:

| Sistema | Comando |
|---|---|
| **Windows** | `iniciar.bat` |
| **Mac / Linux** | `bash iniciar.sh` |

O sistema abre em **http://localhost:8501**.

> Não copie a pasta `venv/` entre computadores. Ela tem os caminhos da
> máquina onde foi criada e não funciona em outro lugar. O instalador recria.

## Configuração opcional

Para enviar email e para usar o Google Maps na geolocalização, copie
`.env.example` para `.env` e preencha com seus dados.

**Nunca envie sua chave para o Git.** O arquivo `.env` já está ignorado.

| Variável | Para que serve |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Geolocalização precisa (sem ela usa OpenStreetMap) |
| `SMTP_USER` / `SMTP_PASSWORD` | Envio de email |

## Primeiros passos

O sistema segue quatro etapas, mostra na tela inicial:

1. **Carregar planilha** — cada escola envia sua demanda no formato
   `modeloupload.xlsx`
2. **Definir vagas** — quantos alunos cada escola comporta
3. **Alocar** — distribui por proximidade, respeitando a capacidade
4. **Gerar e enviar** — produz o PDF e envia para a escola

## O que o sistema faz

- **Importa** a planilha das escolas, agrupando por turma
- **Cadastra** alunos manualmente quando necessário
- **Edita** os dados em grade, com salvamento do que mudou
- **Geolocaliza** escolas e alunos, por busca automática ou ajuste no mapa
- **Aloca** por proximidade: o mais perto primeiro, 1ª opção até lotar,
  excedente vai para a 2ª
- **Agrupa por escola** quem enviou e para onde cada aluno foi
- **Gera** o PDF e o Excel no formato oficial
- **Envia** por email e acompanha o status

## Estrutura

```
encaminhamento/
├── app.py                    # ponto de entrada
├── config.py                 # configurações e caminhos
├── database/                 # modelos e operações
│   ├── models.py
│   └── crud.py
├── services/                 # regras de negócio
│   ├── excel_import.py       # leitura da planilha
│   ├── excel_export.py       # geração do modelodownload
│   ├── pdf_generator.py      # PDF oficial
│   ├── geocoding.py          # coordenadas
│   ├── allocation.py         # alocação por proximidade
│   ├── relatorio.py          # números do painel
│   ├── email_sender.py       # envio de email
│   └── status_tracker.py     # status dos lotes
├── ui/
│   ├── components.py         # peças reutilizáveis
│   └── pages/                # 6 telas
└── utils/                    # traduções e validações
```

## Manutenção

| Script | Para que serve |
|---|---|
| `importar_escolas.py` | Importa `escolas.xlsx` preservando capacidade e coordenadas |
| `geolocalizar_escolas.py` | Geolocaliza escolas em lote |
| `mesclar_duplicadas.py` | Detecta e mescla escolas com nome parecido |
| `migrar_banco.py` | Adiciona colunas novas sem perder dados |
| `gerar_cenario.py` / `carregar_cenario.py` | Gera dados de teste para demonstração |

## Testes

```cmd
venv\Scripts\python rodar_paginas.py
venv\Scripts\python testar_interacoes.py
```

Verificações estáticas que evitam regressões:

```cmd
venv\Scripts\python checar_colunas.py    # atributos existem no banco
venv\Scripts\python checar_rotas.py      # navegação do painel fecha
venv\Scripts\python checar_abas.py       # abas sem parâmetro inválido
venv\Scripts\python checar_st.py         # API do Streamlit compatível
venv\Scripts\python checar_traducao.py   # nenhum status em inglês
```

## Requisitos

- Python 3.10+
- Navegador (Chrome, Edge, Firefox)
- Conexão com a internet para geolocalização e email

## Observação sobre a versão do Streamlit

A versão está fixada em `requirements.txt` (`streamlit==1.64.0`) de propósito.
Outras versões quebram recursos usados nas telas. Se trocar, rode os testes
antes de usar.