"""HTTP routes (student, teacher, public)."""
from __future__ import annotations

import csv
import io
import secrets
import string
import zipfile
from itertools import zip_longest
from pathlib import Path

import hmac
from wtforms import ValidationError
from flask_wtf.csrf import validate_csrf

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from app.course_loader import ensure_assignment_dirs, load_course_config
from app.course_store import save_course_config_atomic, validate_and_build_course_dict
from app.forms import (
    AddStudentForm,
    CourseSaveForm,
    DeleteRowForm,
    EnrollForm,
    ResetPasswordForm,
    RosterImportForm,
    StudentLoginForm,
    TeacherLoginForm,
)
from app.manifest_store import (
    load_manifest,
    manifest_path_for,
    remove_student_from_manifest,
    update_manifest,
)
from app.naming import build_submission_filename
from app.roster_store import (
    ROSTER_FIELDS,
    find_student,
    load_roster,
    unique_student_ids,
    update_roster,
    validate_roster_row,
)

bp_public = Blueprint("public", __name__)
bp_student = Blueprint("student", __name__, url_prefix="/student")
bp_teacher = Blueprint("teacher", __name__, url_prefix="/teacher")


def _cfg():
    return current_app.extensions["cfg"]


def _course():
    return current_app.extensions["course_cfg"]


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _validate_pdf(data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise ValueError("文件过大")
    if not data.startswith(b"%PDF"):
        raise ValueError("仅支持 PDF 文件")


def _assignment_by_id(aid: str) -> dict | None:
    for a in _course().get("assignments", []):
        if a.get("id") == aid:
            return a
    return None


def student_required():
    if not session.get("student_id"):
        flash("请先登录学生账号。", "warning")
        return redirect(url_for("student.login"))
    return None


def teacher_required():
    if not session.get("teacher"):
        flash("请先登录教师账号。", "warning")
        return redirect(url_for("teacher.teacher_login"))
    return None


@bp_public.route("/health")
def health():
    return {"status": "ok"}


@bp_public.route("/")
def index():
    return render_template("index.html")


@bp_student.route("/enroll", methods=["GET", "POST"])
def enroll():
    cfg = _cfg()
    form = EnrollForm()
    if form.validate_on_submit():
        sid = form.student_id.data.strip()
        name = form.name.data.strip()

        def mutator(rows):
            row = find_student(rows, sid)
            if row is None:
                raise ValueError("该学生不存在于名册中")
            if row.get("姓名", "").strip() != name:
                raise ValueError("姓名与学号不匹配")
            if row.get("密码哈希", "").strip():
                raise ValueError("该账号已初始化，请直接登录")
            plain = _generate_password()
            row["密码哈希"] = generate_password_hash(plain)
            session["_last_plain_password"] = plain
            session["_last_plain_student"] = sid
            return rows

        try:
            update_roster(cfg.ROSTER_PATH, mutator)
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("student/enroll.html", form=form)
        flash("请妥善保存系统生成的初始密码（仅此一次显示）。", "success")
        return redirect(url_for("student.enroll_done"))

    return render_template("student/enroll.html", form=form)


@bp_student.route("/enroll/done")
def enroll_done():
    plain = session.pop("_last_plain_password", None)
    sid = session.pop("_last_plain_student", None)
    if not plain or not sid:
        flash("会话已过期。", "warning")
        return redirect(url_for("student.enroll"))
    return render_template("student/enroll_done.html", plain_password=plain, student_id=sid)


@bp_student.route("/login", methods=["GET", "POST"])
def login():
    cfg = _cfg()
    form = StudentLoginForm()
    if form.validate_on_submit():
        sid = form.student_id.data.strip()
        password = form.password.data or ""
        rows = load_roster(cfg.ROSTER_PATH)
        row = find_student(rows, sid)
        if not row or not row.get("密码哈希"):
            flash("学号或密码错误，或尚未完成初次注册。", "danger")
            return render_template("student/login.html", form=form)
        if not check_password_hash(row["密码哈希"], password):
            flash("学号或密码错误。", "danger")
            return render_template("student/login.html", form=form)
        session.permanent = True
        session["student_id"] = sid
        flash("登录成功。", "success")
        return redirect(url_for("student.assignments"))
    return render_template("student/login.html", form=form)


@bp_student.route("/logout")
def logout():
    session.pop("student_id", None)
    flash("已退出。", "info")
    return redirect(url_for("public.index"))


@bp_student.route("/assignments")
def assignments():
    redir = student_required()
    if redir:
        return redir
    cfg = _cfg()
    sid = session["student_id"]
    rows = load_roster(cfg.ROSTER_PATH)
    row = find_student(rows, sid)
    course = _course()
    storage = cfg.STORAGE_ROOT
    states = {}
    for a in course.get("assignments", []):
        aid = a["id"]
        mp = load_manifest(manifest_path_for(storage, aid))
        st = mp.get(sid)
        states[aid] = st
    return render_template(
        "student/assignments.html",
        row=row,
        assignments=course.get("assignments", []),
        states=states,
        course_title=course.get("course_title", ""),
    )


@bp_student.route("/assignments/<assignment_id>/upload", methods=["POST"])
def upload_pdf(assignment_id: str):
    redir = student_required()
    if redir:
        return redir
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        abort(400)
    cfg = _cfg()
    course = _course()
    a = _assignment_by_id(assignment_id)
    if not a:
        abort(404)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("请选择 PDF 文件。", "danger")
        return redirect(url_for("student.assignments"))
    sid = session["student_id"]
    rows = load_roster(cfg.ROSTER_PATH)
    row = find_student(rows, sid)
    if not row:
        abort(403)
    data = upload.read()
    max_b = cfg.MAX_UPLOAD_MB * 1024 * 1024
    try:
        _validate_pdf(data, max_b)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("student.assignments"))

    filename = build_submission_filename(
        course["course_id"],
        int(a.get("order", 1)),
        row.get("专业", ""),
        sid,
        row.get("姓名", ""),
    )
    dest_dir = cfg.STORAGE_ROOT / assignment_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    mp_path = manifest_path_for(cfg.STORAGE_ROOT, assignment_id)
    prev = load_manifest(mp_path).get(sid)
    replace = prev is not None
    if dest_path.exists():
        replace = True
        dest_path.unlink()

    dest_path.write_bytes(data)
    update_manifest(mp_path, sid, filename, replace=replace)
    flash("上传成功。", "success")
    return redirect(url_for("student.assignments"))


