"""
Leitura do arquivo no formato modeloupload.

Espera colunas: Nº | NOME DO ALUNO | ENDEREÇO | ESCOLA DE DESTINO | ASSINATURA
Cada aluno ocupa duas linhas: a primeira traz a 1a opcao de destino,
a segunda (vazia nos outros campos) traz a 2a opcao.

O arquivo pode ter varios blocos, um por escola de origem, caso em
que a planilha foi consolidada por alguem antes de chegar ate aqui.
"""
import re
import tempfile
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import openpyxl


@dataclass
class ImportResult:
    success: bool
    students: List[Dict[str, Any]]
    origin_school: str
    origin_class: str
    total_expected: int
    errors: List[str]
    warnings: List[str]
    # Preenchido quando a planilha tem mais de uma escola de origem
    grupos: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def total_alunos(self) -> int:
        return len(self.students)


def _texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _limpar(valor) -> str:
    """Remove preenchimentos vazios tipo '------------'."""
    t = _texto(valor)
    if not t or set(t) <= {"-", " "}:
        return ""
    return t


def _achar_cabecalho(ws) -> Optional[int]:
    """Localiza a linha de cabecalho (a que tem 'Nº' e 'NOME DO ALUNO')."""
    for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), 1):
        celulas = [_texto(v).upper() for v in row]
        tem_nome = any("NOME DO ALUNO" in c for c in celulas)
        tem_destino = any("DESTINO" in c for c in celulas)
        if tem_nome and tem_destino:
            return idx
    return None


def parse_modeloupload(file_path: str) -> ImportResult:
    """Le a planilha e devolve os alunos lidos, com 1a e 2a opcoes de destino."""
    erros: List[str] = []
    avisos: List[str] = []
    alunos: List[Dict[str, Any]] = []
    grupos: List[Dict[str, Any]] = []

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
    except Exception as exc:
        return ImportResult(
            success=False, students=[], origin_school="", origin_class="",
            total_expected=0, errors=[f"Nao foi possivel ler o arquivo: {exc}"],
            warnings=[],
        )

    cabecalho = _achar_cabecalho(ws)
    if cabecalho is None:
        return ImportResult(
            success=False, students=[], origin_school="", origin_class="",
            total_expected=0,
            errors=["Nao encontrei a linha de cabecalho (esperado 'NOME DO ALUNO' e 'ESCOLA DE DESTINO')"],
            warnings=[],
        )

    # Estado do bloco atual
    origem_atual = ""
    turma_atual = ""
    total_declarado = 0
    alunos_no_bloco: List[Dict[str, Any]] = []
    aluno_aberto: Optional[Dict[str, Any]] = None
    cabecalho_visto = False

    def fechar_bloco():
        nonlocal alunos_no_bloco, origem_atual, turma_atual, total_declarado, aluno_aberto
        if aluno_aberto:
            alunos_no_bloco.append(aluno_aberto)
            aluno_aberto = None
        if alunos_no_bloco:
            grupos.append({
                "origin_school": origem_atual,
                "origin_class": turma_atual,
                "total_declared": total_declarado,
                "students": alunos_no_bloco,
            })
        alunos_no_bloco = []
        origem_atual = ""
        turma_atual = ""
        total_declarado = 0

    # Varre a planilha inteira: o cabecalho de cada bloco traz a escola e a turma
    for row in ws.iter_rows(min_row=1, values_only=True):
        linha = [_texto(v) for v in row]
        texto_linha = " ".join(v for v in linha if v)
        celulas_upper = [v.upper() for v in linha]

        # ---- Linha de cabecalho: marca que os alunos comecam aqui ----
        if any("NOME DO ALUNO" in c for c in celulas_upper):
            cabecalho_visto = True
            continue

        # ---- Rodape entre blocos ----
        if cabecalho_visto and (texto_linha.startswith("Data:") or "Secret" in texto_linha):
            fechar_bloco()
            cabecalho_visto = False
            continue

        # ---- Escola e turma do bloco ----
        m_escola = re.search(r"Unidade Escolar de Origem:\s*(.+)", texto_linha, re.IGNORECASE)
        if m_escola:
            if alunos_no_bloco or origem_atual:
                fechar_bloco()
                cabecalho_visto = False
            origem_atual = m_escola.group(1).strip()
            continue

        m_turma = re.search(r"Turma:\s*(\S+)", texto_linha, re.IGNORECASE)
        if m_turma and not turma_atual and not cabecalho_visto:
            turma_atual = m_turma.group(1).strip()
            m_total = re.search(r"Total de alunos encaminhados:\s*(\d+)",
                                 texto_linha, re.IGNORECASE)
            if m_total:
                total_declarado = int(m_total.group(1))
            continue

        # Antes do cabecalho so interessam os dados do bloco
        if not cabecalho_visto:
            continue

        # ---- Linha de aluno ----
        primeiro = linha[0] if linha else ""
        if primeiro.isdigit():
            if aluno_aberto:
                alunos_no_bloco.append(aluno_aberto)

            nome = linha[1] if len(linha) > 1 else ""
            nome_civil = ""
            m_civil = re.match(r"^\s*Nome Civil:\s*(.+)$", nome, re.IGNORECASE)
            if m_civil:
                nome_civil = m_civil.group(1).strip()
                nome = nome_civil

            assinatura = linha[4] if len(linha) > 4 else ""
            aluno_aberto = {
                "name": nome,
                "civil_name": nome_civil or nome,
                "address": linha[2] if len(linha) > 2 else "",
                "reference_point": "",
                "destination_school_1_name": linha[3] if len(linha) > 3 else "",
                "destination_school_2_name": "",
                "responsible_signature": bool(
                    assinatura and set(assinatura) != {"-"}
                    and "ASSINATURA" not in assinatura.upper()
                ),
            }
            continue

        # ---- Linha da 2a opcao ----
        if aluno_aberto is not None and len(linha) > 3 and linha[3]:
            aluno_aberto["destination_school_2_name"] = linha[3]

    fechar_bloco()

    if not grupos:
        return ImportResult(
            success=False, students=[], origin_school="", origin_class="",
            total_expected=0, errors=["A planilha nao tem nenhum aluno"],
            warnings=[],
        )

    # Achata a lista de alunos
    for g in grupos:
        alunos.extend(g["students"])

        if not g["origin_school"]:
            avisos.append("Ha alunos sem escola de origem informada.")

        declarado = g["total_declared"]
        if declarado and declarado != len(g["students"]):
            avisos.append(
                f"{g['origin_school'] or 'Sem nome'}: a planilha declara {declarado} aluno(s) "
                f"e foram lidos {len(g['students'])}"
            )

    if not alunos:
        return ImportResult(
            success=False, students=[], origin_school="", origin_class="",
            total_expected=0, errors=["A planilha nao tem nenhum aluno"],
            warnings=avisos,
        )

    # Origem principal: a do primeiro bloco
    principal = grupos[0]
    return ImportResult(
        success=True,
        students=alunos,
        origin_school=principal["origin_school"],
        origin_class=principal["origin_class"],
        total_expected=len(alunos),
        errors=erros,
        warnings=avisos,
        grupos=grupos,
    )


def parse_modeloupload_bytes(file_bytes: bytes) -> ImportResult:
    """Mesma leitura, a partir dos bytes de um arquivo enviado."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(file_bytes)
        caminho = tmp.name
    try:
        return parse_modeloupload(caminho)
    finally:
        try:
            os.unlink(caminho)
        except OSError:
            pass
