@echo off
cd /d "C:\Users\User\Encaminhamento-Alunos"
set PYTHONPATH=.
venv\Scripts\python.exe scripts\tests\gerar_dados_teste.py
pause