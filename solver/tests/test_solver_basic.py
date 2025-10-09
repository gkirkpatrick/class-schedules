"""Basic solver tests using simple working configurations.

These tests establish that the solver works with straightforward setups.
If these fail, something fundamental is broken.
"""

import pytest
from django.test import TestCase

from core.models import Room, School, Teacher
from solver.engine import ScheduleSolver, solve_scenario
from timetable.models import Course, Scenario, Section


class TestBasicSolverFeasibility(TestCase):
    """Test that the solver can handle basic feasible scenarios."""

    def setUp(self):
        """Create a basic school configuration that should be feasible."""
        # Create school with 5 days, 8 periods/day
        self.school = School.objects.create(
            name="Test High School",
            cycle_days=5,
            periods_per_day=8,
            period_minutes=45,
            lunch_window_start_period=4,
            lunch_window_span=2,
            default_teacher_daily_cap=5,
        )

        # Create 3 rooms
        self.room1 = Room.objects.create(school=self.school, name="101", capacity=30)
        self.room2 = Room.objects.create(school=self.school, name="102", capacity=30)
        self.room3 = Room.objects.create(school=self.school, name="103", capacity=30)

        # Create 5 teachers (3 English, 2 Math)
        self.eng_teacher1 = Teacher.objects.create(
            school=self.school,
            first_name="John",
            last_name="Smith",
            email="jsmith@test.edu",
            subject="English",
            max_sections=4,
            daily_teaching_cap=5,
        )
        self.eng_teacher2 = Teacher.objects.create(
            school=self.school,
            first_name="Jane",
            last_name="Doe",
            email="jdoe@test.edu",
            subject="English",
            max_sections=4,
            daily_teaching_cap=5,
        )
        self.eng_teacher3 = Teacher.objects.create(
            school=self.school,
            first_name="Fred",
            last_name="Fa",
            email="ffa@test.edu",
            subject="English",
            max_sections=4,
            daily_teaching_cap=5,
        )
        self.math_teacher1 = Teacher.objects.create(
            school=self.school,
            first_name="Sarah",
            last_name="Johnson",
            email="sjohnson@test.edu",
            subject="Math",
            max_sections=4,
            daily_teaching_cap=5,
        )
        self.math_teacher2 = Teacher.objects.create(
            school=self.school,
            first_name="Michael",
            last_name="Chen",
            email="mchen@test.edu",
            subject="Math",
            max_sections=4,
            daily_teaching_cap=5,
        )

        # Create 2 courses
        self.eng_course = Course.objects.create(
            school=self.school,
            code="ENG9",
            name="English 9",
            meets_per_week=5,
            capacity=25,
        )
        self.math_course = Course.objects.create(
            school=self.school,
            code="MATH9",
            name="Algebra I",
            meets_per_week=5,
            capacity=25,
        )

    def test_small_feasible_scenario(self):
        """Test: 2 sections, 2 teachers, 3 rooms should be feasible."""
        # Create scenario
        scenario = Scenario.objects.create(
            school=self.school, name="Small Test", status="DRAFT"
        )

        # Create 1 English section
        eng_section = Section.objects.create(
            course=self.eng_course,
            section_number=1,
            planned_count_per_week=5,
        )
        eng_section.teacher_candidates.set([self.eng_teacher1])
        eng_section.room_candidates.set([self.room1, self.room2, self.room3])

        # Create 1 Math section
        math_section = Section.objects.create(
            course=self.math_course,
            section_number=1,
            planned_count_per_week=5,
        )
        math_section.teacher_candidates.set([self.math_teacher1])
        math_section.room_candidates.set([self.room1, self.room2, self.room3])

        # Solve
        success = solve_scenario(scenario.id)

        # Assert
        scenario.refresh_from_db()
        self.assertTrue(success, f"Solver failed. Logs:\n{scenario.logs}")
        self.assertEqual(scenario.status, Scenario.Status.SOLVED)
        self.assertEqual(scenario.placements.count(), 10)  # 2 sections × 5 meetings

    def test_medium_feasible_scenario(self):
        """Test: 13 sections (7 ENG + 6 MATH), 5 teachers, 3 rooms should be feasible.

        This mimics the current working setup in the application.
        """
        # Create scenario
        scenario = Scenario.objects.create(
            school=self.school, name="Medium Test", status="DRAFT"
        )

        # Create 7 English sections
        eng_teachers = [self.eng_teacher1, self.eng_teacher2, self.eng_teacher3]
        for i in range(1, 8):
            section = Section.objects.create(
                course=self.eng_course,
                section_number=i,
                planned_count_per_week=5,
            )
            # First 6 sections use teacher1 and teacher2, last one uses all 3
            if i <= 6:
                section.teacher_candidates.set([self.eng_teacher1, self.eng_teacher2])
            else:
                section.teacher_candidates.set(eng_teachers)
            section.room_candidates.set([self.room1, self.room2, self.room3])

        # Create 6 Math sections
        math_teachers = [self.math_teacher1, self.math_teacher2]
        for i in range(1, 7):
            section = Section.objects.create(
                course=self.math_course,
                section_number=i,
                planned_count_per_week=5,
            )
            section.teacher_candidates.set(math_teachers)
            section.room_candidates.set([self.room1, self.room2, self.room3])

        # Solve
        success = solve_scenario(scenario.id)

        # Assert
        scenario.refresh_from_db()
        self.assertTrue(success, f"Solver failed. Logs:\n{scenario.logs}")
        self.assertEqual(scenario.status, Scenario.Status.SOLVED)
        self.assertEqual(scenario.placements.count(), 65)  # 13 sections × 5 meetings

        # Verify all sections are placed
        placements = scenario.placements.all()
        sections_placed = set(p.section_id for p in placements)
        all_sections = Section.objects.filter(course__school=self.school)
        self.assertEqual(len(sections_placed), all_sections.count())

    def test_sections_have_proper_m2m_setup(self):
        """Test: Verify that sections have teacher and room candidates configured.

        This is a regression test - if sections lack candidates, the solver will fail.
        """
        # Create scenario
        scenario = Scenario.objects.create(
            school=self.school, name="M2M Test", status="DRAFT"
        )

        # Create sections
        for i in range(1, 4):
            section = Section.objects.create(
                course=self.eng_course,
                section_number=i,
                planned_count_per_week=5,
            )
            section.teacher_candidates.set([self.eng_teacher1])
            section.room_candidates.set([self.room1, self.room2])

        # Verify all sections have candidates
        sections = Section.objects.filter(course__school=self.school)
        for section in sections:
            self.assertGreater(
                section.teacher_candidates.count(),
                0,
                f"Section {section} has no teacher candidates",
            )
            self.assertGreater(
                section.room_candidates.count(),
                0,
                f"Section {section} has no room candidates",
            )

        # Solve
        success = solve_scenario(scenario.id)

        # Assert
        scenario.refresh_from_db()
        self.assertTrue(success, f"Solver failed. Logs:\n{scenario.logs}")
        self.assertEqual(scenario.status, Scenario.Status.SOLVED)

    def test_same_period_constraint_with_single_section(self):
        """Test: Same period constraint works for a teacher with 1 section."""
        # Create scenario
        scenario = Scenario.objects.create(
            school=self.school, name="Same Period Single", status="DRAFT"
        )

        # Create 1 section
        section = Section.objects.create(
            course=self.eng_course,
            section_number=1,
            planned_count_per_week=5,
        )
        section.teacher_candidates.set([self.eng_teacher1])
        section.room_candidates.set([self.room1, self.room2, self.room3])

        # Solve
        success = solve_scenario(scenario.id)

        # Assert
        scenario.refresh_from_db()
        self.assertTrue(success, f"Solver failed. Logs:\n{scenario.logs}")
        self.assertEqual(scenario.status, Scenario.Status.SOLVED)

        # Verify all occurrences are at the same period
        placements = scenario.placements.filter(section=section)
        periods = set(p.period for p in placements)
        self.assertEqual(
            len(periods),
            1,
            f"Section should meet at same period every day, but found periods: {periods}",
        )

    def test_same_period_constraint_with_multiple_sections(self):
        """Test: Same period constraint works for a teacher with 3 sections."""
        # Create scenario
        scenario = Scenario.objects.create(
            school=self.school, name="Same Period Multiple", status="DRAFT"
        )

        # Create 3 sections for same teacher
        for i in range(1, 4):
            section = Section.objects.create(
                course=self.eng_course,
                section_number=i,
                planned_count_per_week=5,
            )
            section.teacher_candidates.set([self.eng_teacher1])
            section.room_candidates.set([self.room1, self.room2, self.room3])

        # Solve
        success = solve_scenario(scenario.id)

        # Assert
        scenario.refresh_from_db()
        self.assertTrue(success, f"Solver failed. Logs:\n{scenario.logs}")
        self.assertEqual(scenario.status, Scenario.Status.SOLVED)

        # Verify each section's occurrences are at the same period
        sections = Section.objects.filter(course=self.eng_course)
        for section in sections:
            placements = scenario.placements.filter(section=section)
            periods = set(p.period for p in placements)
            self.assertEqual(
                len(periods),
                1,
                f"Section {section.section_number} should meet at same period every day, but found periods: {periods}",
            )


