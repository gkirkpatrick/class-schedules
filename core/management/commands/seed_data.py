"""Management command to seed test data for school scheduling."""

from django.core.management.base import BaseCommand

from core.models import Room, RoomFeature, School, Student, Teacher
from timetable.models import Course, RequirementTemplate, Section


class Command(BaseCommand):
    """Seed database with test data."""

    help = "Seed database with test school, teachers, students, courses, and sections"

    def handle(self, *args: any, **kwargs: any) -> None:
        """Execute the command."""
        self.stdout.write("Seeding database with test data...")

        # Create school
        school, created = School.objects.get_or_create(
            name="Lincoln High School",
            defaults={
                "timezone": "America/New_York",
                "cycle_days": 5,
                "periods_per_day": 8,
                "period_minutes": 50,
                "recess_after_period": 3,
                "lunch_window_start_period": 4,
                "lunch_window_span": 2,
                "default_teacher_daily_cap": 3,
                "notes": "Test high school for scheduling demo",
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

        # Create rooms
        rooms_data = [
            ("Room 101", 30, []),
            ("Room 102", 30, []),
            ("Room 103", 30, []),
            ("Room 104", 30, []),
            ("Science Lab", 24, [lab_feature]),
            ("Gymnasium", 40, [gym_feature]),
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

        # Create teachers
        teachers_data = [
            ("Alice", "Johnson", "alice.johnson@lincoln.edu"),
            ("Bob", "Smith", "bob.smith@lincoln.edu"),
            ("Carol", "Williams", "carol.williams@lincoln.edu"),
            ("David", "Brown", "david.brown@lincoln.edu"),
            ("Emily", "Davis", "emily.davis@lincoln.edu"),
            ("Frank", "Miller", "frank.miller@lincoln.edu"),
            ("Grace", "Wilson", "grace.wilson@lincoln.edu"),
            ("Henry", "Moore", "henry.moore@lincoln.edu"),
        ]

        for first, last, email in teachers_data:
            teacher, created = Teacher.objects.get_or_create(
                email=email,
                defaults={
                    "school": school,
                    "first_name": first,
                    "last_name": last,
                    "daily_teaching_cap": 3,
                },
            )
            if created:
                self.stdout.write(f"  Created teacher: {first} {last}")

        self.stdout.write(self.style.SUCCESS(f"Created {len(teachers_data)} teachers"))

        # Create students (60 students across grades 9-10)
        students_created = 0
        for grade in [9, 10]:
            for i in range(30):
                first_name = f"Student{grade}_{i+1}"
                last_name = f"Last{i+1}"
                attributes = {}

                # Some students have IEP
                if i % 5 == 0:
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
                "meets_per_week": 5,
                "is_lab": False,
                "capacity": 25,
            },
            {
                "code": "MATH1",
                "name": "Algebra 1",
                "duration_periods": 1,
                "meets_per_week": 5,
                "is_lab": False,
                "capacity": 25,
            },
            {
                "code": "HIST9",
                "name": "World History",
                "duration_periods": 1,
                "meets_per_week": 5,
                "is_lab": False,
                "capacity": 30,
            },
            {
                "code": "SCI9",
                "name": "Biology",
                "duration_periods": 1,
                "meets_per_week": 4,
                "is_lab": False,
                "capacity": 24,
            },
            {
                "code": "PE",
                "name": "Physical Education",
                "duration_periods": 1,
                "meets_per_week": 2,
                "is_lab": False,
                "capacity": 40,
                "room_feature": gym_feature,
            },
            {
                "code": "ART",
                "name": "Art Fundamentals",
                "duration_periods": 1,
                "meets_per_week": 2,
                "is_lab": False,
                "capacity": 25,
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
                "meets_per_week": 2,
                "is_lab": True,
                "base_course": course_objs["SCI9"],
                "room_feature_required": lab_feature,
                "capacity": 24,
            },
        )
        if created:
            self.stdout.write(f"  Created lab course: SCI9_LAB")

        self.stdout.write(self.style.SUCCESS(f"Created {len(courses_data) + 1} courses"))

        # Create sections with teacher and room candidates
        all_teachers = list(Teacher.objects.filter(school=school))
        all_regular_rooms = list(Room.objects.filter(school=school).exclude(features__code="GYM").exclude(features__code="LAB"))
        lab_rooms = list(Room.objects.filter(school=school, features__code="LAB"))
        gym_rooms = list(Room.objects.filter(school=school, features__code="GYM"))

        sections_created = 0

        # Create 2 sections for each main course
        for course in Course.objects.filter(school=school, is_lab=False):
            for section_num in range(2):
                # Determine room candidates
                if course.code == "PE":
                    room_candidates = gym_rooms
                else:
                    room_candidates = all_regular_rooms

                section, created = Section.objects.get_or_create(
                    course=course,
                    planned_count_per_week=course.meets_per_week,
                    defaults={}
                )

                if created:
                    # Assign teacher candidates (all teachers can teach any course for simplicity)
                    section.teacher_candidates.set(all_teachers[:4])  # 4 teachers per section
                    section.room_candidates.set(room_candidates)
                    sections_created += 1

        # Create 1 section for lab
        lab_course = Course.objects.get(school=school, code="SCI9_LAB")
        lab_section, created = Section.objects.get_or_create(
            course=lab_course,
            planned_count_per_week=lab_course.meets_per_week,
            defaults={}
        )
        if created:
            lab_section.teacher_candidates.set(all_teachers[:4])
            lab_section.room_candidates.set(lab_rooms)
            sections_created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {sections_created} sections"))

        # Create requirement templates
        req_template, created = RequirementTemplate.objects.get_or_create(
            school=school,
            name="Grade 9 Core Requirements",
            defaults={
                "selector": {"grade": 9},
                "required_courses": [
                    {"course_code": "ENG9", "count": 1},
                    {"course_code": "MATH1", "count": 1},
                    {"course_code": "HIST9", "count": 1},
                    {"course_code": "SCI9", "count": 1},
                    {"course_code": "PE", "count": 1},
                ],
                "lab_policy": {
                    "SCI9": {"min_labs": 1, "max_labs": 2}
                },
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Grade 9 requirement template"))

        req_template_10, created = RequirementTemplate.objects.get_or_create(
            school=school,
            name="Grade 10 Core Requirements",
            defaults={
                "selector": {"grade": 10},
                "required_courses": [
                    {"course_code": "ENG9", "count": 1},
                    {"course_code": "MATH1", "count": 1},
                    {"course_code": "HIST9", "count": 1},
                    {"course_code": "SCI9", "count": 1},
                    {"course_code": "ART", "count": 1},
                ],
                "lab_policy": {
                    "SCI9": {"min_labs": 1, "max_labs": 2}
                },
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Grade 10 requirement template"))

        self.stdout.write(
            self.style.SUCCESS("\n✓ Database seeded successfully!")
        )
        self.stdout.write(
            "\nYou can now create scenarios and run the scheduler."
        )
