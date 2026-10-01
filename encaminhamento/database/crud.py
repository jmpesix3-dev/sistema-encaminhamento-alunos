from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, joinedload
from encaminhamento.database.models import (
    School, Class, Student, ForwardingBatch, BatchItem,
    StudentStatus, BatchStatus
)


# School CRUD
def create_school(session: Session, name: str, code: str = None, address: str = None,
                  phone: str = None, email: str = None,
                  is_origin: bool = True, is_destination: bool = True,
                  oferta: int = 0, latitude: float = None, longitude: float = None,
                  distrito: str = None, modalidade: str = None,
                  contato: str = None) -> School:
    school = School(
        name=name, code=code, address=address,
        phone=phone, email=email,
        is_origin=is_origin, is_destination=is_destination,
        oferta=oferta, latitude=latitude, longitude=longitude,
        distrito=distrito, modalidade=modalidade, contato=contato
    )
    session.add(school)
    session.flush()
    return school


def get_school(session: Session, school_id: int) -> Optional[School]:
    return session.get(School, school_id)


def get_school_by_name(session: Session, name: str) -> Optional[School]:
    return session.execute(select(School).where(School.name == name)).scalar_one_or_none()


def list_schools(session: Session, is_origin: bool = None, is_destination: bool = None) -> List[School]:
    stmt = select(School)
    if is_origin is not None:
        stmt = stmt.where(School.is_origin == is_origin)
    if is_destination is not None:
        stmt = stmt.where(School.is_destination == is_destination)
    return session.execute(stmt.order_by(School.name)).scalars().all()


def update_school(session: Session, school_id: int, **kwargs) -> Optional[School]:
    school = get_school(session, school_id)
    if school:
        for k, v in kwargs.items():
            if hasattr(school, k):
                setattr(school, k, v)
        school.updated_at = datetime.now()
        session.flush()
    return school


# Class CRUD
def create_class(session: Session, school_id: int, name: str, year: int, shift: str = None) -> Class:
    cls = Class(school_id=school_id, name=name, year=year, shift=shift)
    session.add(cls)
    session.flush()
    return cls


def list_classes(session: Session, school_id: int = None, year: int = None) -> List[Class]:
    stmt = select(Class).options(joinedload(Class.school))
    if school_id:
        stmt = stmt.where(Class.school_id == school_id)
    if year:
        stmt = stmt.where(Class.year == year)
    return session.execute(stmt.order_by(Class.year.desc(), Class.name)).scalars().all()


# Student CRUD
def create_student(session: Session, name: str, origin_school_id: int,
                   civil_name: str = None, address: str = None, reference_point: str = None,
                   origin_class_id: int = None,
                   destination_school_1_id: int = None,
                   destination_school_2_id: int = None,
                   status: StudentStatus = StudentStatus.DRAFT,
                   responsible_signature: bool = False) -> Student:
    student = Student(
        name=name, civil_name=civil_name, address=address, reference_point=reference_point,
        origin_school_id=origin_school_id, origin_class_id=origin_class_id,
        destination_school_1_id=destination_school_1_id,
        destination_school_2_id=destination_school_2_id,
        status=status, responsible_signature=responsible_signature
    )
    session.add(student)
    session.flush()
    return student


def get_student(session: Session, student_id: int) -> Optional[Student]:
    return session.execute(
        select(Student).options(
            joinedload(Student.origin_school),
            joinedload(Student.origin_class),
            joinedload(Student.destination_school_1),
            joinedload(Student.destination_school_2)
        ).where(Student.id == student_id)
    ).unique().scalar_one_or_none()


def list_students(session: Session,
                  origin_school_id: int = None,
                  destination_school_id: int = None,
                  origin_class_id: int = None,
                  status: StudentStatus = None,
                  search: str = None,
                  limit: int = 100,
                  offset: int = 0) -> List[Student]:
    stmt = select(Student).options(
        joinedload(Student.origin_school),
        joinedload(Student.origin_class),
        joinedload(Student.destination_school_1),
        joinedload(Student.destination_school_2)
    )
    if origin_school_id:
        stmt = stmt.where(Student.origin_school_id == origin_school_id)
    if destination_school_id:
        stmt = stmt.where(
            or_(
                Student.destination_school_1_id == destination_school_id,
                Student.destination_school_2_id == destination_school_id
            )
        )
    if origin_class_id:
        stmt = stmt.where(Student.origin_class_id == origin_class_id)
    if status:
        stmt = stmt.where(Student.status == status)
    if search:
        stmt = stmt.where(Student.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Student.name).limit(limit).offset(offset)
    return session.execute(stmt).unique().scalars().all()


