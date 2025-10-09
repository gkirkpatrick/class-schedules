"""Views for timetable app."""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render

from core.models import School

from .models import Scenario, Section, Course


def school_list(request: HttpRequest) -> HttpResponse:
    """List all schools."""
    schools = School.objects.all()
    return render(request, "schools/list.html", {"schools": schools})


def school_detail(request: HttpRequest, school_id: int) -> HttpResponse:
    """Show school details with scenarios."""
    from collections import defaultdict
    from core.models import Teacher, Room, Student
    from timetable.models import Section, Course

    school = get_object_or_404(School, id=school_id)
    scenarios = school.scenarios.all()

    # Calculate summary stats
    from core.models import RoomFeature

    teachers = Teacher.objects.filter(school=school).order_by('last_name', 'first_name')
    rooms = Room.objects.filter(school=school).prefetch_related('features').order_by('name')
    room_count = rooms.count()
    room_features = RoomFeature.objects.filter(school=school).order_by('code')
    student_count = Student.objects.filter(school=school).count()
    sections = Section.objects.filter(course__school=school).exclude(course__code__startswith='LUNCH')
    section_count = sections.count()
    courses = Course.objects.filter(school=school).order_by('code')
    total_slots = school.cycle_days * school.periods_per_day

    # Calculate teacher candidate counts and overload
    teachers_data = []
    for teacher in teachers:
        candidate_sections = sections.filter(teacher_candidates=teacher)
        candidate_count = candidate_sections.count()
        overload = max(0, candidate_count - teacher.max_sections)
        teachers_data.append({
            'id': teacher.id,
            'first_name': teacher.first_name,
            'last_name': teacher.last_name,
            'email': teacher.email,
            'max_sections': teacher.max_sections,
            'daily_teaching_cap': teacher.daily_teaching_cap,
            'candidate_count': candidate_count,
            'overload': overload,
        })

    # Group sections by course and analyze feasibility
    courses_dict = defaultdict(list)
    for section in sections:
        courses_dict[section.course.code].append(section)

    courses_summary = []
    for course_code in sorted(courses_dict.keys()):
        course_sections = courses_dict[course_code]
        first_section = course_sections[0]
        course = first_section.course

        candidates = list(first_section.teacher_candidates.all())
        candidate_count = len(candidates)
        candidate_names = [f"{t.first_name[0]}.{t.last_name}" for t in candidates]

        # Check feasibility
        section_count_for_course = len(course_sections)
        total_capacity = sum(t.max_sections for t in candidates)
        is_feasible = candidate_count > 0 and total_capacity >= section_count_for_course

        if candidate_count == 0:
            feasibility_msg = "No candidates"
        elif total_capacity < section_count_for_course:
            shortfall = section_count_for_course - total_capacity
            feasibility_msg = f"Need {shortfall} more capacity"
        else:
            feasibility_msg = ""

        courses_summary.append({
            'code': course_code,
            'is_lab': course.is_lab,
            'section_count': section_count_for_course,
            'meets_per_week': course.meets_per_week,
            'candidate_count': candidate_count,
            'candidate_names': candidate_names,
            'is_feasible': is_feasible,
            'feasibility_msg': feasibility_msg,
        })

    lunch_end = school.lunch_window_start_period + school.lunch_window_span - 1

    # Prepare rooms data
    rooms_data = []
    for room in rooms:
        feature_codes = [f.code for f in room.features.all()]
        rooms_data.append({
            'id': room.id,
            'name': room.name,
            'capacity': room.capacity,
            'features': feature_codes,
        })

    # Prepare sections data with teacher and room candidates
    sections_data = []
    for section in sections.select_related('course').prefetch_related('teacher_candidates', 'room_candidates'):
        teacher_names = [f"{t.first_name[0]}.{t.last_name}" for t in section.teacher_candidates.all()]
        room_names = [r.name for r in section.room_candidates.all()]
        sections_data.append({
            'id': section.id,
            'course_code': section.course.code,
            'section_number': section.section_number,
            'planned_count_per_week': section.planned_count_per_week,
            'meets_per_week': section.course.meets_per_week,
            'capacity': section.course.capacity,
            'teacher_candidates': teacher_names,
            'teacher_candidate_ids': [t.id for t in section.teacher_candidates.all()],
            'room_candidates': room_names,
            'room_candidate_ids': [r.id for r in section.room_candidates.all()],
            'is_lab': section.course.is_lab,
        })

    return render(
        request,
        "schools/detail.html",
        {
            "school": school,
            "scenarios": scenarios,
            "teachers": teachers_data,
            "all_teachers": teachers,
            "teacher_count": len(teachers_data),
            "rooms": rooms_data,
            "room_features": room_features,
            "room_count": room_count,
            "sections": sections_data,
            "courses": courses,
            "student_count": student_count,
            "section_count": section_count,
            "total_slots": total_slots,
            "courses_summary": courses_summary,
            "lunch_end": lunch_end,
        },
    )


def scenario_create(request: HttpRequest, school_id: int) -> HttpResponse:
    """Create/edit scenario configuration (splash page)."""
    school = get_object_or_404(School, id=school_id)
    # TODO: Implement form handling
    return render(request, "scenarios/create.html", {"school": school})