@bp_student.route("/assignments/<assignment_id>/delete", methods=["POST"])
def delete_pdf(assignment_id: str):
    redir = student_required()
    if redir:
        return redir
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        abort(400)
    cfg = _cfg()
    sid = session["student_id"]
    mp_path = manifest_path_for(cfg.STORAGE_ROOT, assignment_id)
    man = load_manifest(mp_path)
    st = man.get(sid)
    if not st:
        flash("没有可删除的文件。", "warning")
        return redirect(url_for("student.assignments"))
    fn = st.get("filename")
    if fn:
        p = cfg.STORAGE_ROOT / assignment_id / fn
        if p.exists():
            p.unlink()
    remove_student_from_manifest(mp_path, sid)
    flash("已删除提交（可重新上传）。", "info")
    return redirect(url_for("student.assignments"))


@bp_teacher.route("/login", methods=["GET", "POST"])
def teacher_login():
    cfg = _cfg()
    form = TeacherLoginForm()
    if form.validate_on_submit():
        u = form.username.data.strip()
        p = form.password.data or ""
        if not cfg.TEACHER_PASSWORD:
            flash("服务器未配置教师密码（TEACHER_PASSWORD）。", "danger")
            return render_template("teacher/login.html", form=form)
        ok = u == cfg.TEACHER_USERNAME and hmac.compare_digest(
            p.encode("utf-8"),
            cfg.TEACHER_PASSWORD.encode("utf-8"),
        )
        if not ok:
            flash("用户名或密码错误。", "danger")
            return render_template("teacher/login.html", form=form)
        session.permanent = True
        session["teacher"] = True
        flash("教师登录成功。", "success")
        return redirect(url_for("teacher.roster_view"))
    return render_template("teacher/login.html", form=form)


@bp_teacher.route("/logout")
def teacher_logout():
    session.pop("teacher", None)
    flash("已退出教师账号。", "info")
    return redirect(url_for("public.index"))


@bp_teacher.route("/course", methods=["GET", "POST"])
def course_edit():
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    path = cfg.COURSE_CONFIG
    form = CourseSaveForm()
    if request.method == "POST" and form.validate_on_submit():
        raw_ids = request.form.getlist("assignment_id")
        raw_titles = request.form.getlist("assignment_title")
        ids: list[str] = []
        titles: list[str] = []
        for i, t in zip_longest(raw_ids, raw_titles, fillvalue=""):
            if len(ids) >= 40:
                break
            si = (i or "").strip()
            st = (t or "").strip()
            if si or st:
                ids.append(si)
                titles.append(st)
        try:
            data = validate_and_build_course_dict(
                form.course_id.data,
                form.course_title.data,
                ids,
                titles,
            )
            save_course_config_atomic(path, data)
            cfg_obj = load_course_config(path)
            ensure_assignment_dirs(cfg.STORAGE_ROOT, cfg_obj.get("assignments", []))
            current_app.extensions["course_cfg"] = cfg_obj
            flash(
                "课程配置已保存。若修改了作业 id，旧的 storage 子目录不会自动删除，可按需在服务器上清理。",
                "success",
            )
            return redirect(url_for("teacher.course_edit"))
        except ValueError as e:
            flash(str(e), "danger")

    data = load_course_config(path)
    rows = list(data.get("assignments", []))
    if not rows:
        rows = [{"id": "", "title": "", "order": 1}]
    if request.args.get("add") == "1":
        rows.append({"id": "", "title": "", "order": len(rows) + 1})
    if not form.is_submitted() or request.method == "GET":
        form.course_id.data = data.get("course_id", "")
        form.course_title.data = data.get("course_title", "")
    return render_template(
        "teacher/course_edit.html",
        form=form,
        assignment_rows=rows,
    )


