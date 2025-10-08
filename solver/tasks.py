"""Celery tasks for running solvers asynchronously."""

from celery import shared_task

from .assignment import assign_students
from .engine import solve_scenario


@shared_task(bind=True)
def run_scenario_task(self, scenario_id: int) -> dict[str, any]:
    """
    Celery task to run the full scenario solve.

    This runs both Stage A (master schedule) and Stage B (student assignment).

    Args:
        scenario_id: ID of the scenario to solve

    Returns:
        Dictionary with success status and message
    """
    try:
        # Stage A: Master schedule with CP-SAT
        success_stage_a = solve_scenario(scenario_id)

        if not success_stage_a:
            return {
                "success": False,
                "message": "Master schedule solving failed (infeasible)",
            }

        # Stage B: Student assignment with MIP
        success_stage_b = assign_students(scenario_id)

        if not success_stage_b:
            return {
                "success": False,
                "message": "Student assignment failed (infeasible)",
            }

        return {
            "success": True,
            "message": "Scenario solved successfully - master schedule and student assignments complete",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error during solve: {str(e)}",
        }