def scenario_detail(request: HttpRequest, scenario_id: int) -> HttpResponse:
    """Show scenario details."""
    scenario = get_object_or_404(Scenario, id=scenario_id)
    return render(request, "scenarios/detail.html", {"scenario": scenario})


def scenario_results(request: HttpRequest, scenario_id: int) -> HttpResponse:
    """Show scenario results with schedules."""
    from collections import defaultdict
    from core.models import Teacher

    scenario = get_object_or_404(Scenario, id=scenario_id)

    # Fetch placements ordered by day and period
    placements = scenario.placements.select_related(
        "section__course", "teacher", "room"
    ).order_by("day", "period")

    # Fetch enrollments
    enrollments = scenario.enrollments.select_related(
        "student", "section__course"
    ).order_by("student__last_name", "day", "period")

    # Build teacher schedules
    teachers = Teacher.objects.filter(school=scenario.school).order_by("last_name", "first_name")

    # Get dimensions for grid
    num_days = scenario.school.cycle_days
    num_periods = scenario.school.periods_per_day

    # Build teacher schedule data structure for template
    teacher_schedule_data = []

    for teacher in teachers:
        # Create grid: day -> period -> placement
        schedule_grid = defaultdict(dict)
        teacher_placements = placements.filter(teacher=teacher)

        for placement in teacher_placements:
            schedule_grid[placement.day][placement.period] = placement

        # Build grid rows (periods) with cells (days)
        grid = []
        for period in range(num_periods):
            cells = []
            for day in range(num_days):
                placement = schedule_grid.get(day, {}).get(period)
                if placement:
                    cells.append({
                        'course': placement.section.course.code,
                        'section_number': placement.section.section_number,
                        'room': placement.room.name,
                        'is_lab': placement.is_lab,
                    })
                else:
                    cells.append(None)
            grid.append({
                'period_num': period + 1,
                'cells': cells
            })

        teacher_schedule_data.append({
            'teacher': teacher,
            'total_periods': teacher_placements.count(),
            'days': list(range(1, num_days + 1)),
            'grid': grid
        })

    return render(
        request,
        "scenarios/results.html",
        {
            "scenario": scenario,
            "placements": placements,
            "enrollments": enrollments,
            "teacher_schedule_data": teacher_schedule_data,
        },
    )


def api_scenario_status(request: HttpRequest, scenario_id: int) -> JsonResponse:
    """Get scenario status (for polling)."""
    scenario = get_object_or_404(Scenario, id=scenario_id)
    return JsonResponse(
        {
            "status": scenario.status,
            "message": scenario.logs[-500:] if scenario.logs else "",
        }
    )


def api_scenario_run(request: HttpRequest, scenario_id: int) -> HttpResponse:
    """Trigger scenario solver run."""
    from django.shortcuts import redirect

    if request.method != "POST":
        return HttpResponse("POST required", status=405)

    scenario = get_object_or_404(Scenario, id=scenario_id)

    # Clear previous results if re-running
    if scenario.status in [Scenario.Status.SOLVED, Scenario.Status.INFEASIBLE, Scenario.Status.FAILED]:
        scenario.placements.all().delete()
        scenario.enrollments.all().delete()
        scenario.logs = ""
        scenario.status = Scenario.Status.DRAFT
        scenario.save()

    # Import solver functions
    from solver.engine import solve_scenario
    from solver.assignment import assign_students

    # Run synchronously (for demo - in production would use Celery)
    try:
        # Stage A: Master Schedule
        solve_scenario(scenario_id)

        # Stage B: Student Assignment
        assign_students(scenario_id)
    except Exception as e:
        scenario.refresh_from_db()
        scenario.logs += f"\n\nError: {str(e)}"
        scenario.status = Scenario.Status.FAILED
        scenario.save()

    # Redirect back to scenario detail
    return redirect("timetable:scenario_detail", scenario_id=scenario_id)


