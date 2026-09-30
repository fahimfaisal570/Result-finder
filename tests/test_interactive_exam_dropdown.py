import collections
import cli_scraper as cs


def test_format_exam_name():
    # 1. Standard format - department discarded, 1st year 1st semester -> 1-1, exam year included
    assert cs.format_exam_name("B.Sc. in Computer Science and Engineering 1st year 1st Semester Examination of 2023") == "1-1 Exam 2023"
    assert cs.format_exam_name("B.Sc. in Computer Science and Engineering 3rd year 2nd Semester Examination of 2024") == "3-2 Exam 2024"

    # 2. Other departments
    assert cs.format_exam_name("B.Sc. in Civil Engineering 4th year 2nd Semester Examination of 2023") == "4-2 Exam 2023"
    assert cs.format_exam_name("B.Sc. in Electrical and Electronic Engineering 2nd year 1st Semester Examination of 2021") == "2-1 Exam 2021"

    # 3. Department name in middle of string
    assert cs.format_exam_name("1st Year 1st Semester B.Sc. in Computer Science & Engineering  Examination 2020 (2019-2020)") == "1-1 Exam 2020 (2019-2020)"

    # 4. Extra syllabus / curriculum tags in parentheses preserved for disambiguation
    assert cs.format_exam_name("B.Sc. in Civil Engineering 4th year 1st Semester Examination of 2024 (New Syllabus)") == "4-1 Exam 2024 (New Syllabus)"
    assert cs.format_exam_name("B.Sc. in Computer Science and Engineering 4th year 2nd Semester Examination of 2023 (Old Syllabus)") == "4-2 Exam 2023 (Old Syllabus)"

    # 5. Retake / Improvement exams formatted cleanly
    assert cs.format_exam_name("B.Sc. in Computer Science and Engineering 3rd year 2nd Semester Improvement Examination of 2024 (Retake/Improvement)") == "3-2 Imp. Exam 2024 (Retake/Improvement)"
    assert cs.format_exam_name("B.Sc. in Computer Science and Engineering 1st year 1st Semester Retake Examination of 2022 (Retake/Improvement)") == "1-1 Retake Exam 2022 (Retake/Improvement)"


def test_get_all_main_exams():
    mock_exams = collections.OrderedDict([
        ("1", "B.Sc. in Computer Science and Engineering 1st year 1st Semester Examination of 2020"),
        ("2", "B.Sc. in Computer Science and Engineering 1st year 1st Semester Examination of 2021"),
        ("3", "B.Sc. in Computer Science and Engineering 1st year 1st Semester Examination of 2022"),
        ("4", "B.Sc. in Computer Science and Engineering 1st year 1st Semester Examination of 2023"),
        ("5", "B.Sc. in Computer Science and Engineering 1st year 1st Semester Examination of 2024"),
        ("6", "B.Sc. in Computer Science and Engineering 1st year 2nd Semester Examination of 2024"),
        ("7", "B.Sc. in Computer Science and Engineering 2nd year 1st Semester Examination of 2024"),
        ("8", "B.Sc. in Computer Science and Engineering 2nd year 2nd Semester Examination of 2024"),
        ("9", "B.Sc. in Computer Science and Engineering 3rd year 1st Semester Examination of 2024"),
        ("10", "B.Sc. in Computer Science and Engineering 3rd year 2nd Semester Examination of 2024"),
        ("11", "B.Sc. in Computer Science and Engineering 4th year 1st Semester Examination of 2024"),
        ("12", "B.Sc. in Computer Science and Engineering 4th year 2nd Semester Examination of 2024"),
        # Improvement / Retake should be excluded
        ("13", "B.Sc. in Computer Science and Engineering 1st year 1st Semester Improvement Examination of 2024"),
        ("14", "B.Sc. in Computer Science and Engineering 2nd year 1st Semester Retake Examination of 2024"),
    ])

    mains = cs.get_all_main_exams(mock_exams)

    # All 12 main exams must be included (no 8-exam artificial limit!)
    assert len(mains) == 12
    assert "13" not in mains
    assert "14" not in mains

    # Verify chronological sorting (newest exam first)
    keys = list(mains.keys())
    assert keys[0] == "12"  # 4-2 2024
    assert keys[-1] == "1"  # 1-1 2020
