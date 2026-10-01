from typing import List
from encaminhamento.database.models import StudentStatus, BatchStatus
from encaminhamento.database.crud import (
    get_student, update_student, get_batch, update_batch_status,
    get_students_for_batch
)
from encaminhamento.database import get_session


class StatusTransition:
    """Valid status transitions for students and batches."""
    
    STUDENT_TRANSITIONS = {
        StudentStatus.DRAFT: [StudentStatus.PENDING, StudentStatus.CANCELLED],
        StudentStatus.PENDING: [StudentStatus.SENT, StudentStatus.CANCELLED, StudentStatus.DRAFT],
        StudentStatus.SENT: [StudentStatus.CONFIRMED, StudentStatus.CANCELLED],
        StudentStatus.CONFIRMED: [],
        StudentStatus.CANCELLED: [StudentStatus.DRAFT],
    }
    
    BATCH_TRANSITIONS = {
        BatchStatus.DRAFT: [BatchStatus.GENERATED, BatchStatus.COMPLETED],
        BatchStatus.GENERATED: [BatchStatus.SENT, BatchStatus.DRAFT],
        BatchStatus.SENT: [BatchStatus.COMPLETED],
        BatchStatus.COMPLETED: [],
    }
    
    @classmethod
    def can_transition_student(cls, from_status: StudentStatus, to_status: StudentStatus) -> bool:
        return to_status in cls.STUDENT_TRANSITIONS.get(from_status, [])
    
    @classmethod
    def can_transition_batch(cls, from_status: BatchStatus, to_status: BatchStatus) -> bool:
        return to_status in cls.BATCH_TRANSITIONS.get(from_status, [])


def transition_student_status(student_id: int, new_status: StudentStatus) -> bool:
    """Transition a student to a new status if valid."""
    with get_session() as session:
        student = get_student(session, student_id)
        if not student:
            return False
        
        if StatusTransition.can_transition_student(student.status, new_status):
            update_student(session, student_id, status=new_status)
            return True
        return False


def auto_advance_batch_status(batch_id: int) -> BatchStatus:
    """
    Automatically advance batch status based on student statuses.
    - If all students are SENT -> batch becomes SENT
    - If all students are CONFIRMED -> batch becomes COMPLETED
    """
    with get_session() as session:
        batch = get_batch(session, batch_id)
        if not batch:
            return batch.status
        
        students = get_students_for_batch(session, batch_id)
        if not students:
            return batch.status
        
        # Extract statuses while session is open
        statuses = [s.status for s in students]
        
        batch_status = batch.status
    
    if all(s == StudentStatus.CONFIRMED for s in statuses):
        new_status = BatchStatus.COMPLETED
    elif all(s in [StudentStatus.SENT, StudentStatus.CONFIRMED] for s in statuses):
        new_status = BatchStatus.SENT
    elif all(s == StudentStatus.PENDING for s in statuses):
        new_status = BatchStatus.GENERATED
    else:
        new_status = BatchStatus.DRAFT
    
    if new_status != batch_status and StatusTransition.can_transition_batch(batch_status, new_status):
        with get_session() as session:
            update_batch_status(session, batch_id, new_status)
        return new_status
    
    return batch_status


def get_status_summary(batch_id: int) -> dict:
    """Get status summary for a batch."""
    with get_session() as session:
        batch = get_batch(session, batch_id)
        if not batch:
            return {}
        
        students = get_students_for_batch(session, batch_id)
        
        # Extract student data while session is open
        student_statuses = []
        for s in students:
            student_statuses.append({
                "id": s.id,
                "status": s.status,
            })
        
        # Batch status and other info
        batch_status = batch.status
        batch_id_val = batch.id
    
    # Build summary using extracted data
    summary = {
        "batch_id": batch_id_val,
        "batch_status": batch_status.value,
        "total_students": len(student_statuses),
        "by_status": {},
        "can_send_emails": False,
        "can_generate_pdf": False,
    }
    
    for status in StudentStatus:
        summary["by_status"][status.value] = sum(1 for s in student_statuses if s["status"] == status)
    
    # Can send emails if batch is GENERATED or SENT and has pending students
    if batch_status in [BatchStatus.GENERATED, BatchStatus.SENT]:
        pending = summary["by_status"].get(StudentStatus.PENDING.value, 0)
        sent = summary["by_status"].get(StudentStatus.SENT.value, 0)
        if pending > 0 or sent > 0:
            summary["can_send_emails"] = True
    
    # Can generate PDF if batch is DRAFT or GENERATED
    if batch_status in [BatchStatus.DRAFT, BatchStatus.GENERATED]:
        summary["can_generate_pdf"] = True
    
    return summary


def bulk_transition_students(student_ids: List[int], new_status: StudentStatus) -> dict:
    """Transition multiple students at once."""
    results = {"success": [], "failed": []}
    
    with get_session() as session:
        for student_id in student_ids:
            student = get_student(session, student_id)
            if student and StatusTransition.can_transition_student(student.status, new_status):
                update_student(session, student_id, status=new_status)
                results["success"].append(student_id)
            else:
                results["failed"].append(student_id)
    
    return results