@bp_teacher.route("/roster")
def roster_view():
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    rows = load_roster(cfg.ROSTER_PATH)
    return render_template(
        "teacher/roster.html",
        rows=rows,
        course=_course(),
        import_form=RosterImportForm(),
        add_form=AddStudentForm(),
        delete_form=DeleteRowForm(),
        reset_password_form=ResetPasswordForm(),
    )


@bp_teacher.route("/roster/template.csv")
def roster_template():
    redir = teacher_required()
    if redir:
        return redir
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["序号", "学院", "专业", "学号", "姓名", "密码哈希"])
    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=roster_template.csv"},
    )


@bp_teacher.route("/roster/import", methods=["POST"])
def roster_import():
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    form = RosterImportForm()
    if not form.validate_on_submit():
        flash("请选择 CSV 文件。", "danger")
        return redirect(url_for("teacher.roster_view"))
    raw = form.file.data.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    new_rows: list[dict[str, str]] = []
    for row in reader:
        r = {k: (row.get(k) or "").strip() for k in ROSTER_FIELDS}
        new_rows.append(r)
    if not unique_student_ids(new_rows):
        flash("导入失败：学号重复。", "danger")
        return redirect(url_for("teacher.roster_view"))
    for r in new_rows:
        validate_roster_row(r)

    backup = cfg.ROSTER_PATH.with_suffix(".bak.csv")
    if cfg.ROSTER_PATH.exists():
        backup.write_bytes(cfg.ROSTER_PATH.read_bytes())

    def mutator(_rows):
        return new_rows

    update_roster(cfg.ROSTER_PATH, mutator)
    flash("名册已导入。", "success")
    return redirect(url_for("teacher.roster_view"))


@bp_teacher.route("/roster/add", methods=["POST"])
def roster_add():
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    form = AddStudentForm()
    if not form.validate_on_submit():
        flash("表单无效。", "danger")
        return redirect(url_for("teacher.roster_view"))
    row = {
        "序号": form.seq.data.strip() if form.seq.data else "",
        "学院": form.college.data.strip(),
        "专业": form.major.data.strip(),
        "学号": form.student_id.data.strip(),
        "姓名": form.name.data.strip(),
        "密码哈希": "",
    }
    validate_roster_row(row)

    def mutator(rows):
        if find_student(rows, row["学号"]):
            raise ValueError("学号已存在")
        rows.append(row)
        return rows

    try:
        update_roster(cfg.ROSTER_PATH, mutator)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("teacher.roster_view"))
    flash("已添加学生（未注册前无密码哈希）。", "success")
    return redirect(url_for("teacher.roster_view"))


@bp_teacher.route("/roster/delete/<student_id>", methods=["POST"])
def roster_delete(student_id: str):
    redir = teacher_required()
    if redir:
        return redir
    form = DeleteRowForm()
    if not form.validate_on_submit():
        flash("提交无效。", "danger")
        return redirect(url_for("teacher.roster_view"))
    cfg = _cfg()
    course = _course()
    sid = student_id.strip()

    def mutator(rows):
        return [r for r in rows if r.get("学号", "").strip() != sid]

    update_roster(cfg.ROSTER_PATH, mutator)
    for a in course.get("assignments", []):
        aid = a["id"]
        mp_path = manifest_path_for(cfg.STORAGE_ROOT, aid)
        man = load_manifest(mp_path)
        st = man.get(sid)
        if st and st.get("filename"):
            p = cfg.STORAGE_ROOT / aid / st["filename"]
            if p.exists():
                p.unlink()
        remove_student_from_manifest(mp_path, sid)
    flash("已删除学生及其作业记录。", "success")
    return redirect(url_for("teacher.roster_view"))


@bp_teacher.route("/roster/reset-password/<student_id>", methods=["POST"])
def roster_reset_password(student_id: str):
    redir = teacher_required()
    if redir:
        return redir
    form = ResetPasswordForm()
    if not form.validate_on_submit():
        flash("提交无效。", "danger")
        return redirect(url_for("teacher.roster_view"))
    cfg = _cfg()
    sid = student_id.strip()

    def mutator(rows):
        row = find_student(rows, sid)
        if row is None:
            raise ValueError("名册中无此学号")
        plain = _generate_password()
        row["密码哈希"] = generate_password_hash(plain)
        session["_teacher_reset_plain_password"] = plain
        session["_teacher_reset_student_id"] = sid
        return rows

    try:
        update_roster(cfg.ROSTER_PATH, mutator)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("teacher.roster_view"))
    flash("已生成新密码，请仅在安全环境下展示给学生。", "success")
    return redirect(url_for("teacher.roster_reset_done"))


