"""Views for timetable app."""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render

from core.models import School

from .models import Scenario


def school_list(request: HttpRequest) -> HttpResponse:
    """List all schools."""
    schools = School.objects.all()
    return render(request, "schools/list.html", {"schools": schools})


def school_detail(request: HttpRequest, school_id: int) -> HttpResponse:
    """Show school details with scenarios."""
    school = get_object_or_404(School, id=school_id)
    scenarios = school.scenarios.all()
    return render(
        request,
        "schools/detail.html",
        {"school": school, "scenarios": scenarios},
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
