from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from encaminhamento.database import get_session
from encaminhamento.database.crud import list_schools, list_students, update_student
from encaminhamento.database.models import School, Student, StudentStatus
from encaminhamento.services.geocoding import haversine_distance, get_geocoding_service


@dataclass
class AllocationResult:
    """Resultado de um aluno na alocacao."""
    student_id: int
    student_name: str
    original_choice_1_id: int
    original_choice_2_id: int
    allocated_school_id: Optional[int]
    allocated_school_name: Optional[str]
    distance_km: Optional[float]
    status: str  # allocated ou sem_vaga
    priority: int


@dataclass
class AllocationSummary:
    """Resumo de uma execucao da alocacao."""
    total_students: int
    allocated: int
    waitlist: int
    no_address: int
    no_capacity: int
    by_school: Dict[int, Dict]  # school_id -> {allocated, capacity, students}
    results: List[AllocationResult]


class AllocationService:
    """Aloca alunos nas escolas por proximidade e capacidade."""

    def __init__(self):
        self.geocoding = get_geocoding_service()
        # True enquanto roda uma simulacao (nao grava no banco)
        self.preview = False

    def _get_student_distance_to_school(
        self,
        student: Student,
        school: School,
        referencia: School = None,
    ) -> Optional[float]:
        """
        Distancia do aluno ate a escola, em km.

        Quando o aluno nao tem coordenada, usa a da escola de referencia
        (normalmente a 1a opcao dele) como aproximacao.
        """
        lat_a, lon_a = student.latitude, student.longitude
        if lat_a is None or lon_a is None:
            if referencia is None:
                return None
            lat_a, lon_a = referencia.latitude, referencia.longitude
            if lat_a is None or lon_a is None:
                return None

        if school.latitude is None or school.longitude is None:
            return None

        return haversine_distance(lat_a, lon_a, school.latitude, school.longitude)
    
    def _allocate_for_school(
        self,
        school: School,
        candidatos: List[Student],
        session,
        referencia_por_aluno: Dict[int, School] = None,
    ) -> Tuple[List[AllocationResult], List[Student]]:
        """
        Aloca os candidatos mais proximos ate preencher a oferta da escola.

        referencia_por_aluno: quando o aluno nao tem coordenada, usa a posicao
        da escola indicada nele (normalmente a 1a opcao) como aproximacao.
        """
        com_coordenada = []
        sem_coordenada = []

        for aluno in candidatos:
            referencia = (referencia_por_aluno or {}).get(aluno.id)
            dist = self._get_student_distance_to_school(aluno, school, referencia)
            if dist is None:
                sem_coordenada.append(aluno)
            else:
                com_coordenada.append((aluno, dist))

        # O mais proximo primeiro
        com_coordenada.sort(key=lambda par: par[1])

        vagas = school.oferta or 0
        alocados = []
        excedente = list(sem_coordenada)

        for i, (aluno, dist) in enumerate(com_coordenada):
            if i >= vagas:
                excedente.append(aluno)
                continue

            alocados.append(AllocationResult(
                student_id=aluno.id,
                student_name=aluno.name,
                original_choice_1_id=aluno.destination_school_1_id,
                original_choice_2_id=aluno.destination_school_2_id,
                allocated_school_id=school.id,
                allocated_school_name=school.name,
                distance_km=round(dist, 2),
                status="allocated",
                priority=i + 1,
            ))

            if not self.preview:
                update_student(
                    session,
                    aluno.id,
                    allocated_school_id=school.id,
                    allocation_status="allocated",
                    allocation_priority=i + 1,
                )

        return alocados, excedente
    
    def run_allocation(self, preview: bool = False) -> AllocationSummary:
        """
        Executa a alocacao por proximidade e capacidade.

        1. Para cada escola, pega os alunos que a indicaram como 1a opcao
        2. Ordena por distancia (o mais perto primeiro) e aloca ate a oferta
        3. O excedente passa para a 2a opcao
        4. Repete o processo nas 2as opcoes
        5. O que sobrar fica sem vaga

        preview=True apenas simula, sem gravar no banco.
        """
        all_allocated = []
        all_no_address = []
        by_school = defaultdict(lambda: {'allocated': 0, 'capacity': 0, 'students': []})

        self.preview = preview

        try:
            with get_session() as session:
                dest_schools = [
                    s for s in list_schools(session, is_destination=True)
                    if (s.oferta or 0) > 0
                ]

                if not dest_schools:
                    return AllocationSummary(
                        total_students=0, allocated=0, waitlist=0,
                        no_address=0, no_capacity=0,
                        by_school={}, results=[],
                    )

                alunos = list_students(session, status=StudentStatus.DRAFT, limit=5000)
                escola_por_id = {s.id: s for s in dest_schools}

                # Separa por preferencia
                por_primeira = defaultdict(list)
                por_segunda = defaultdict(list)
                for aluno in alunos:
                    if aluno.destination_school_1_id:
                        por_primeira[aluno.destination_school_1_id].append(aluno)
                    if aluno.destination_school_2_id:
                        por_segunda[aluno.destination_school_2_id].append(aluno)

                ja_alocados = set()

                # ---- 1a opcao: os mais perto ate lotar a escola ----
                for escola in dest_schools:
                    candidatos = [
                        a for a in por_primeira.get(escola.id, [])
                        if a.id not in ja_alocados
                    ]
                    if not candidatos:
                        continue

                    by_school[escola.id]['capacity'] = escola.oferta
                    by_school[escola.id]['school_name'] = escola.name

                    alocados, excedente = self._allocate_for_school(escola, candidatos, session)

                    for r in alocados:
                        all_allocated.append(r)
                        ja_alocados.add(r.student_id)
                        by_school[escola.id]['allocated'] += 1
                        by_school[escola.id]['students'].append({
                            'student_id': r.student_id,
                            'name': r.student_name,
                            'distance_km': r.distance_km,
                            'choice': '1a',
                        })

                    # O que nao coube tenta a 2a opcao
                    for aluno in excedente:
                        if aluno.destination_school_2_id:
                            por_segunda[aluno.destination_school_2_id].append(aluno)
                        else:
                            all_no_address.append(aluno)

                # ---- 2a opcao: sobra de vaga de quem nao lotou ----
                # Alunos sem coordenada sao posicionados pela 1a opcao
                referencia = {}
                for lista in por_segunda.values():
                    for aluno in lista:
                        if aluno.destination_school_1_id:
                            ref = escola_por_id.get(aluno.destination_school_1_id)
                            if ref and ref.latitude is not None:
                                referencia[aluno.id] = ref

                for escola in dest_schools:
                    vagas = (escola.oferta or 0) - by_school[escola.id]['allocated']
                    if vagas <= 0:
                        continue

                    candidatos = [
                        a for a in por_segunda.get(escola.id, [])
                        if a.id not in ja_alocados
                    ]
                    if not candidatos:
                        continue

                    oferta_original = escola.oferta
                    escola.oferta = vagas
                    by_school[escola.id]['capacity'] = oferta_original
                    by_school[escola.id]['school_name'] = escola.name

                    alocados, excedente = self._allocate_for_school(
                        escola, candidatos, session, referencia
                    )

                    escola.oferta = oferta_original

                    for r in alocados:
                        # Nunca aloca o mesmo aluno duas vezes
                        if r.student_id in ja_alocados:
                            continue
                        all_allocated.append(r)
                        ja_alocados.add(r.student_id)
                        by_school[escola.id]['allocated'] += 1
                        by_school[escola.id]['students'].append({
                            'student_id': r.student_id,
                            'name': r.student_name,
                            'distance_km': r.distance_km,
                            'choice': '2a',
                        })

                    all_no_address.extend(excedente)

                # Quem nao entrou em nenhuma escola
                for aluno in alunos:
                    if aluno.id not in ja_alocados:
                        all_no_address.append(aluno)

                # Garante que nenhum aluno apareca duas vezes
                vistos = set()
                sem_vaga = []
                for aluno in all_no_address:
                    if aluno.id in ja_alocados or aluno.id in vistos:
                        continue
                    vistos.add(aluno.id)
                    sem_vaga.append(aluno)
                all_no_address = sem_vaga

                # Extrai os dados ainda dentro da sessao
                no_address_data = [{
                    'student_id': a.id,
                    'student_name': a.name,
                    'original_choice_1_id': a.destination_school_1_id,
                    'original_choice_2_id': a.destination_school_2_id,
                } for a in all_no_address]

                # Nenhum aluno pode ter duas alocacoes
                unicos = {}
                for r in all_allocated:
                    unicos.setdefault(r.student_id, r)
                all_allocated = list(unicos.values())

        finally:
            self.preview = False

        # Monta o resumo
        total = len(all_allocated) + len(all_no_address)

        resultados_sem_vaga = [
            AllocationResult(
                student_id=d['student_id'],
                student_name=d['student_name'],
                original_choice_1_id=d['original_choice_1_id'],
                original_choice_2_id=d['original_choice_2_id'],
                allocated_school_id=None,
                allocated_school_name=None,
                distance_km=None,
                status="sem_vaga",
                priority=0
            ) for d in no_address_data
        ]

        return AllocationSummary(
            total_students=total,
            allocated=len(all_allocated),
            waitlist=0,
            no_address=len(all_no_address),
            no_capacity=0,
            by_school={k: v for k, v in by_school.items() if v.get('school_name')},
            results=all_allocated + resultados_sem_vaga,
        )
    
    def reset_allocations(self) -> int:
        """Reset all student allocations to pending status."""
        with get_session() as session:
            from sqlalchemy import update
            from encaminhamento.database.models import Student
            stmt = update(Student).where(
                Student.allocation_status.in_(["allocated", "waitlist"])
            ).values(
                allocated_school_id=None,
                allocation_status="pending",
                allocation_priority=None
            )
            result = session.execute(stmt)
            return result.rowcount
    
    def get_allocation_stats(self) -> Dict:
        """Get current allocation statistics."""
        with get_session() as session:
            from sqlalchemy import func, select
            from encaminhamento.database.models import Student
            
            total = session.execute(select(func.count(Student.id))).scalar() or 0
            allocated = session.execute(
                select(func.count(Student.id)).where(Student.allocation_status == "allocated")
            ).scalar() or 0
            waitlist = session.execute(
                select(func.count(Student.id)).where(Student.allocation_status == "waitlist")
            ).scalar() or 0
            pending = session.execute(
                select(func.count(Student.id)).where(Student.allocation_status == "pending")
            ).scalar() or 0
            
            # By school
            by_school = {}
            schools = list_schools(session, is_destination=True)
            for school in schools:
                count = session.execute(
                    select(func.count(Student.id)).where(
                        Student.allocated_school_id == school.id
                    )
                ).scalar() or 0
                if count > 0:
                    by_school[school.id] = {
                        'school_name': school.name,
                        'allocated': count,
                        'capacity': school.oferta
                    }
            
            return {
                'total': total,
                'allocated': allocated,
                'waitlist': waitlist,
                'pending': pending,
                'by_school': by_school
            }


# Singleton instance
_allocation_service = None

def get_allocation_service() -> AllocationService:
    """Get singleton allocation service instance."""
    global _allocation_service
    if _allocation_service is None:
        _allocation_service = AllocationService()
    return _allocation_service