@bp_teacher.route("/roster/reset-done")
def roster_reset_done():
    redir = teacher_required()
    if redir:
        return redir
    plain = session.pop("_teacher_reset_plain_password", None)
    sid = session.pop("_teacher_reset_student_id", None)
    if not plain or not sid:
        flash("会话已过期或无效。", "warning")
        return redirect(url_for("teacher.roster_view"))
    return render_template(
        "teacher/reset_password_done.html",
        plain_password=plain,
        student_id=sid,
    )


@bp_teacher.route("/assignments/<assignment_id>/status")
def assignment_submission_status(assignment_id: str):
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    a = _assignment_by_id(assignment_id)
    if not a:
        abort(404)
    rows = load_roster(cfg.ROSTER_PATH)
    mp_path = manifest_path_for(cfg.STORAGE_ROOT, assignment_id)
    man = load_manifest(mp_path)
    status_rows: list[dict] = []
    for row in rows:
        sid = row.get("学号", "").strip()
        st = man.get(sid) if sid else None
        submitted = bool(st and st.get("filename"))
        status_rows.append(
            {
                "row": row,
                "submitted": submitted,
                "first_upload_at": (st.get("first_upload_at", "") if st else ""),
                "last_updated_at": (st.get("last_updated_at", "") if st else ""),
                "filename": (st.get("filename", "") if st else ""),
            }
        )
    return render_template(
        "teacher/assignment_status.html",
        assignment=a,
        status_rows=status_rows,
    )


@bp_teacher.route("/assignments/<assignment_id>/download.zip")
def download_zip(assignment_id: str):
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    course = _course()
    if not _assignment_by_id(assignment_id):
        abort(404)
    rows = load_roster(cfg.ROSTER_PATH)
    mp_path = manifest_path_for(cfg.STORAGE_ROOT, assignment_id)
    man = load_manifest(mp_path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            sid = row.get("学号", "").strip()
            st = man.get(sid)
            if st and st.get("filename"):
                fp = cfg.STORAGE_ROOT / assignment_id / st["filename"]
                if fp.exists():
                    zf.write(fp, arcname=f"pdfs/{fp.name}")
        # ledger CSV
        led = io.StringIO()
        w = csv.writer(led)
        w.writerow(
            [
                "学号",
                "姓名",
                "专业",
                "学院",
                "first_submit_utc",
                "last_updated_utc",
                "submitted",
                "filename",
            ]
        )
        for row in rows:
            sid = row.get("学号", "").strip()
            st = man.get(sid)
            sub = bool(st and st.get("filename"))
            w.writerow(
                [
                    sid,
                    row.get("姓名", ""),
                    row.get("专业", ""),
                    row.get("学院", ""),
                    st.get("first_upload_at", "") if st else "",
                    st.get("last_updated_at", "") if st else "",
                    "yes" if sub else "no",
                    st.get("filename", "") if st else "",
                ]
            )
        zf.writestr("ledger.csv", led.getvalue().encode("utf-8-sig"))
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{course['course_id']}_{assignment_id}.zip",
    )


@bp_teacher.route("/export/full.csv")
def export_full():
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    course = _course()
    rows = load_roster(cfg.ROSTER_PATH)
    assigns = course.get("assignments", [])
    buf = io.StringIO()
    fieldnames = ["学号", "姓名", "专业", "学院"]
    for a in assigns:
        aid = a["id"]
        fieldnames.extend(
            [
                f"{aid}_first_submit",
                f"{aid}_last_updated",
                f"{aid}_submitted",
            ]
        )
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
        sid = row.get("学号", "").strip()
        out = {
            "学号": sid,
            "姓名": row.get("姓名", ""),
            "专业": row.get("专业", ""),
            "学院": row.get("学院", ""),
        }
        for a in assigns:
            aid = a["id"]
            mp = load_manifest(manifest_path_for(cfg.STORAGE_ROOT, aid))
            st = mp.get(sid)
            out[f"{aid}_first_submit"] = st.get("first_upload_at", "") if st else ""
            out[f"{aid}_last_updated"] = st.get("last_updated_at", "") if st else ""
            out[f"{aid}_submitted"] = "yes" if st and st.get("filename") else "no"
        w.writerow(out)
    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=full_export.csv"},
    )


def register_blueprints(app):
    app.register_blueprint(bp_public)
    app.register_blueprint(bp_student)
    app.register_blueprint(bp_teacher)
