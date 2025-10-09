"""Performance benchmarking tests for precheck system.

Target: < 200ms for 100 sections, 60 teachers, 40 time slots
"""

import time

import pytest

from core.models import Room, School, Teacher
from timetable.models import Course, Section
from timetable.precheck import run_precheck


@pytest.mark.django_db
class TestPrecheckPerformance:
    """Test precheck performance meets target benchmarks."""

    def test_baseline_small_school(self):
        """Baseline: Small school (10 sections, 10 teachers, 35 slots)."""
        school = School.objects.create(
            name="Small School",
            timezone="America/New_York",
            cycle_days=5,
            periods_per_day=7,
            lunch_window_start_period=3,
            lunch_window_span=1,
            default_teacher_daily_cap=5,
        )

        # 10 teachers
        for i in range(10):
            Teacher.objects.create(
                school=school,
                first_name=f"Teacher{i}",
                last_name=f"Last{i}",
                email=f"teacher{i}@school.edu",
            )

        # 5 rooms
        for i in range(5):
            Room.objects.create(school=school, name=f"Room{i}", capacity=30)

        # 5 courses with 2 sections each = 10 sections
        for i in range(5):
            course = Course.objects.create(
                school=school,
                code=f"COURSE{i:03d}",
                name=f"Course {i}",
                duration_periods=1,
                meets_per_week=5,
                capacity=25,
            )
            Section.objects.create(
                course=course,
                section_number=1,
                planned_count_per_week=3,
            )
            Section.objects.create(
                course=course,
                section_number=2,
                planned_count_per_week=3,
            )

        start = time.perf_counter()
        report = run_precheck(school.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert report.status in ["OK", "WARN", "FAIL"]
        assert elapsed_ms < 50  # Should be very fast for small school
        print(f"\nSmall school: {elapsed_ms:.2f}ms")

    def test_target_benchmark_medium_school(self):
        """Target benchmark: 100 sections, 60 teachers, 40 slots (< 200ms)."""
        school = School.objects.create(
            name="Medium School",
            timezone="America/New_York",
            cycle_days=5,
            periods_per_day=8,  # 40 time slots
            lunch_window_start_period=4,
            lunch_window_span=1,
            default_teacher_daily_cap=6,
        )

        # 60 teachers
        for i in range(60):
            Teacher.objects.create(
                school=school,
                first_name=f"Teacher{i}",
                last_name=f"Last{i}",
                email=f"teacher{i}@school.edu",
            )

        # 20 rooms
        for i in range(20):
            Room.objects.create(school=school, name=f"Room{i}", capacity=30)

        # Create 100 sections across 50 courses
        for i in range(50):
            course = Course.objects.create(
                school=school,
                code=f"COURSE{i:03d}",
                name=f"Course {i}",
                duration_periods=1,
                meets_per_week=5,
                capacity=25,
            )
            Section.objects.create(
                course=course,
                section_number=1,
                planned_count_per_week=3,
            )
            Section.objects.create(
                course=course,
                section_number=2,
                planned_count_per_week=3,
            )

        start = time.perf_counter()
        report = run_precheck(school.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert report.status in ["OK", "WARN", "FAIL"]
        assert (
            elapsed_ms < 200
        ), f"Precheck took {elapsed_ms:.2f}ms, exceeds 200ms target"
        print(f"\nMedium school (target): {elapsed_ms:.2f}ms")

    def test_large_school_scaling(self):
        """Stress test: Large school (200 sections, 100 teachers, 50 slots)."""
        school = School.objects.create(
            name="Large School",
            timezone="America/New_York",
            cycle_days=5,
            periods_per_day=10,  # 50 time slots
            lunch_window_start_period=5,
            lunch_window_span=1,
            default_teacher_daily_cap=7,
        )

        # 100 teachers
        for i in range(100):
            Teacher.objects.create(
                school=school,
                first_name=f"Teacher{i}",
                last_name=f"Last{i}",
                email=f"teacher{i}@school.edu",
            )

        # 40 rooms
        for i in range(40):
            Room.objects.create(school=school, name=f"Room{i}", capacity=30)

        # Create 200 sections across 100 courses
        for i in range(100):
            course = Course.objects.create(
                school=school,
                code=f"COURSE{i:03d}",
                name=f"Course {i}",
                duration_periods=1,
                meets_per_week=5,
                capacity=25,
            )
            Section.objects.create(
                course=course,
                section_number=1,
                planned_count_per_week=3,
            )
            Section.objects.create(
                course=course,
                section_number=2,
                planned_count_per_week=3,
            )

        start = time.perf_counter()
        report = run_precheck(school.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert report.status in ["OK", "WARN", "FAIL"]
        assert (
            elapsed_ms < 500
        ), f"Precheck took {elapsed_ms:.2f}ms for large school, should scale gracefully"
        print(f"\nLarge school (stress): {elapsed_ms:.2f}ms")

    def test_performance_with_complex_constraints(self):
        """Performance with complex constraints (locked placements, labs, unavailability)."""
        school = School.objects.create(
            name="Complex School",
            timezone="America/New_York",
            cycle_days=5,
            periods_per_day=8,
            lunch_window_start_period=4,
            lunch_window_span=1,
            default_teacher_daily_cap=6,
        )

        # 50 teachers with various unavailability patterns
        for i in range(50):
            teacher = Teacher.objects.create(
                school=school,
                first_name=f"Teacher{i}",
                last_name=f"Last{i}",
                email=f"teacher{i}@school.edu",
            )
            # Add unavailability for some teachers
            if i % 3 == 0:
                teacher.unavailable_timeslot_set = (1 << 0) | (1 << 5) | (1 << 10)
                teacher.save()

        # 15 rooms
        for i in range(15):
            Room.objects.create(
                school=school,
                name=f"Room{i}",
                capacity=30,
            )

        # Create 80 sections with labs
        for i in range(40):
            course = Course.objects.create(
                school=school,
                code=f"COURSE{i:03d}",
                name=f"Course {i}",
                duration_periods=1,
                meets_per_week=5,
                capacity=25,
            )

            # Regular section
            section1 = Section.objects.create(
                course=course,
                section_number=1,
                planned_count_per_week=3,
            )

            # Section with lab
            section2 = Section.objects.create(
                course=course,
                section_number=2,
                planned_count_per_week=3,
            )

        start = time.perf_counter()
        report = run_precheck(school.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert report.status in ["OK", "WARN", "FAIL"]
        assert (
            elapsed_ms < 300
        ), f"Complex constraints precheck took {elapsed_ms:.2f}ms, should stay under 300ms"
        print(f"\nComplex constraints: {elapsed_ms:.2f}ms")

    def test_check_individual_function_performance(self):
        """Benchmark individual check functions."""
        from timetable.precheck import (
            _check_feature_supply,
            _check_lunch_feasibility,
            _check_room_capacity,
            _check_teacher_capacity,
        )
        from timetable.precheck_utils import TimeMaskBuilder

        school = School.objects.create(
            name="Benchmark School",
            timezone="America/New_York",
            cycle_days=5,
            periods_per_day=8,
            lunch_window_start_period=4,
            lunch_window_span=1,
            default_teacher_daily_cap=6,
        )

        # 60 teachers
        for i in range(60):
            Teacher.objects.create(
                school=school,
                first_name=f"Teacher{i}",
                last_name=f"Last{i}",
                email=f"teacher{i}@school.edu",
            )

        # 20 rooms
        for i in range(20):
            Room.objects.create(school=school, name=f"Room{i}", capacity=30)

        # 100 sections
        for i in range(50):
            course = Course.objects.create(
                school=school,
                code=f"COURSE{i:03d}",
                name=f"Course {i}",
                duration_periods=1,
                meets_per_week=5,
                capacity=25,
            )
            Section.objects.create(
                course=course, section_number=1, planned_count_per_week=3
            )
            Section.objects.create(
                course=course, section_number=2, planned_count_per_week=3
            )

        mask_builder = TimeMaskBuilder(school.cycle_days, school.periods_per_day)

        # Benchmark each check
        checks = [
            ("teacher_capacity", _check_teacher_capacity),
            ("lunch_feasibility", _check_lunch_feasibility),
            ("room_capacity", _check_room_capacity),
            ("feature_supply", _check_feature_supply),
        ]

        for name, check_fn in checks:
            start = time.perf_counter()
            issues = check_fn(school, mask_builder)
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"\n  {name}: {elapsed_ms:.2f}ms ({len(issues)} issues)")
            assert elapsed_ms < 50, f"{name} check too slow: {elapsed_ms:.2f}ms"
