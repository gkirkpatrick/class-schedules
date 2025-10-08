"""Student assignment solver (Stage B) - assigns students to placed sections."""

from collections import defaultdict
from typing import Any

from pulp import LpBinary, LpMinimize, LpProblem, LpStatus, LpVariable, lpSum

from core.models import Student
from timetable.models import Placement, RequirementTemplate, Scenario, Section, StudentEnrollment


class StudentAssignmentSolver:
    """Solver for assigning students to sections after master schedule is created."""

    def __init__(self, scenario: Scenario) -> None:
        """Initialize student assignment solver."""
        self.scenario = scenario
        self.school = scenario.school
        self.problem = LpProblem("StudentAssignment", LpMinimize)

        # Data structures
        self.students = list(Student.objects.filter(school=self.school))
        self.placements = list(
            Placement.objects.filter(scenario=scenario).select_related(
                "section__course", "teacher", "room"
            )
        )

        # Variables storage
        self.assignment_vars: dict[tuple[int, int], Any] = {}
        # Key: (student_id, placement_id)

        # Diagnostics
        self.diagnostics: list[str] = []

    def solve(self) -> bool:
        """
        Run MIP solver to assign students to sections.

        Returns:
            True if solved successfully, False if infeasible
        """
        if not self.placements:
            self.diagnostics.append("No placements available - master schedule must be solved first")
            return False

        self._create_variables()
        self._add_hard_constraints()
        self._add_soft_constraints()

        # Solve
        status = self.problem.solve()

        if status == 1:  # LpStatus.OPTIMAL
            self._save_solution()
            return True
        else:
            self.diagnostics.append(f"Assignment failed with status: {LpStatus[status]}")
            self._generate_infeasibility_diagnostics()
            return False

    def _create_variables(self) -> None:
        """Create binary variables for student-placement assignments."""
        for student in self.students:
            for placement in self.placements:
                var_name = f"assign_s{student.id}_p{placement.id}"
                var = LpVariable(var_name, cat=LpBinary)
                self.assignment_vars[(student.id, placement.id)] = var

    def _add_hard_constraints(self) -> None:
        """Add hard constraints that must be satisfied."""
        self._constraint_no_student_overlap()
        self._constraint_section_capacity()
        self._constraint_lunch_requirement()
        self._constraint_course_requirements()

    def _constraint_no_student_overlap(self) -> None:
        """A student cannot be in two places at the same time."""
        for student in self.students:
            # Group placements by (day, period)
            slots: dict[tuple[int, int], list[Placement]] = defaultdict(list)
            for placement in self.placements:
                slots[(placement.day, placement.period)].append(placement)

            # For each time slot, student can be assigned to at most one placement
            for (day, period), slot_placements in slots.items():
                conflict_vars = [
                    self.assignment_vars[(student.id, p.id)] for p in slot_placements
                ]
                if conflict_vars:
                    self.problem += lpSum(conflict_vars) <= 1, f"no_overlap_s{student.id}_d{day}_p{period}"

    def _constraint_section_capacity(self) -> None:
        """Sections cannot exceed their capacity."""
        # Group placements by section
        section_placements: dict[int, list[Placement]] = defaultdict(list)
        for placement in self.placements:
            section_placements[placement.section_id].append(placement)

        for section_id, placements in section_placements.items():
            section = Section.objects.get(id=section_id)
            capacity = section.course.capacity

            # All students assigned to any placement of this section
            for placement in placements:
                assignment_vars_for_placement = [
                    self.assignment_vars[(s.id, placement.id)] for s in self.students
                ]
                self.problem += (
                    lpSum(assignment_vars_for_placement) <= capacity,
                    f"capacity_p{placement.id}",
                )

    def _constraint_lunch_requirement(self) -> None:
        """Each student must have at least one free period in the lunch window."""
        lunch_start = self.school.lunch_window_start_period - 1  # 0-indexed
        lunch_end = lunch_start + self.school.lunch_window_span

        for student in self.students:
            for day in range(self.school.cycle_days):
                # Find all placements in lunch window for this day
                lunch_placements = [
                    p
                    for p in self.placements
                    if p.day == day and lunch_start <= p.period < lunch_end
                ]

                if lunch_placements:
                    # Student must have at least one free period (not assigned to all)
                    lunch_vars = [
                        self.assignment_vars[(student.id, p.id)] for p in lunch_placements
                    ]
                    # Must leave at least one period free
                    self.problem += (
                        lpSum(lunch_vars) <= self.school.lunch_window_span - 1,
                        f"lunch_s{student.id}_d{day}",
                    )

    def _constraint_course_requirements(self) -> None:
        """Students must be assigned to required courses based on RequirementTemplates."""
        # Get requirement templates
        templates = RequirementTemplate.objects.filter(school=self.school)

        for student in self.students:
            # Find applicable templates for this student
            applicable_templates = self._get_applicable_templates(student, templates)

            for template in applicable_templates:
                required_courses = template.required_courses
                if isinstance(required_courses, list):
                    for req in required_courses:
                        course_code = req.get("course_code")
                        count = req.get("count", 1)

                        # Find all placements for this course
                        course_placements = [
                            p
                            for p in self.placements
                            if p.section.course.code == course_code
                        ]

                        if course_placements:
                            # Student must be assigned to at least 'count' meetings
                            # Since a section meets multiple times per week, we need to be careful
                            # For MVP: ensure student is assigned to the section (any occurrence)

                            # Group by section
                            section_groups: dict[int, list[Placement]] = defaultdict(list)
                            for p in course_placements:
                                section_groups[p.section_id].append(p)

                            # Create section choice variables
                            section_choice_vars = []
                            for section_id, section_placements in section_groups.items():
                                # If assigned to any placement of this section, count as enrolled
                                section_var = LpVariable(
                                    f"enrolled_s{student.id}_sec{section_id}", cat=LpBinary
                                )
                                section_choice_vars.append(section_var)

                                # Link: if enrolled in section, must attend ALL occurrences
                                for placement in section_placements:
                                    assign_var = self.assignment_vars[(student.id, placement.id)]
                                    # If enrolled in section, must attend this occurrence
                                    self.problem += (
                                        assign_var >= section_var,
                                        f"attend_s{student.id}_p{placement.id}",
                                    )
                                    # If attending, must be enrolled
                                    self.problem += (
                                        section_var >= assign_var,
                                        f"enroll_s{student.id}_p{placement.id}",
                                    )

                            # Must be enrolled in at least 'count' sections
                            if section_choice_vars:
                                self.problem += (
                                    lpSum(section_choice_vars) >= count,
                                    f"req_s{student.id}_{course_code}",
                                )

    def _get_applicable_templates(
        self, student: Student, templates: Any
    ) -> list[RequirementTemplate]:
        """Get requirement templates applicable to a student."""
        applicable = []
        for template in templates:
            selector = template.selector
            if self._matches_selector(student, selector):
                applicable.append(template)
        return applicable

    def _matches_selector(self, student: Student, selector: dict[str, Any]) -> bool:
        """Check if student matches selector predicate."""
        # Simple predicate matching (can be extended)
        if not selector:
            return True

        # Check grade
        if "grade" in selector:
            if student.grade != selector["grade"]:
                return False

        # Check attributes (IEP, ELL, etc.)
        if "attributes" in selector:
            for key, value in selector["attributes"].items():
                if student.attributes.get(key) != value:
                    return False

        return True

    def _add_soft_constraints(self) -> None:
        """Add soft constraints as penalties in objective."""
        penalty_vars = []

        # Penalty: minimize gaps in student schedules
        for student in self.students:
            for day in range(self.school.cycle_days):
                # Count number of periods with classes
                day_placements = [p for p in self.placements if p.day == day]

                if day_placements:
                    # Create variables for first and last period with class
                    # This is complex, skip for MVP
                    pass

        # For MVP, just minimize number of assignments (no-op if requirements are tight)
        # Uncomment to add minimal objective if no soft constraints:
        # all_vars = list(self.assignment_vars.values())
        # self.problem += lpSum(all_vars)

    def _save_solution(self) -> None:
        """Save the solution as StudentEnrollment objects."""
        # Clear existing enrollments
        StudentEnrollment.objects.filter(scenario=self.scenario).delete()

        enrollments_to_create = []

        for (student_id, placement_id), var in self.assignment_vars.items():
            if var.varValue == 1:
                student = Student.objects.get(id=student_id)
                placement = next(p for p in self.placements if p.id == placement_id)

                enrollments_to_create.append(
                    StudentEnrollment(
                        scenario=self.scenario,
                        student=student,
                        section=placement.section,
                        day=placement.day,
                        period=placement.period,
                    )
                )

        StudentEnrollment.objects.bulk_create(enrollments_to_create)
        self.diagnostics.append(f"Successfully created {len(enrollments_to_create)} enrollments")

    def _generate_infeasibility_diagnostics(self) -> None:
        """Generate diagnostics for infeasible assignment."""
        self.diagnostics.append("Student assignment is INFEASIBLE. Possible reasons:")
        self.diagnostics.append("  - Section capacities too low for number of students")
        self.diagnostics.append("  - Course requirements cannot be met with current schedule")
        self.diagnostics.append("  - Conflicting time slots for required courses")


def assign_students(scenario_id: int) -> bool:
    """
    Main entry point for student assignment.

    Args:
        scenario_id: ID of the scenario

    Returns:
        True if assignment succeeded, False otherwise
    """
    scenario = Scenario.objects.get(id=scenario_id)

    if scenario.status != Scenario.Status.SOLVED:
        return False

    solver = StudentAssignmentSolver(scenario)
    success = solver.solve()

    if success:
        scenario.logs += "\n" + "\n".join(solver.diagnostics)
    else:
        scenario.logs += "\n" + "ASSIGNMENT FAILED:\n" + "\n".join(solver.diagnostics)

    scenario.save()
    return success
