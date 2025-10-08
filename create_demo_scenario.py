#!/usr/bin/env python
"""Create a demo scenario for testing the UI."""

import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
django.setup()

from core.models import School
from timetable.models import Scenario


def main():
    # Check for --realistic flag
    realistic = "--realistic" in sys.argv or "-r" in sys.argv

    if realistic:
        school = School.objects.filter(name="Washington High School").first()
        if not school:
            print("❌ Washington High School not found.")
            print("   Run: python manage.py seed_realistic")
            exit(1)
        expected_result = "BOTH Stage A and Stage B should SUCCEED! 🎉"
        scenario_name = "Realistic Demo - Full Success"
    else:
        school = School.objects.filter(name="Lincoln High School").first()
        if not school:
            print("❌ Lincoln High School not found.")
            print("   Run: python manage.py seed_data")
            exit(1)
        expected_result = "Stage A will succeed, Stage B will be INFEASIBLE (intentional)"
        scenario_name = "Demo Scenario - UI Test"

    # Check if there's already a DRAFT scenario for this school
    existing = Scenario.objects.filter(
        school=school, status=Scenario.Status.DRAFT
    ).first()

    if existing:
        print(f"✓ Found existing DRAFT scenario: {existing.name} (ID: {existing.id})")
        print(f"  School: {school.name}")
        print(f"\nView at: http://localhost:8000/scenarios/{existing.id}/")
    else:
        scenario = Scenario.objects.create(
            school=school,
            name=scenario_name,
            status=Scenario.Status.DRAFT,
            config={},
        )
        print(f"✓ Created new DRAFT scenario: {scenario.name} (ID: {scenario.id})")
        print(f"  School: {school.name}")
        print(f"\nView at: http://localhost:8000/scenarios/{scenario.id}/")

    print("\n🚀 Click 'Run Solver' button in the UI to test!")
    print(f"   Expected: {expected_result}")

    if not realistic:
        print("\n💡 Want to see a SUCCESSFUL solve?")
        print("   Run: python manage.py seed_realistic")
        print("   Then: python create_demo_scenario.py --realistic")


if __name__ == "__main__":
    main()