def api_teacher_add(request: HttpRequest, school_id: int) -> JsonResponse:
    """API endpoint: Add new teacher."""
    import json
    from core.models import Teacher

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    school = get_object_or_404(School, id=school_id)

    try:
        data = json.loads(request.body)

        teacher = Teacher.objects.create(
            school=school,
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            subject=data.get("subject", ""),
            max_sections=int(data.get("max_sections", 3)),
            daily_teaching_cap=int(data.get("daily_teaching_cap", 5)),
        )

        return JsonResponse({
            "success": True,
            "teacher": {
                "id": teacher.id,
                "first_name": teacher.first_name,
                "last_name": teacher.last_name,
                "email": teacher.email,
                "max_sections": teacher.max_sections,
                "daily_teaching_cap": teacher.daily_teaching_cap,
            }
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_teacher_update(request: HttpRequest, teacher_id: int) -> JsonResponse:
    """API endpoint: Update teacher settings."""
    import json
    from core.models import Teacher

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    teacher = get_object_or_404(Teacher, id=teacher_id)

    try:
        data = json.loads(request.body)

        if "max_sections" in data:
            teacher.max_sections = int(data["max_sections"])

        if "daily_teaching_cap" in data:
            teacher.daily_teaching_cap = int(data["daily_teaching_cap"])

        teacher.save()

        return JsonResponse({
            "success": True,
            "teacher": {
                "id": teacher.id,
                "max_sections": teacher.max_sections,
                "daily_teaching_cap": teacher.daily_teaching_cap,
            }
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_room_add(request: HttpRequest, school_id: int) -> JsonResponse:
    """API endpoint: Add new room."""
    import json
    from core.models import Room, RoomFeature

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    school = get_object_or_404(School, id=school_id)

    try:
        data = json.loads(request.body)

        room = Room.objects.create(
            school=school,
            name=data["name"],
            capacity=int(data["capacity"]),
        )

        # Add features if provided
        if "features" in data and data["features"]:
            features = RoomFeature.objects.filter(id__in=data["features"])
            room.features.set(features)

        return JsonResponse({
            "success": True,
            "room": {
                "id": room.id,
                "name": room.name,
                "capacity": room.capacity,
            }
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_room_update(request: HttpRequest, room_id: int) -> JsonResponse:
    """API endpoint: Update room settings."""
    import json
    from core.models import Room

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    room = get_object_or_404(Room, id=room_id)

    try:
        data = json.loads(request.body)

        if "capacity" in data:
            room.capacity = int(data["capacity"])

        room.save()

        return JsonResponse({
            "success": True,
            "room": {
                "id": room.id,
                "capacity": room.capacity,
            }
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_teacher_delete(request: HttpRequest, teacher_id: int) -> JsonResponse:
    """API endpoint: Delete teacher."""
    from core.models import Teacher

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    teacher = get_object_or_404(Teacher, id=teacher_id)

    try:
        teacher.delete()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_room_delete(request: HttpRequest, room_id: int) -> JsonResponse:
    """API endpoint: Delete room."""
    from core.models import Room

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    room = get_object_or_404(Room, id=room_id)

    try:
        room.delete()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_section_add(request: HttpRequest, school_id: int) -> JsonResponse:
    """API endpoint: Add new section."""
    import json
    from core.models import Teacher, Room

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    school = get_object_or_404(School, id=school_id)

    try:
        data = json.loads(request.body)

        course = Course.objects.get(id=data["course_id"], school=school)

        section = Section.objects.create(
            course=course,
            section_number=int(data["section_number"]),
            planned_count_per_week=course.meets_per_week,
        )

        # Add teacher candidates if provided
        if "teacher_candidates" in data and data["teacher_candidates"]:
            teachers = Teacher.objects.filter(id__in=data["teacher_candidates"], school=school)
            section.teacher_candidates.set(teachers)

        # Add all rooms as candidates by default
        rooms = Room.objects.filter(school=school)
        section.room_candidates.set(rooms)

        return JsonResponse({
            "success": True,
            "section": {
                "id": section.id,
                "course_code": course.code,
                "section_number": section.section_number,
            }
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_section_delete(request: HttpRequest, section_id: int) -> JsonResponse:
    """API endpoint: Delete section."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    section = get_object_or_404(Section, id=section_id)

    try:
        section.delete()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


def api_scenario_precheck(request: HttpRequest, scenario_id: int) -> JsonResponse:
    """API endpoint: Run pre-check diagnostics and return JSON report."""
    from timetable.precheck import run_precheck

    scenario = get_object_or_404(Scenario, id=scenario_id)
    report = run_precheck(scenario.school.id)

    return JsonResponse(report.to_dict())


def scenario_precheck_html(request: HttpRequest, scenario_id: int) -> HttpResponse:
    """HTML partial: Render pre-check report as HTML."""
    from timetable.precheck import run_precheck

    scenario = get_object_or_404(Scenario, id=scenario_id)
    report = run_precheck(scenario.school.id)

    return render(
        request,
        "scenarios/precheck_report.html",
        {"scenario": scenario, "report": report},
    )


def scenario_precheck_export(
    request: HttpRequest, scenario_id: int, format: str
) -> HttpResponse:
    """Export pre-check report in various formats (json, csv, markdown)."""
    from timetable.precheck import run_precheck

    scenario = get_object_or_404(Scenario, id=scenario_id)
    report = run_precheck(scenario.school.id)

    if format == "json":
        return JsonResponse(report.to_dict())
    elif format == "csv":
        response = HttpResponse(report.to_csv(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="precheck_{scenario_id}.csv"'
        )
        return response
    elif format == "markdown":
        response = HttpResponse(report.to_markdown(), content_type="text/markdown")
        response["Content-Disposition"] = (
            f'attachment; filename="precheck_{scenario_id}.md"'
        )
        return response
    else:
        return HttpResponse("Invalid format", status=400)


def api_scenario_export(request: HttpRequest, scenario_id: int) -> JsonResponse:
    """Export scenario configuration and results as JSON."""
    scenario = get_object_or_404(Scenario, id=scenario_id)
    # TODO: Serialize scenario data
    return JsonResponse(
        {
            "id": scenario.id,
            "name": scenario.name,
            "status": scenario.status,
            "config": scenario.config,
        }
    )