def update_student(session: Session, student_id: int, **kwargs) -> Optional[Student]:
    student = get_student(session, student_id)
    if student:
        for k, v in kwargs.items():
            if hasattr(student, k):
                setattr(student, k, v)
        student.updated_at = datetime.now()
        session.flush()
    return student


def delete_student(session: Session, student_id: int) -> bool:
    student = session.get(Student, student_id)
    if student:
        session.delete(student)
        return True
    return False


# Batch CRUD
def create_batch(session: Session, origin_school_id: int, destination_school_id: int,
                 year: int, origin_class_id: int = None,
                 notes: str = None) -> ForwardingBatch:
    batch = ForwardingBatch(
        origin_school_id=origin_school_id,
        destination_school_id=destination_school_id,
        origin_class_id=origin_class_id,
        year=year,
        notes=notes
    )
    session.add(batch)
    session.flush()
    return batch


def get_batch(session: Session, batch_id: int) -> Optional[ForwardingBatch]:
    return session.execute(
        select(ForwardingBatch).options(
            joinedload(ForwardingBatch.origin_school),
            joinedload(ForwardingBatch.destination_school),
            joinedload(ForwardingBatch.origin_class),
            joinedload(ForwardingBatch.items).joinedload(BatchItem.student)
        ).where(ForwardingBatch.id == batch_id)
    ).unique().scalar_one_or_none()


def list_batches(session: Session,
                 origin_school_id: int = None,
                 destination_school_id: int = None,
                 year: int = None,
                 status: BatchStatus = None) -> List[ForwardingBatch]:
    stmt = select(ForwardingBatch).options(
        joinedload(ForwardingBatch.origin_school),
        joinedload(ForwardingBatch.destination_school),
        joinedload(ForwardingBatch.origin_class)
    )
    if origin_school_id:
        stmt = stmt.where(ForwardingBatch.origin_school_id == origin_school_id)
    if destination_school_id:
        stmt = stmt.where(ForwardingBatch.destination_school_id == destination_school_id)
    if year:
        stmt = stmt.where(ForwardingBatch.year == year)
    if status:
        stmt = stmt.where(ForwardingBatch.status == status)
    stmt = stmt.order_by(ForwardingBatch.created_at.desc())
    return session.execute(stmt).unique().scalars().all()


def add_students_to_batch(session: Session, batch_id: int, student_ids: List[int]) -> List[BatchItem]:
    batch = get_batch(session, batch_id)
    if not batch:
        return []
    
    existing = {item.student_id for item in batch.items}
    new_items = []
    seq = len(batch.items) + 1
    
    for student_id in student_ids:
        if student_id not in existing:
            item = BatchItem(batch_id=batch_id, student_id=student_id, sequence_number=seq)
            session.add(item)
            new_items.append(item)
            seq += 1
    
    batch.student_count = len(batch.items) + len(new_items)
    session.flush()
    return new_items


def update_batch_status(session: Session, batch_id: int, status: BatchStatus, pdf_path: str = None) -> Optional[ForwardingBatch]:
    batch = get_batch(session, batch_id)
    if batch:
        batch.status = status
        if pdf_path:
            batch.pdf_path = pdf_path
        if status == BatchStatus.SENT:
            batch.sent_at = datetime.now()
        batch.updated_at = datetime.now()
        session.flush()
    return batch


def get_students_for_batch(session: Session, batch_id: int) -> List[Student]:
    batch = get_batch(session, batch_id)
    if not batch:
        return []
    return [item.student for item in batch.items]


# Search helpers
def search_schools(session: Session, query: str, limit: int = 10) -> List[School]:
    stmt = select(School).where(
        or_(
            School.name.ilike(f"%{query}%"),
            School.code.ilike(f"%{query}%")
        )
    ).limit(limit)
    return session.execute(stmt).scalars().all()


def find_or_create_school(session: Session, name: str, **defaults) -> School:
    school = get_school_by_name(session, name)
    if not school:
        school = create_school(session, name, **defaults)
    return school