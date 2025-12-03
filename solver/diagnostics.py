"""Diagnostics and feasibility reporting for solver."""

from typing import Any

from core.models import Room, Teacher
from timetable.models import Placement, Scenario, Section, StudentEnrollment


def generate_scenario_report(scenario: Scenario) -> dict[str, Any]:
    """
    Generate comprehensive diagnostics report for a scenario.

    Args:
        scenario: The scenario to analyze

    Returns:
        Dictionary with diagnostic information
    """
    report: dict[str, Any] = {
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "status": scenario.status,
        "school": scenario.school.name,
    }

    if scenario.status == Scenario.Status.SOLVED:
        report["placements"] = _analyze_placements(scenario)
        report["enrollments"] = _analyze_enrollments(scenario)
        report["utilization"] = _analyze_utilization(scenario)
        report["gaps"] = _analyze_gaps(scenario)
    elif scenario.status == Scenario.Status.INFEASIBLE:
        report["infeasibility_reasons"] = _analyze_infeasibility(scenario)

    return report


def _analyze_placements(scenario: Scenario) -> dict[str, Any]:
    """Analyze placement statistics."""
    placements = Placement.objects.filter(scenario=scenario).select_related("section__course", "teacher", "room")

    total_placements = placements.count()
    lab_placements = placements.filter(is_lab=True).count()

    # Count unique sections
    unique_sections = placements.values("section").distinct().count()

    return {
        "total_placements": total_placements,
        "lab_placements": lab_placements,
        "regular_placements": total_placements - lab_placements,
        "unique_sections": unique_sections,
    }


def _analyze_enrollments(scenario: Scenario) -> dict[str, Any]:
    """Analyze student enrollment statistics."""
    enrollments = StudentEnrollment.objects.filter(scenario=scenario)

    total_enrollments = enrollments.count()
    unique_students = enrollments.values("student").distinct().count()
    unique_sections = enrollments.values("section").distinct().count()

    avg_courses_per_student = total_enrollments / unique_students if unique_students > 0 else 0

    return {
        "total_enrollments": total_enrollments,
        "unique_students": unique_students,
        "sections_with_students": unique_sections,
        "avg_courses_per_student": round(avg_courses_per_student, 2),
    }


def _analyze_utilization(scenario: Scenario) -> dict[str, Any]:
    """Analyze resource utilization."""
    school = scenario.school
    placements = Placement.objects.filter(scenario=scenario)

    # Teacher utilization
    teachers = Teacher.objects.filter(school=school)
    teacher_loads = {}
    for teacher in teachers:
        load = placements.filter(teacher=teacher).count()
        max_load = teacher.effective_daily_cap * school.cycle_days
        utilization = (load / max_load * 100) if max_load > 0 else 0
        teacher_loads[teacher.id] = {
            "name": f"{teacher.first_name} {teacher.last_name}",
            "load": load,
            "max_load": max_load,
            "utilization_percent": round(utilization, 1),
        }

    # Room utilization
    rooms = Room.objects.filter(school=school)
    room_loads = {}
    for room in rooms:
        load = placements.filter(room=room).count()
        max_load = school.periods_per_day * school.cycle_days
        utilization = (load / max_load * 100) if max_load > 0 else 0
        room_loads[room.name] = {"load": load, "max_load": max_load, "utilization_percent": round(utilization, 1)}

    return {
        "teachers": teacher_loads,
        "rooms": room_loads,
    }


def _analyze_gaps(scenario: Scenario) -> dict[str, Any]:
    """Analyze gaps in student and teacher schedules."""
    # This is complex - count free periods between first and last class
    # Skip for MVP
    return {
        "analysis": "Gap analysis not yet implemented",
    }


def _analyze_infeasibility(scenario: Scenario) -> list[str]:
    """Analyze why a scenario might be infeasible."""
    reasons = []

    school = scenario.school
    sections = Section.objects.filter(course__school=school)

    # Check teacher capacity
    total_section_occurrences = sum(s.planned_count_per_week for s in sections)
    teachers = Teacher.objects.filter(school=school)
    total_teacher_capacity = sum(t.effective_daily_cap * school.cycle_days for t in teachers)

    if total_section_occurrences > total_teacher_capacity:
        reasons.append(
            f"Teacher capacity shortage: need {total_section_occurrences} slots but only have {total_teacher_capacity} available"
        )

    # Check room capacity
    rooms = Room.objects.filter(school=school)
    total_room_slots = len(rooms) * school.cycle_days * school.periods_per_day
    if total_section_occurrences > total_room_slots:
        reasons.append(
            f"Room capacity shortage: need {total_section_occurrences} slots but only have {total_room_slots} available"
        )

    # Check lab requirements
    lab_sections = sections.filter(course__is_lab=True)
    if lab_sections.exists():
        lab_rooms = rooms.filter(features__code="LAB").distinct()
        if not lab_rooms.exists():
            reasons.append("No LAB rooms available for lab courses")

    return reasons if reasons else ["Unknown infeasibility - check solver logs"]
