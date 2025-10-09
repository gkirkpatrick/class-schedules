"""Management command to seed REALISTIC, solvable data for school scheduling."""

from django.core.management.base import BaseCommand

from core.models import Room, RoomFeature, School, Student, Teacher
from timetable.models import Course, RequirementTemplate, Section


class Command(BaseCommand):
    """Seed database with realistic, solvable data."""

    help = "Seed database with realistic school data that WILL solve successfully"

    def handle(self, *args: any, **kwargs: any) -> None:
        """Execute the command."""
        self.stdout.write("Seeding REALISTIC, SOLVABLE data...")

        # Create school
        school, created = School.objects.get_or_create(
            name="Washington High School",
            defaults={
                "timezone": "America/New_York",
                "cycle_days": 5,
                "periods_per_day": 7,  # Standard school day
                "period_minutes": 55,
                "recess_after_period": None,  # No recess to maximize slots
                "lunch_window_start_period": 4,
                "lunch_window_span": 1,  # Smaller lunch window
                "default_teacher_daily_cap": 3,  # Max 3 periods per day
                "notes": "Realistic solvable school with adequate capacity",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created school: {school.name}"))
        else:
            self.stdout.write(f"School already exists: {school.name}")

        # Create room features
        lab_feature, _ = RoomFeature.objects.get_or_create(
            school=school,
            code="LAB",
            defaults={"description": "Science laboratory"},
        )
        gym_feature, _ = RoomFeature.objects.get_or_create(
            school=school,
            code="GYM",
            defaults={"description": "Gymnasium"},
        )
        self.stdout.write(self.style.SUCCESS("Created room features"))

        # Create 12 rooms total (8 regular, 2 labs, 2 gyms)
        rooms_data = [
            ("Room 201", 28, []),
            ("Room 202", 28, []),
            ("Room 203", 28, []),
            ("Room 204", 28, []),
            ("Room 205", 28, []),
            ("Room 206", 28, []),
            ("Room 207", 28, []),
            ("Room 208", 28, []),
            ("Science Lab A", 24, [lab_feature]),
            ("Science Lab B", 24, [lab_feature]),
            ("Gymnasium A", 40, [gym_feature]),
            ("Gymnasium B", 40, [gym_feature]),
        ]

        for room_name, capacity, features in rooms_data:
            room, created = Room.objects.get_or_create(
                school=school,
                name=room_name,
                defaults={"capacity": capacity},
            )
            if features:
                room.features.set(features)
            if created:
                self.stdout.write(f"  Created room: {room_name}")

        self.stdout.write(self.style.SUCCESS(f"Created {len(rooms_data)} rooms"))

        # Create MORE teachers (12 teachers with cap 4/day)
        teachers_data = [
            ("Sarah", "Anderson", "sarah.anderson@washington.edu", "English", 3),
            ("Michael", "Brown", "michael.brown@washington.edu", "English", 3),
            ("Jennifer", "Chen", "jennifer.chen@washington.edu", "Math", 3),
            ("David", "Davis", "david.davis@washington.edu", "Math", 3),
            ("Emily", "Evans", "emily.evans@washington.edu", "History", 3),
            ("Frank", "Foster", "frank.foster@washington.edu", "History", 3),
            ("Grace", "Garcia", "grace.garcia@washington.edu", "Science", 3),
            ("Henry", "Harris", "henry.harris@washington.edu", "Science", 3),
            ("Isabel", "Jackson", "isabel.jackson@washington.edu", "PE", 2),
            ("James", "Johnson", "james.johnson@washington.edu", "PE", 2),
            ("Karen", "Kim", "karen.kim@washington.edu", "PE", 2),
            ("Lucas", "Lopez", "lucas.lopez@washington.edu", "PE", 2),
        ]

        for first, last, email, subject, max_sections in teachers_data:
            teacher, created = Teacher.objects.get_or_create(
                email=email,
                defaults={
                    "school": school,
                    "first_name": first,
                    "last_name": last,
                    "subject": subject,
                    "daily_teaching_cap": 4,
                    "max_sections": max_sections,
                },
            )
            if created:
                self.stdout.write(f"  Created teacher: {first} {last} ({subject})")

        self.stdout.write(self.style.SUCCESS(f"Created {len(teachers_data)} teachers"))

        # Create FEWER students (30 total - manageable)
        students_created = 0
        for grade in [9]:  # Only grade 9 for simplicity
            for i in range(30):
                first_name = f"Student{grade}_{i+1}"
                last_name = f"Last{i+1}"
                attributes = {}

                # Some students have IEP
                if i % 8 == 0:
                    attributes["IEP"] = True

                student, created = Student.objects.get_or_create(
                    school=school,
                    first_name=first_name,
                    last_name=last_name,
                    grade=grade,
                    defaults={"attributes": attributes},
                )
                if created:
                    students_created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {students_created} students"))

        # Create courses
        courses_data = [
            {
                "code": "ENG9",
                "name": "English 9",
                "duration_periods": 1,
                "meets_per_week": 5,  # Meets every day at the same period
                "is_lab": False,
                "capacity": 5,  # Small sections (30 students ÷ 6 sections = 5 each)
            },
            {
                "code": "MATH9",
                "name": "Algebra 1",
                "duration_periods": 1,
                "meets_per_week": 5,  # Meets every day at the same period
                "is_lab": False,
                "capacity": 5,
            },
            {
                "code": "HIST9",
                "name": "World History",
                "duration_periods": 1,
                "meets_per_week": 5,  # Meets every day at the same period
                "is_lab": False,
                "capacity": 5,
            },
            {
                "code": "SCI9",
                "name": "Biology",
                "duration_periods": 1,
                "meets_per_week": 4,  # Meets 4 days (lab on 5th day)
                "is_lab": False,
                "capacity": 5,
            },
            {
                "code": "PE9",
                "name": "Physical Education",
                "duration_periods": 1,
                "meets_per_week": 5,  # Meets every day at the same period
                "is_lab": False,
                "capacity": 4,  # 30 students ÷ 8 sections ≈ 4 each
                "room_feature": gym_feature,
            },
        ]

        course_objs = {}
        for course_data in courses_data:
            room_feature = course_data.pop("room_feature", None)
            course, created = Course.objects.get_or_create(
                school=school,
                code=course_data["code"],
                defaults={**course_data, "room_feature_required": room_feature},
            )
            course_objs[course.code] = course
            if created:
                self.stdout.write(f"  Created course: {course.code} - {course.name}")

        # Create lab course for SCI9
        sci9_lab, created = Course.objects.get_or_create(
            school=school,
            code="SCI9_LAB",
            defaults={
                "name": "Biology Lab",
                "duration_periods": 1,
                "meets_per_week": 1,  # Only 1x per week
                "is_lab": True,
                "base_course": course_objs["SCI9"],
                "room_feature_required": lab_feature,
                "capacity": 24,
            },
        )
        if created:
            self.stdout.write(f"  Created lab course: SCI9_LAB")

        self.stdout.write(self.style.SUCCESS(f"Created {len(courses_data) + 1} courses"))

        # Create MORE sections (2 sections per course for 30 students)
        all_teachers = list(Teacher.objects.filter(school=school))
        all_regular_rooms = list(
            Room.objects.filter(school=school)
            .exclude(features__code="GYM")
            .exclude(features__code="LAB")
        )
        lab_rooms = list(Room.objects.filter(school=school, features__code="LAB"))
        gym_rooms = list(Room.objects.filter(school=school, features__code="GYM"))

        sections_created = 0

        # Assign teachers by subject (2 teachers per subject area)
        # This ensures all 12 teachers have sections to teach
        teacher_assignments = {
            "ENG9": all_teachers[0:2],   # Anderson, Brown
            "MATH9": all_teachers[2:4],  # Chen, Davis
            "HIST9": all_teachers[4:6],  # Evans, Foster
            "SCI9": all_teachers[6:8],   # Garcia, Harris
            "SCI9_LAB": all_teachers[6:8],  # Garcia, Harris (same as SCI9)
            "PE9": all_teachers[8:12],   # Jackson, Johnson, Kim, Lopez
        }

        # Create sections for each main course
        # With same-period constraint: each section occupies 1 room at 1 period across all 5 days
        # At any given period, we can have up to 26 rooms of classes happening simultaneously
        # So we just need enough periods for teachers to teach their sections
        for course in Course.objects.filter(school=school, is_lab=False):
            if course.code == "PE9":
                num_sections = 8  # 4 PE teachers × 2 sections each
            else:
                num_sections = 6  # 2 teachers × 3 sections each

            for section_num in range(num_sections):
                # Determine room candidates
                if course.code == "PE9":
                    room_candidates = gym_rooms
                else:
                    room_candidates = all_regular_rooms

                # Just create sections, don't use get_or_create
                section = Section.objects.create(
                    course=course,
                    section_number=section_num + 1,  # 1-indexed
                    planned_count_per_week=course.meets_per_week,
                )

                # Assign teacher candidates by subject
                subject_teachers = teacher_assignments.get(course.code, all_teachers[:2])
                section.teacher_candidates.set(subject_teachers)
                section.room_candidates.set(room_candidates)
                sections_created += 1
                self.stdout.write(
                    f"  Created {course.code} - Section {section_num+1}"
                )

        # Create lab sections (6 sections to match SCI9 sections)
        # Each lab meets 1x/week on the day SCI9 doesn't meet
        for section_num in range(6):
            lab_section = Section.objects.create(
                course=sci9_lab,
                section_number=section_num + 1,
                planned_count_per_week=1,  # Labs meet 1x per week
            )
            # Same teachers as SCI9 (science teachers)
            lab_section.teacher_candidates.set(teacher_assignments["SCI9_LAB"])
            lab_section.room_candidates.set(lab_rooms)
            sections_created += 1
            self.stdout.write(f"  Created SCI9_LAB - Section {section_num+1}")

        self.stdout.write(self.style.SUCCESS(f"Created {sections_created} sections"))

        # Create requirement templates
        req_template, created = RequirementTemplate.objects.get_or_create(
            school=school,
            name="Grade 9 Core Requirements",
            defaults={
                "selector": {"grade": 9},
                "required_courses": [
                    {"course_code": "ENG9", "count": 1},
                    {"course_code": "MATH9", "count": 1},
                    {"course_code": "HIST9", "count": 1},
                    {"course_code": "SCI9", "count": 1},
                    {"course_code": "PE9", "count": 1},
                    {"course_code": "SCI9_LAB", "count": 1},
                ],
                "lab_policy": {"SCI9": {"min_labs": 1, "max_labs": 1}},
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Grade 9 requirement template"))

        # Calculate capacity
        total_capacity = sections_created * 28  # Approximate
        total_students = students_created

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✓ REALISTIC data seeded successfully!"))
        self.stdout.write("=" * 60)
        self.stdout.write("\nCapacity Analysis:")
        self.stdout.write(f"  Students: {total_students}")
        self.stdout.write(f"  Total Section Capacity: ~{total_capacity}")
        self.stdout.write(f"  Capacity Ratio: {total_capacity/total_students:.1f}x")
        self.stdout.write("\n  ✅ This should SOLVE SUCCESSFULLY!\n")
        self.stdout.write("Next steps:")
        self.stdout.write("  1. python create_demo_scenario.py --realistic")
        self.stdout.write("  2. Click 'Run Solver' in UI")
        self.stdout.write("  3. Watch BOTH Stage A and Stage B succeed! 🎉\n")
