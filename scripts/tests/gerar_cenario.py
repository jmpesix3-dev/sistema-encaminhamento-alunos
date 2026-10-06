"""
Gera um cenario de teste completo.

Cria uma planilha no formato modeloupload.xlsx com alunos de varias escolas
de origem, distribute entre varias escolas de destino (com excesso em uma,
para testar a lotacao e o transbordo para a 2a opcao).

Uso:  python gerar_cenario.py
"""
import random
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# ----------------------------------------------------------------------
# Escolas de origem (turmas que vao encaminhar alunos)
# ----------------------------------------------------------------------
ORIGENS = [
    {
        "escola": "E. E. M. Francisco Alves Toledo",
        "turma": "601",
        # alunosmoram principalmente perto de 1o e 3o distrito
        "bairros": ["Atafona", "Cardoso", "Grussaí", "Centro"],
        "destinos": [
            "E. M. Manoel Nunes Barreto",
            "E. E. M. João Batista Alves",
            "E. M. Amaro de Souza Paes",
        ],
    },
    {
        "escola": "E. E. M. João Batista Alves",
        "turma": "702",
        "bairros": ["Bajuru", "Açu", "Mato Escuro"],
        "destinos": [
            "E. E. M. Luiz Gomes da Silva Neto",
            "E. M. Manoel Nunes Barreto",
            "E. E. M. Manoel Ducas de Brito",
        ],
    },
    {
        "escola": "E. M. Amaro de Souza Paes",
        "turma": "503",
        "bairros": ["Barcelos", "Água Preta", "Perigoso"],
        "destinos": [
            "E. E. M. Francisco Alves Toledo",
            "E. E. M. Manoel Ducas de Brito",
        ],
    },
    {
        "escola": "C. M. E. Marcos Medeiros Valiengo",
        "turma": "1º ano",
        "bairros": ["Centro", "Atafona"],
        "destinos": [
            "Creche Municipal Floriano de Azeredo Siqueira",
            "Creche Municipal Maria da Conceição dos Santos Campos",
            "C. M. E. Aldair Coutinho Machado",
        ],
    },
]

# Enderecos base por bairro
ENDERECOS = {
    "Atafona": "R. Ernani Alves nº 396, Atafona",
    "Cardoso": "R. Cardoso, s/n, Cardoso",
    "Grussaí": "R. Manoel Fagundes de Melo s/n, Grussaí",
    "Centro": "Av. Rotary, 1200, Centro",
    "Bajuru": "Estrada Principal s/n, Bajuru",
    "Açu": "R. Maria Clarina, s/n, Açu",
    "Mato Escuro": "Estrada Principal s/n, Mato Escuro",
    "Barcelos": "R. Barão de Barcelos nº 345, Barcelos",
    "Água Preta": "Est. de Água Preta, 85, Água Preta",
    "Perigoso": "BR 356 s/n Cajueiro, Perigoso",
    "Cajueiro": "BR 356 s/n, Cajueiro",
}

NOMES = [
    "Ana Beatriz", "Bruno", "Camila", "Diego", "Eduarda", "Felipe",
    "Gabriela", "Henrique", "Isabela", "João", "Karina", "Lucas",
    "Mariana", "Nathan", "Olívia", "Pedro", "Queila", "Rafael",
    "Sofia", "Thiago", "Úrsula", "Victor", "Wanda", "Xavier",
    "Yasmin", "Zeca", "Amanda", "Caio", "Daniela", "Enzo",
    "Fernanda", "Gustavo", "Helena", "Igor", "Juliana", "Leonardo",
    "Marcela", "Nicolas", "Otávio", "Patrícia", "Renato", "Sabrina",
]

SOBRENOMES = [
    "Alves", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferreira",
    "Gonçalves", "Henriques", "Imperatriz", "Junqueira", "Klein",
    "Lemos", "Martins", "Nogueira", "Oliveira", "Pereira", "Quintana",
    "Ribeiro", "Santos", "Teixeira", "Uchôa", "Vieira", "Werneck",
    "Xavier", "Young", "Zanella", "Andrade", "Bastos", "Correia",
]


def nome_aleatorio(usados):
    while True:
        nome = f"{random.choice(NOMES)} {random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"
        if nome not in usados:
            usados.add(nome)
            return nome


