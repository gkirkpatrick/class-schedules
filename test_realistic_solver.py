#!/usr/bin/env python
"""Test script for realistic solvable scenario."""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
django.setup()

from timetable.models import Scenario
from solver.engine import solve_scenario
from solver.assignment import assign_students


def main():
    """Test the realistic scenario."""
    print("=" * 60)
    print("Testing REALISTIC Scenario (Should SUCCEED!)")
    print("=" * 60)

    # Get the realistic scenario
    scenario = Scenario.objects.filter(
        school__name="Washington High School", status=Scenario.Status.DRAFT
    ).first()

    if not scenario:
        print("❌ No DRAFT scenario found for Washington High School")
        print("   Run: python create_demo_scenario.py --realistic")
        return

    from timetable.models import Section

    print(f"\n✓ Found scenario: {scenario.name} (ID: {scenario.id})")
    print(f"  School: {scenario.school.name}")
    print(f"  Students: {scenario.school.students.count()}")
    print(f"  Sections: {Section.objects.filter(course__school=scenario.school).count()}")

    # Run Stage A
    print("\n🔄 Running Stage A: Master Schedule (CP-SAT)...")
    success_a = solve_scenario(scenario.id)

    scenario.refresh_from_db()
    print(f"\n{'✅' if success_a else '❌'} Stage A: {scenario.status}")
    print(f"  Placements created: {scenario.placements.count()}")

    if not success_a:
        print(f"\nLogs:\n{scenario.logs}")
        return

    # Run Stage B
    print("\n🔄 Running Stage B: Student Assignment (MIP)...")
    success_b = assign_students(scenario.id)

    scenario.refresh_from_db()
    print(f"\n{'✅' if success_b else '❌'} Stage B: {'SUCCESS' if success_b else 'FAILED'}")
    print(f"  Student enrollments: {scenario.enrollments.count()}")

    if success_b:
        print("\n" + "=" * 60)
        print("🎉 BOTH STAGES SUCCEEDED!")
        print("=" * 60)
        print(f"\nResults:")
        print(f"  Placements: {scenario.placements.count()}")
        print(f"  Enrollments: {scenario.enrollments.count()}")
        print(f"  Students enrolled: {scenario.enrollments.values('student').distinct().count()}")
        print(f"\nView at: http://localhost:8000/scenarios/{scenario.id}/results/")
    else:
        print("\n" + "=" * 60)
        print("⚠️  Stage B Failed")
        print("=" * 60)
        print(f"\nLogs:\n{scenario.logs}")


if __name__ == "__main__":
    main()
