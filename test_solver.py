#!/usr/bin/env python
"""Quick test script to verify solver functionality."""

import os
import django

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
django.setup()

from core.models import School
from timetable.models import Scenario
from solver.engine import solve_scenario
from solver.assignment import assign_students


def main():
    """Test the solver with a simple scenario."""
    print("=" * 60)
    print("School Scheduler - Solver Test")
    print("=" * 60)

    # Get the test school
    school = School.objects.first()
    if not school:
        print("❌ No school found. Run: python manage.py seed_data")
        return

    print(f"\n✓ Found school: {school.name}")
    print(f"  - {school.cycle_days} days, {school.periods_per_day} periods/day")

    # Create a test scenario
    scenario = Scenario.objects.create(
        school=school,
        name="Test Scenario - Solver Demo",
        status=Scenario.Status.DRAFT
    )
    print(f"\n✓ Created scenario: {scenario.name} (ID: {scenario.id})")

    # Run Stage A: Master Schedule
    print("\n🔄 Running Stage A: Master Schedule (CP-SAT)...")
    print("   This may take a minute...")

    success_a = solve_scenario(scenario.id)

    # Reload scenario to get updated status
    scenario.refresh_from_db()

    if not success_a:
        print(f"\n❌ Stage A FAILED: {scenario.status}")
        print(f"\nLogs:\n{scenario.logs}")
        return

    print(f"✓ Stage A completed: {scenario.status}")
    placements_count = scenario.placements.count()
    print(f"  - Created {placements_count} placements")

    # Run Stage B: Student Assignment
    print("\n🔄 Running Stage B: Student Assignment (MIP)...")

    success_b = assign_students(scenario.id)
    scenario.refresh_from_db()

    if not success_b:
        print(f"\n❌ Stage B FAILED")
        print(f"\nLogs:\n{scenario.logs}")
        return

    print(f"✓ Stage B completed")
    enrollments_count = scenario.enrollments.count()
    print(f"  - Created {enrollments_count} student enrollments")

    # Show summary
    print("\n" + "=" * 60)
    print("✨ SUCCESS! Scenario solved")
    print("=" * 60)
    print(f"\nScenario ID: {scenario.id}")
    print(f"Status: {scenario.status}")
    print(f"Placements: {placements_count}")
    print(f"Student Enrollments: {enrollments_count}")
    print(f"\nView results at: http://localhost:8000/scenarios/{scenario.id}/results/")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