class TestSolverConstraints(TestCase):
    """Test specific constraint behaviors."""

    def setUp(self):
        """Create basic school configuration."""
        self.school = School.objects.create(
            name="Constraint Test School",
            cycle_days=5,
            periods_per_day=8,
            period_minutes=45,
            lunch_window_start_period=4,
            lunch_window_span=2,
            default_teacher_daily_cap=5,
        )

        self.room = Room.objects.create(school=self.school, name="101", capacity=30)

        self.teacher = Teacher.objects.create(
            school=self.school,
            first_name="Test",
            last_name="Teacher",
            email="test@test.edu",
            subject="Test",
            max_sections=5,
            daily_teaching_cap=5,
        )

        self.course = Course.objects.create(
            school=self.school,
            code="TEST101",
            name="Test Course",
            meets_per_week=5,
            capacity=25,
        )

    def test_same_period_skips_once_per_week_sections(self):
        """Test: Same period constraint skips sections meeting once per week."""
        scenario = Scenario.objects.create(
            school=self.school, name="Once Per Week Test", status="DRAFT"
        )

        # Create a section that meets once per week (like a lab)
        section = Section.objects.create(
            course=self.course,
            section_number=1,
            planned_count_per_week=1,  # Meets only once
        )
        section.teacher_candidates.set([self.teacher])
        section.room_candidates.set([self.room])

        # Solve
        success = solve_scenario(scenario.id)

        # Assert - should be feasible (constraint doesn't apply)
        scenario.refresh_from_db()
        self.assertTrue(success, f"Solver failed. Logs:\n{scenario.logs}")
        self.assertEqual(scenario.status, Scenario.Status.SOLVED)
        self.assertEqual(scenario.placements.count(), 1)