def gerar_planilha(destino):
    """Monta a planilha no formato modeloupload."""
    usados = set()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "modeloupload"

    estilo_titulo = Font(bold=True, size=14)
    estilo_header = Font(bold=True, size=11, color="FFFFFF")
    estilo_normal = Font(size=11)
    preenchimento = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    esquerda = Alignment(horizontal="left", vertical="center", wrap_text=True)
    borda = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    linha = 1
    for origem in ORIGENS:
        # Quantos alunos desta escola
        total = random.randint(12, 20)

        ws.merge_cells(f"A{linha}:E{linha}")
        ws[f"A{linha}"] = "ENCAMINHAMENTO DE ALUNOS PARA 2026"
        ws[f"A{linha}"].font = estilo_titulo
        ws[f"A{linha}"].alignment = centro
        linha += 1

        ws.merge_cells(f"A{linha}:E{linha}")
        ws[f"A{linha}"] = f"Unidade Escolar de Origem: {origem['escola']}"
        ws[f"A{linha}"].font = estilo_header and Font(bold=True, size=11)
        linha += 1

        ws.merge_cells(f"A{linha}:E{linha}")
        ws[f"A{linha}"] = f"Turma: {origem['turma']}          Total de alunos encaminhados: {total}"
        ws[f"A{linha}"].font = Font(bold=True, size=11)
        linha += 1

        cabecalhos = [
            "Nº", "NOME DO ALUNO (completo)",
            "ENDEREÇO COMPLETO E COM PONTO DE REFERÊNCIA",
            "ESCOLA DE DESTINO", "ASSINATURA DO RESPONSÁVEL LEGAL",
        ]
        for col, titulo in enumerate(cabecalhos, 1):
            c = ws.cell(row=linha, column=col, value=titulo)
            c.font = estilo_header
            c.fill = preenchimento
            c.alignment = centro
            c.border = borda
        linha += 1

        for i in range(1, total + 1):
            bairro = random.choice(origem["bairros"])
            endereco = ENDERECOS.get(bairro, f"R. {bairro}, {bairro}")
            # inclui o numero do lote
            endereco = f"{endereco}, nº {random.randint(10, 899)}"

            destino_1 = random.choice(origem["destinos"])
            destino_2 = random.choice([d for d in origem["destinos"] if d != destino_1])

            ws.cell(row=linha, column=1, value=i).font = estilo_normal
            ws.cell(row=linha, column=1).alignment = centro
            ws.cell(row=linha, column=1).border = borda

            nome = nome_aleatorio(usados)
            ws.cell(row=linha, column=2, value=f"Nome Civil: {nome}").font = estilo_normal
            ws.cell(row=linha, column=2).alignment = esquerda
            ws.cell(row=linha, column=2).border = borda

            ws.cell(row=linha, column=3, value=endereco).font = estilo_normal
            ws.cell(row=linha, column=3).alignment = esquerda
            ws.cell(row=linha, column=3).border = borda

            ws.cell(row=linha, column=4, value=destino_1).font = estilo_normal
            ws.cell(row=linha, column=4).alignment = centro
            ws.cell(row=linha, column=4).border = borda

            assinatura = "ASSINATURA DO RESPONSÁVEL" if random.random() > 0.2 else ""
            ws.cell(row=linha, column=5, value=assinatura).font = estilo_normal
            ws.cell(row=linha, column=5).border = borda
            linha += 1

            # linha da 2a opcao
            ws.cell(row=linha, column=4, value=destino_2).font = estilo_normal
            ws.cell(row=linha, column=4).alignment = centro
            ws.cell(row=linha, column=4).border = borda
            for col in (1, 2, 3, 5):
                ws.cell(row=linha, column=col).border = borda
            linha += 1

        # rodape
        linha += 1
        ws.merge_cells(f"A{linha}:E{linha}")
        ws[f"A{linha}"] = "Data: ____/____/______."
        ws[f"A{linha}"].font = Font(bold=True)
        linha += 1
        ws.merge_cells(f"A{linha}:E{linha}")
        ws[f"A{linha}"] = (
            "Secretário                                      "
            "Diretor ou Responsável pela Unidade de Ensino"
        )
        linha += 3

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 42
    ws.column_dimensions["C"].width = 50
    ws.column_dimensions["D"].width = 34
    ws.column_dimensions["E"].width = 28

    wb.save(destino)
    return destino


if __name__ == "__main__":
    random.seed(7)  # resultado reproduzivel
    caminho = gerar_planilha("modeloupload_teste.xlsx")
    print(f"Planilha criada: {caminho}")

    wb = openpyxl.load_workbook(caminho)
    ws = wb.active
    nomes = sum(
        1 for row in ws.iter_rows(min_col=2, max_col=2, values_only=True)
        if row[0] and str(row[0]).startswith("Nome Civil:")
    )
    print(f"Alunos na planilha: {nomes}")
