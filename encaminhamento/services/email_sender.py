import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional
from pathlib import Path
from dataclasses import dataclass
from encaminhamento.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    SMTP_USE_TLS, EMAIL_FROM
)


@dataclass
class EmailResult:
    success: bool
    message: str
    error: str = None


def send_email(
    to_emails: List[str],
    subject: str,
    body_text: str = None,
    body_html: str = None,
    attachments: List[str] = None,
    cc: List[str] = None,
    bcc: List[str] = None
) -> EmailResult:
    """
    Send email with optional attachments.
    
    Args:
        to_emails: List of recipient email addresses
        subject: Email subject
        body_text: Plain text body
        body_html: HTML body (optional)
        attachments: List of file paths to attach
        cc: CC recipients
        bcc: BCC recipients
    
    Returns:
        EmailResult with success status and message
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        return EmailResult(
            success=False,
            message="SMTP credentials not configured",
            error="Missing SMTP_USER or SMTP_PASSWORD in environment"
        )
    
    if not to_emails:
        return EmailResult(
            success=False,
            message="No recipients specified",
            error="to_emails list is empty"
        )
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM or SMTP_USER
        msg['To'] = ", ".join(to_emails)
        msg['Subject'] = subject
        
        if cc:
            msg['Cc'] = ", ".join(cc)
        if bcc:
            msg['Bcc'] = ", ".join(bcc)
        
        # Add body
        if body_text:
            msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        if body_html:
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))
        
        # Add attachments
        if attachments:
            for file_path in attachments:
                path = Path(file_path)
                if path.exists():
                    with open(path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{path.name}"'
                    )
                    msg.attach(part)
                else:
                    return EmailResult(
                        success=False,
                        message=f"Attachment not found: {file_path}",
                        error=f"File does not exist: {file_path}"
                    )
        
        # Send
        context = ssl.create_default_context()
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USE_TLS:
                server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            
            all_recipients = to_emails + (cc or []) + (bcc or [])
            server.sendmail(EMAIL_FROM or SMTP_USER, all_recipients, msg.as_string())
        
        return EmailResult(success=True, message=f"Email sent to {len(to_emails)} recipient(s)")
    
    except smtplib.SMTPAuthenticationError as e:
        return EmailResult(
            success=False,
            message="SMTP authentication failed",
            error=str(e)
        )
    except smtplib.SMTPConnectError as e:
        return EmailResult(
            success=False,
            message="Could not connect to SMTP server",
            error=str(e)
        )
    except Exception as e:
        return EmailResult(
            success=False,
            message=f"Failed to send email: {str(e)}",
            error=str(e)
        )


def send_batch_notification(
    batch_id: int,
    to_emails: List[str],
    pdf_path: str = None,
    custom_message: str = None,
    cc: List[str] = None,
    bcc: List[str] = None,
) -> EmailResult:
    """Send batch forwarding notification with PDF attachment."""
    with get_session() as session:
        from encaminhamento.database.crud import get_batch
        batch = get_batch(session, batch_id)
        if not batch:
            return EmailResult(
                success=False,
                message=f"Batch {batch_id} not found",
                error="Batch not found in database"
            )
        
        destination_school = batch.destination_school
        origin_school = batch.origin_school
        class_name = batch.origin_class.name if batch.origin_class else ""
        student_count = batch.student_count
    
    from encaminhamento.config import NOME_SISTEMA

    subject = f"{NOME_SISTEMA} - {destination_school.name} - {student_count} alunos"

    body_text = f"""
{NOME_SISTEMA}

Unidade Escolar de Destino: {destination_school.name}
Unidade Escolar de Origem: {origin_school.name}
Turma: {class_name}
Número de Alunos: {student_count}

{custom_message or 'Segue em anexo o quadro de encaminhamento dos alunos.'}

Atenciosamente,
{NOME_SISTEMA}
"""

    body_html = f"""
<html>
<body>
<h2>{NOME_SISTEMA}</h2>
<table>
<tr><td><b>Unidade Escolar de Destino:</b></td><td>{destination_school.name}</td></tr>
<tr><td><b>Unidade Escolar de Origem:</b></td><td>{origin_school.name}</td></tr>
<tr><td><b>Turma:</b></td><td>{class_name}</td></tr>
<tr><td><b>Número de Alunos:</b></td><td>{student_count}</td></tr>
</table>
<p>{custom_message or 'Segue em anexo o quadro de encaminhamento dos alunos.'}</p>
<hr>
<p><small>{NOME_SISTEMA}</small></p>
</body>
</html>
"""
    
    attachments = [pdf_path] if pdf_path and Path(pdf_path).exists() else None
    
    return send_email(
        to_emails=to_emails,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
        cc=cc,
        bcc=bcc,
    )


def test_smtp_connection() -> EmailResult:
    """Test SMTP connection and authentication."""
    if not SMTP_USER or not SMTP_PASSWORD:
        return EmailResult(
            success=False,
            message="SMTP credentials not configured",
            error="Missing SMTP_USER or SMTP_PASSWORD"
        )
    
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USE_TLS:
                server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
        return EmailResult(success=True, message="SMTP connection successful")
    except Exception as e:
        return EmailResult(
            success=False,
            message=f"SMTP connection failed: {str(e)}",
            error=str(e)
        )


# Import get_session for the email functions
from encaminhamento.database import get_session