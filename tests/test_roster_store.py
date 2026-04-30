from pathlib import Path

from app.roster_store import load_roster, save_roster_atomic, unique_student_ids, update_roster


def test_bom_strip_tmp(tmp_path: Path):
    p = tmp_path / "r.csv"
    p.write_text("\ufeff序号,学院,专业,学号,姓名,密码哈希\n1,A,B,sid1,Name,\n", encoding="utf-8")
    rows = load_roster(p)
    assert len(rows) == 1
    assert rows[0]["学号"] == "sid1"


def test_atomic_roundtrip(tmp_path: Path):
    p = tmp_path / "r.csv"
    rows = [
        {
            "序号": "1",
            "学院": "C",
            "专业": "M",
            "学号": "s",
            "姓名": "N",
            "密码哈希": "",
        }
    ]
    save_roster_atomic(p, rows)
    assert load_roster(p) == rows


def test_unique_student_ids():
    assert unique_student_ids(
        [
            {"学号": "a", "姓名": "x", "序号": "", "学院": "", "专业": "", "密码哈希": ""},
            {"学号": "b", "姓名": "y", "序号": "", "学院": "", "专业": "", "密码哈希": ""},
        ]
    )
    assert not unique_student_ids(
        [
            {"学号": "a", "姓名": "x", "序号": "", "学院": "", "专业": "", "密码哈希": ""},
            {"学号": "a", "姓名": "y", "序号": "", "学院": "", "专业": "", "密码哈希": ""},
        ]
    )


def test_update_roster_mutator(tmp_path: Path):
    p = tmp_path / "r.csv"
    save_roster_atomic(
        p,
        [
            {
                "序号": "1",
                "学院": "C",
                "专业": "M",
                "学号": "sid",
                "姓名": "Nm",
                "密码哈希": "",
            }
        ],
    )

    def mutator(rows):
        rows[0]["密码哈希"] = "hashed"
        return rows

    update_roster(p, mutator)
    rows = load_roster(p)
    assert rows[0]["密码哈希"] == "hashed"
