"""Build storage filenames (Unicode-safe, no path separators)."""


def slug_part(s: str) -> str:
    t = str(s).strip()
    out = []
    for ch in t:
        if ch in "/\\\\:*?\"<>|":
            out.append("_")
        else:
            out.append(ch)
    return "".join(out).strip() or "x"


def build_submission_filename(
    course_id: str,
    assignment_order: int,
    major: str,
    student_id: str,
    name: str,
    suffix: str = ".pdf",
) -> str:
    parts = [
        slug_part(course_id),
        f"hw{assignment_order:02d}",
        slug_part(major),
        slug_part(student_id),
        slug_part(name),
    ]
    base = "_".join(parts)
    return base + suffix
