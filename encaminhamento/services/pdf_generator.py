from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image,
)
from typing import List
from encaminhamento.database.models import Student, School
from encaminhamento.database.crud import get_students_for_batch
from encaminhamento.database import get_session
from encaminhamento.config import PDF_EXPORT_DIR, DATA_DIR
from encaminhamento.utils.arquivos import nome_seguro


def generate_batch_pdf(batch_id: int, output_path: str = None) -> str:
    """Generate PDF for a forwarding batch in modelodownload format."""
    with get_session() as session:
        from encaminhamento.database.crud import get_batch
        batch = get_batch(session, batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")
        
        students = get_students_for_batch(session, batch_id)
        if not students:
            raise ValueError(f"No students in batch {batch_id}")
        
        destination_school_name = batch.destination_school.name if batch.destination_school else ""
        student_data = []
        for s in students:
            origin_name = s.origin_school.name if s.origin_school else ""
            student_data.append((s.name, s.full_address, origin_name))
    
    if output_path is None:
        output_path = PDF_EXPORT_DIR / f"encaminhamento_batch_{batch_id}.pdf"
    
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Title'],
        fontSize=12,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=10,
        leading=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        textColor=white
    )
    
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    cell_center_style = ParagraphStyle(
        'TableCellCenter',
        parent=cell_style,
        alignment=TA_CENTER
    )
    
    elements = []
    
    # Logo
    logo_path = DATA_DIR / "logo_sjb.png"
    if logo_path.exists():
        elements.append(Image(str(logo_path), width=2.5*cm, height=2.5*cm, kind='proportional'))
        elements.append(Spacer(1, 6))
    
    # Title row
    class_name = batch.origin_class.name if batch.origin_class else ""
    oferta = batch.destination_school.oferta if batch.destination_school else 0
    header_parts = []
    header_parts.append(f"<b>Unidade Escolar de destino:</b> {destination_school_name}")
    if class_name:
        header_parts.append(f"<b>Turma:</b> {class_name}")
    header_parts.append(f"<b>Nº de alunos encaminhados:</b> {len(student_data)} / <b>Oferta:</b> {oferta}")
    
    title_text = "                     ".join(header_parts)
    elements.append(Paragraph(title_text, title_style))
    
    # Subtitle
    elements.append(Paragraph("QUADRO DE ENCAMINHAMENTO DE ALUNOS 2025", subtitle_style))
    elements.append(Spacer(1, 6))
    
    # Table data
    headers = ["Nº", "NOME DO ALUNO", "ENDEREÇO", "UNIDADE DE ORIGEM"]
    
    table_data = [headers]
    for idx, (name, address, origin_name) in enumerate(student_data, 1):
        table_data.append([
            str(idx),
            name,
            address,
            origin_name
        ])
    
    # Column widths for landscape A4
    col_widths = [1.5*cm, 7*cm, 11*cm, 7*cm]
    
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Nº column centered
        ('ALIGN', (1, 1), (-1, -1), 'LEFT'),   # Other columns left
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('LINEBELOW', (0, 0), (-1, 0), 1, black),
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        
        # Alternate row colors
        *[('BACKGROUND', (0, i), (-1, i), HexColor('#F2F2F2')) for i in range(2, len(table_data), 2)],
    ]))
    
    elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 20))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    elements.append(Paragraph("Data: _____/_____/______.", footer_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        "Secretário&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "Diretor ou Responsável pela Unidade de Ensino",
        footer_style
    ))
    
    doc.build(elements)
    return str(output_path)


def generate_student_list_pdf(students: List[Student], destination_school: School,
                               origin_school: School, class_name: str = "",
                               output_path: str = None) -> str:
    """Generate PDF for a custom student list."""
    if output_path is None:
        output_path = PDF_EXPORT_DIR / (
            f"encaminhamento_{nome_seguro(destination_school.name, 'escola')}"
            f"_{len(students)}alunos.pdf"
        )
    
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Title'],
        fontSize=12,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=10,
        leading=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        textColor=white
    )
    
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    cell_center_style = ParagraphStyle(
        'TableCellCenter',
        parent=cell_style,
        alignment=TA_CENTER
    )
    
    elements = []
    
    title_text = (
        f"<b>Unidade Escolar de destino:</b> {destination_school.name}"
        f"                     <b>Turma:</b>  {class_name}"
        f"                                                                  <b>Nº de alunos encaminhados:</b> {len(students)}      / Oferta 20"
    )
    elements.append(Paragraph(title_text, title_style))
    elements.append(Paragraph("QUADRO DE ENCAMINHAMENTO DE ALUNOS 2025", subtitle_style))
    elements.append(Spacer(1, 6))
    
    headers = ["Nº", "NOME DO ALUNO", "ENDEREÇO", "UNIDADE DE ORIGEM"]
    table_data = [headers]
    for idx, student in enumerate(students, 1):
        table_data.append([
            str(idx),
            student.name,
            student.full_address,
            origin_school.name
        ])
    
    col_widths = [1.5*cm, 7*cm, 11*cm, 7*cm]
    
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (1, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('LINEBELOW', (0, 0), (-1, 0), 1, black),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        *[('BACKGROUND', (0, i), (-1, i), HexColor('#F2F2F2')) for i in range(2, len(table_data), 2)],
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 20))
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    elements.append(Paragraph("Data: _____/_____/______.", footer_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        "Secretário&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "Diretor ou Responsável pela Unidade de Ensino",
        footer_style
    ))
    
    doc.build(elements)
    return str(output_path)