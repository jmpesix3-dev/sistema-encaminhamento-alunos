from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum,
    UniqueConstraint, Index, Boolean, func, Float
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class StudentStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    SENT = "sent"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class BatchStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    SENT = "sent"
    COMPLETED = "completed"


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), unique=True, nullable=True)
    address = Column(Text, nullable=True)
    distrito = Column(String(50), nullable=True)
    modalidade = Column(String(100), nullable=True)
    contato = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(100), nullable=True)
    is_origin = Column(Boolean, default=True)
    is_destination = Column(Boolean, default=True)
    oferta = Column(Integer, default=0)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    origin_classes = relationship("Class", foreign_keys="Class.school_id", back_populates="school")
    destination_batches = relationship("ForwardingBatch", foreign_keys="ForwardingBatch.destination_school_id", back_populates="destination_school")
    origin_batches = relationship("ForwardingBatch", foreign_keys="ForwardingBatch.origin_school_id", back_populates="origin_school")

    def __repr__(self):
        return f"<School(id={self.id}, name='{self.name}', oferta={self.oferta})>"


class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    name = Column(String(100), nullable=False)
    year = Column(Integer, nullable=False)
    shift = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    school = relationship("School", back_populates="origin_classes")
    students = relationship("Student", back_populates="origin_class")

    __table_args__ = (
        UniqueConstraint("school_id", "name", "year", name="uq_school_class_year"),
    )

    def __repr__(self):
        return f"<Class(id={self.id}, name='{self.name}', year={self.year})>"


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    civil_name = Column(String(200), nullable=True)
    address = Column(Text, nullable=True)
    reference_point = Column(Text, nullable=True)
    origin_school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    origin_class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    destination_school_1_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    destination_school_2_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    status = Column(SQLEnum(StudentStatus), default=StudentStatus.DRAFT, nullable=False)
    responsible_signature = Column(Boolean, default=False)
    # Alocação automática
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    allocated_school_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    allocation_status = Column(String(20), default="pending")  # pending, allocated, waitlist
    allocation_priority = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    origin_school = relationship("School", foreign_keys=[origin_school_id])
    origin_class = relationship("Class", back_populates="students")
    destination_school_1 = relationship("School", foreign_keys=[destination_school_1_id])
    destination_school_2 = relationship("School", foreign_keys=[destination_school_2_id])
    allocated_school = relationship("School", foreign_keys=[allocated_school_id])
    batch_items = relationship("BatchItem", back_populates="student")

    __table_args__ = (
        Index("ix_student_origin_school", "origin_school_id"),
        Index("ix_student_status", "status"),
        Index("ix_student_name", "name"),
        Index("ix_student_allocated_school", "allocated_school_id"),
        Index("ix_student_allocation_status", "allocation_status"),
    )

    def __repr__(self):
        return f"<Student(id={self.id}, name='{self.name}', status='{self.status}', allocated='{self.allocated_school_id}')>"

    @property
    def full_address(self):
        parts = [self.address]
        if self.reference_point:
            parts.append(f"Ref: {self.reference_point}")
        return " - ".join(filter(None, parts))


class ForwardingBatch(Base):
    __tablename__ = "forwarding_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    origin_school_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    destination_school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    origin_class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    year = Column(Integer, nullable=False)
    student_count = Column(Integer, default=0)
    status = Column(SQLEnum(BatchStatus), default=BatchStatus.DRAFT, nullable=False)
    pdf_path = Column(String(500), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    origin_school = relationship("School", foreign_keys=[origin_school_id], back_populates="origin_batches")
    destination_school = relationship("School", foreign_keys=[destination_school_id], back_populates="destination_batches")
    origin_class = relationship("Class", foreign_keys=[origin_class_id])
    items = relationship("BatchItem", back_populates="batch", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ForwardingBatch(id={self.id}, year={self.year}, students={self.student_count})>"


class BatchItem(Base):
    __tablename__ = "batch_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("forwarding_batches.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.now())

    batch = relationship("ForwardingBatch", back_populates="items")
    student = relationship("Student", back_populates="batch_items")

    __table_args__ = (
        UniqueConstraint("batch_id", "student_id", name="uq_batch_student"),
        UniqueConstraint("batch_id", "sequence_number", name="uq_batch_sequence"),
    )

    def __repr__(self):
        return f"<BatchItem(batch_id={self.batch_id}, student_id={self.student_id}, seq={self.sequence_number})>"