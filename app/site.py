"""HTTP routes (student, teacher, public)."""
from __future__ import annotations

import csv
import hmac
import io
import secrets
import string
import zipfile
from itertools import zip_longest
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_wtf.csrf import validate_csrf
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import ValidationError

from app.course_loader import ensure_assignment_dirs, load_course_config
from app.course_registry import (
    course_config_path,
    course_roster_path,
    course_storage_root,
    course_templates_root,
    create_course,
    find_course,
    load_course_registry,
    save_course_registry_atomic,
)
from app.course_store import save_course_config_atomic, validate_and_build_course_dict
from app.forms import (
    AddStudentForm,
    CourseCreateForm,
    CourseSaveForm,
    DeleteRowForm,
    DeleteTemplateForm,
    EnrollForm,
    ResetPasswordForm,
    RosterImportForm,
    StudentLoginForm,
    TeacherLoginForm,
    TemplateUploadForm,
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
from app.template_store import remove_assignment_template, store_assignment_template, template_path

bp_public = Blueprint("public", __name__)
bp_student = Blueprint("student", __name__)
bp_teacher = Blueprint("teacher", __name__, url_prefix="/teacher")


def _cfg():
    return current_app.extensions["cfg"]


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _validate_pdf(data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise ValueError("文件过大")
    if not data.startswith(b"%PDF"):
        raise ValueError("仅支持 PDF 文件")


def _course_paths(course_id: str) -> dict[str, Path]:
    cfg = _cfg()
    return {
        "config": course_config_path(cfg.DATA_DIR, course_id),
        "roster": course_roster_path(cfg.DATA_DIR, course_id),
        "storage": course_storage_root(cfg.DATA_DIR, course_id),
        "templates": course_templates_root(cfg.DATA_DIR, course_id),
    }


def _get_course_or_404(course_id: str) -> dict:
    if not find_course(_cfg().DATA_DIR, course_id):
        abort(404)
    paths = _course_paths(course_id)
    course = load_course_config(paths["config"])
    ensure_assignment_dirs(paths["storage"], course.get("assignments", []))
    return course


def _assignment_by_id(course: dict, assignment_id: str) -> dict | None:
    for a in course.get("assignments", []):
        if a.get("id") == assignment_id:
            return a
    return None


def _active_courses() -> list[dict[str, str]]:
    courses = load_course_registry(_cfg().DATA_DIR).get("courses", [])
    return [c for c in courses if c.get("status") == "active"]


def _set_registry_title(course_id: str, title: str) -> None:
    cfg = _cfg()
    registry = load_course_registry(cfg.DATA_DIR)
    for course in registry.get("courses", []):
        if course.get("id") == course_id:
            course["title"] = title
            course["updated_at"] = course.get("updated_at", "")
            break
    save_course_registry_atomic(cfg.DATA_DIR, registry)
    current_app.extensions["course_registry"] = load_course_registry(cfg.DATA_DIR)


def student_required(course_id: str):
    if not session.get("student_id") or session.get("student_course_id") != course_id:
        flash("请先登录该课程的学生账号。", "warning")
        return redirect(url_for("student.login", course_id=course_id))
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
    return render_template("index.html", courses=_active_courses())


@bp_public.route("/courses/<course_id>")
def course_landing(course_id: str):
    course = _get_course_or_404(course_id)
    return render_template("course_landing.html", course=course)


@bp_student.route("/student/enroll")
def legacy_enroll():
    flash("请先选择课程。", "warning")
    return redirect(url_for("public.index"))


@bp_student.route("/student/login")
def legacy_login():
    flash("请先选择课程。", "warning")
    return redirect(url_for("public.index"))


@bp_student.route("/courses/<course_id>/student/enroll", methods=["GET", "POST"])
def enroll(course_id: str):
    course = _get_course_or_404(course_id)
    paths = _course_paths(course_id)
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
            session["_last_plain_course_id"] = course_id
            return rows

        try:
            update_roster(paths["roster"], mutator)
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("student/enroll.html", form=form, course=course)
        flash("请妥善保存系统生成的初始密码（仅此一次显示）。", "success")
        return redirect(url_for("student.enroll_done", course_id=course_id))

    return render_template("student/enroll.html", form=form, course=course)


@bp_student.route("/courses/<course_id>/student/enroll/done")
def enroll_done(course_id: str):
    _get_course_or_404(course_id)
    plain = session.pop("_last_plain_password", None)
    sid = session.pop("_last_plain_student", None)
    last_course_id = session.pop("_last_plain_course_id", None)
    if not plain or not sid or last_course_id != course_id:
        flash("会话已过期。", "warning")
        return redirect(url_for("student.enroll", course_id=course_id))
    return render_template("student/enroll_done.html", plain_password=plain, student_id=sid, course_id=course_id)


@bp_student.route("/courses/<course_id>/student/login", methods=["GET", "POST"])
def login(course_id: str):
    course = _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    form = StudentLoginForm()
    if form.validate_on_submit():
        sid = form.student_id.data.strip()
        password = form.password.data or ""
        rows = load_roster(paths["roster"])
        row = find_student(rows, sid)
        if not row or not row.get("密码哈希"):
            flash("学号或密码错误，或尚未完成初次注册。", "danger")
            return render_template("student/login.html", form=form, course=course)
        if not check_password_hash(row["密码哈希"], password):
            flash("学号或密码错误。", "danger")
            return render_template("student/login.html", form=form, course=course)
        session.permanent = True
        session["student_id"] = sid
        session["student_course_id"] = course_id
        flash("登录成功。", "success")
        return redirect(url_for("student.assignments", course_id=course_id))
    return render_template("student/login.html", form=form, course=course)


@bp_student.route("/courses/<course_id>/student/logout")
def logout(course_id: str):
    session.pop("student_id", None)
    session.pop("student_course_id", None)
    flash("已退出。", "info")
    return redirect(url_for("public.course_landing", course_id=course_id))


@bp_student.route("/courses/<course_id>/student/assignments")
def assignments(course_id: str):
    redir = student_required(course_id)
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    sid = session["student_id"]
    rows = load_roster(paths["roster"])
    row = find_student(rows, sid)
    storage = paths["storage"]
    states = {}
    for a in course.get("assignments", []):
        aid = a["id"]
        mp = load_manifest(manifest_path_for(storage, aid))
        states[aid] = mp.get(sid)
    return render_template(
        "student/assignments.html",
        row=row,
        assignments=course.get("assignments", []),
        states=states,
        course=course,
        course_id=course_id,
    )


@bp_student.route("/courses/<course_id>/assignments/<assignment_id>/template")
def assignment_template(course_id: str, assignment_id: str):
    course = _get_course_or_404(course_id)
    if not session.get("teacher") and (
        not session.get("student_id") or session.get("student_course_id") != course_id
    ):
        flash("请先登录该课程后下载模板。", "warning")
        return redirect(url_for("student.login", course_id=course_id))
    assignment = _assignment_by_id(course, assignment_id)
    if not assignment:
        abort(404)
    path = template_path(_course_paths(course_id)["templates"], assignment_id, assignment.get("template"))
    if path is None:
        abort(404)
    metadata = assignment.get("template") or {}
    return send_file(path, as_attachment=True, download_name=metadata.get("original_name") or path.name)


@bp_student.route("/courses/<course_id>/student/assignments/<assignment_id>/upload", methods=["POST"])
def upload_pdf(course_id: str, assignment_id: str):
    redir = student_required(course_id)
    if redir:
        return redir
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        abort(400)
    cfg = _cfg()
    course = _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    assignment = _assignment_by_id(course, assignment_id)
    if not assignment:
        abort(404)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("请选择 PDF 文件。", "danger")
        return redirect(url_for("student.assignments", course_id=course_id))
    sid = session["student_id"]
    rows = load_roster(paths["roster"])
    row = find_student(rows, sid)
    if not row:
        abort(403)
    data = upload.read()
    max_b = cfg.MAX_UPLOAD_MB * 1024 * 1024
    try:
        _validate_pdf(data, max_b)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("student.assignments", course_id=course_id))

    filename = build_submission_filename(
        course["course_id"],
        int(assignment.get("order", 1)),
        row.get("专业", ""),
        sid,
        row.get("姓名", ""),
    )
    dest_dir = paths["storage"] / assignment_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    mp_path = manifest_path_for(paths["storage"], assignment_id)
    prev = load_manifest(mp_path).get(sid)
    replace = prev is not None
    if dest_path.exists():
        replace = True
        dest_path.unlink()
    dest_path.write_bytes(data)
    update_manifest(mp_path, sid, filename, replace=replace)
    flash("上传成功。", "success")
    return redirect(url_for("student.assignments", course_id=course_id))


@bp_student.route("/courses/<course_id>/student/assignments/<assignment_id>/delete", methods=["POST"])
def delete_pdf(course_id: str, assignment_id: str):
    redir = student_required(course_id)
    if redir:
        return redir
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        abort(400)
    _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    sid = session["student_id"]
    mp_path = manifest_path_for(paths["storage"], assignment_id)
    man = load_manifest(mp_path)
    st = man.get(sid)
    if not st:
        flash("没有可删除的文件。", "warning")
        return redirect(url_for("student.assignments", course_id=course_id))
    fn = st.get("filename")
    if fn:
        p = paths["storage"] / assignment_id / fn
        if p.exists():
            p.unlink()
    remove_student_from_manifest(mp_path, sid)
    flash("已删除提交（可重新上传）。", "info")
    return redirect(url_for("student.assignments", course_id=course_id))


@bp_teacher.route("/login", methods=["GET", "POST"])
def teacher_login():
    cfg = _cfg()
    form = TeacherLoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data or ""
        if not cfg.TEACHER_PASSWORD:
            flash("服务器未配置教师密码（TEACHER_PASSWORD）。", "danger")
            return render_template("teacher/login.html", form=form)
        ok = username == cfg.TEACHER_USERNAME and hmac.compare_digest(
            password.encode("utf-8"),
            cfg.TEACHER_PASSWORD.encode("utf-8"),
        )
        if not ok:
            flash("用户名或密码错误。", "danger")
            return render_template("teacher/login.html", form=form)
        session.permanent = True
        session["teacher"] = True
        flash("教师登录成功。", "success")
        return redirect(url_for("teacher.courses"))
    return render_template("teacher/login.html", form=form)


@bp_teacher.route("/logout")
def teacher_logout():
    session.pop("teacher", None)
    flash("已退出教师账号。", "info")
    return redirect(url_for("public.index"))


@bp_teacher.route("/course")
def legacy_course_edit():
    redir = teacher_required()
    if redir:
        return redir
    return redirect(url_for("teacher.courses"))


@bp_teacher.route("/roster")
def legacy_roster_view():
    redir = teacher_required()
    if redir:
        return redir
    return redirect(url_for("teacher.courses"))


@bp_teacher.route("/courses")
def courses():
    redir = teacher_required()
    if redir:
        return redir
    registry = load_course_registry(_cfg().DATA_DIR)
    return render_template("teacher/courses.html", courses=registry.get("courses", []))


@bp_teacher.route("/courses/new", methods=["GET", "POST"])
def course_new():
    redir = teacher_required()
    if redir:
        return redir
    form = CourseCreateForm()
    if form.validate_on_submit():
        try:
            course = create_course(_cfg().DATA_DIR, form.course_id.data, form.course_title.data)
            data = validate_and_build_course_dict(course["id"], course["title"], ["hw01"], ["第一次作业"])
            paths = _course_paths(course["id"])
            save_course_config_atomic(paths["config"], data)
            update_roster(paths["roster"], lambda rows: rows)
            ensure_assignment_dirs(paths["storage"], data.get("assignments", []))
            current_app.extensions["course_registry"] = load_course_registry(_cfg().DATA_DIR)
            flash("课程已创建。", "success")
            return redirect(url_for("teacher.course_dashboard", course_id=course["id"]))
        except ValueError as e:
            flash(str(e), "danger")
    return render_template("teacher/course_new.html", form=form)


@bp_teacher.route("/courses/<course_id>")
def course_dashboard(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    rows = load_roster(_course_paths(course_id)["roster"])
    return render_template("teacher/course_dashboard.html", course=course, roster_count=len(rows))


@bp_teacher.route("/courses/<course_id>/settings", methods=["GET", "POST"])
def course_edit(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    form = CourseSaveForm()
    if request.method == "POST" and form.validate_on_submit():
        raw_ids = request.form.getlist("assignment_id")
        raw_titles = request.form.getlist("assignment_title")
        ids: list[str] = []
        titles: list[str] = []
        for raw_id, raw_title in zip_longest(raw_ids, raw_titles, fillvalue=""):
            if len(ids) >= 40:
                break
            aid = (raw_id or "").strip()
            title = (raw_title or "").strip()
            if aid or title:
                ids.append(aid)
                titles.append(title)
        try:
            data = validate_and_build_course_dict(
                form.course_id.data,
                form.course_title.data,
                ids,
                titles,
                existing_assignments=course.get("assignments", []),
            )
            if data["course_id"] != course_id:
                raise ValueError("course_id cannot be changed after creation")
            save_course_config_atomic(paths["config"], data)
            ensure_assignment_dirs(paths["storage"], data.get("assignments", []))
            _set_registry_title(course_id, data["course_title"])
            flash("课程配置已保存。若修改了作业 id，旧的 storage 子目录不会自动删除，可按需在服务器上清理。", "success")
            return redirect(url_for("teacher.course_edit", course_id=course_id))
        except ValueError as e:
            flash(str(e), "danger")

    rows = list(course.get("assignments", [])) or [{"id": "", "title": "", "order": 1, "template": None}]
    if request.args.get("add") == "1":
        rows.append({"id": "", "title": "", "order": len(rows) + 1, "template": None})
    if not form.is_submitted() or request.method == "GET":
        form.course_id.data = course.get("course_id", "")
        form.course_title.data = course.get("course_title", "")
    return render_template(
        "teacher/course_edit.html",
        form=form,
        assignment_rows=rows,
        course=course,
        upload_form=TemplateUploadForm(),
        delete_template_form=DeleteTemplateForm(),
    )


@bp_teacher.route("/courses/<course_id>/roster")
def roster_view(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    rows = load_roster(_course_paths(course_id)["roster"])
    return render_template(
        "teacher/roster.html",
        rows=rows,
        course=course,
        import_form=RosterImportForm(),
        add_form=AddStudentForm(),
        delete_form=DeleteRowForm(),
        reset_password_form=ResetPasswordForm(),
    )


@bp_teacher.route("/courses/<course_id>/roster/template.csv")
def roster_template(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    _get_course_or_404(course_id)
    buf = io.StringIO()
    csv.writer(buf).writerow(ROSTER_FIELDS)
    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=roster_template.csv"},
    )


@bp_teacher.route("/courses/<course_id>/roster/import", methods=["POST"])
def roster_import(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    form = RosterImportForm()
    if not form.validate_on_submit():
        flash("请选择 CSV 文件。", "danger")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
    raw = form.file.data.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    new_rows: list[dict[str, str]] = []
    for row in reader:
        new_rows.append({k: (row.get(k) or "").strip() for k in ROSTER_FIELDS})
    if not unique_student_ids(new_rows):
        flash("导入失败：学号重复。", "danger")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
    for row in new_rows:
        validate_roster_row(row)

    backup = paths["roster"].with_suffix(".bak.csv")
    if paths["roster"].exists():
        backup.write_bytes(paths["roster"].read_bytes())
    update_roster(paths["roster"], lambda _rows: new_rows)
    flash("名册已导入。", "success")
    return redirect(url_for("teacher.roster_view", course_id=course_id))


@bp_teacher.route("/courses/<course_id>/roster/add", methods=["POST"])
def roster_add(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    form = AddStudentForm()
    if not form.validate_on_submit():
        flash("表单无效。", "danger")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
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
        update_roster(paths["roster"], mutator)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
    flash("已添加学生（未注册前无密码哈希）。", "success")
    return redirect(url_for("teacher.roster_view", course_id=course_id))


@bp_teacher.route("/courses/<course_id>/roster/delete/<student_id>", methods=["POST"])
def roster_delete(course_id: str, student_id: str):
    redir = teacher_required()
    if redir:
        return redir
    form = DeleteRowForm()
    if not form.validate_on_submit():
        flash("提交无效。", "danger")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
    course = _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    sid = student_id.strip()
    update_roster(paths["roster"], lambda rows: [r for r in rows if r.get("学号", "").strip() != sid])
    for assignment in course.get("assignments", []):
        aid = assignment["id"]
        mp_path = manifest_path_for(paths["storage"], aid)
        st = load_manifest(mp_path).get(sid)
        if st and st.get("filename"):
            path = paths["storage"] / aid / st["filename"]
            if path.exists():
                path.unlink()
        remove_student_from_manifest(mp_path, sid)
    flash("已删除学生及其作业记录。", "success")
    return redirect(url_for("teacher.roster_view", course_id=course_id))


@bp_teacher.route("/courses/<course_id>/roster/reset-password/<student_id>", methods=["POST"])
def roster_reset_password(course_id: str, student_id: str):
    redir = teacher_required()
    if redir:
        return redir
    form = ResetPasswordForm()
    if not form.validate_on_submit():
        flash("提交无效。", "danger")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
    _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    sid = student_id.strip()

    def mutator(rows):
        row = find_student(rows, sid)
        if row is None:
            raise ValueError("名册中无此学号")
        plain = _generate_password()
        row["密码哈希"] = generate_password_hash(plain)
        session["_teacher_reset_plain_password"] = plain
        session["_teacher_reset_student_id"] = sid
        session["_teacher_reset_course_id"] = course_id
        return rows

    try:
        update_roster(paths["roster"], mutator)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
    flash("已生成新密码，请仅在安全环境下展示给学生。", "success")
    return redirect(url_for("teacher.roster_reset_done", course_id=course_id))


@bp_teacher.route("/courses/<course_id>/roster/reset-done")
def roster_reset_done(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    _get_course_or_404(course_id)
    plain = session.pop("_teacher_reset_plain_password", None)
    sid = session.pop("_teacher_reset_student_id", None)
    reset_course_id = session.pop("_teacher_reset_course_id", None)
    if not plain or not sid or reset_course_id != course_id:
        flash("会话已过期或无效。", "warning")
        return redirect(url_for("teacher.roster_view", course_id=course_id))
    return render_template("teacher/reset_password_done.html", plain_password=plain, student_id=sid, course_id=course_id)


@bp_teacher.route("/courses/<course_id>/assignments/<assignment_id>/template", methods=["GET"])
def teacher_template_download(course_id: str, assignment_id: str):
    redir = teacher_required()
    if redir:
        return redir
    return assignment_template(course_id, assignment_id)


@bp_teacher.route("/courses/<course_id>/assignments/<assignment_id>/template", methods=["POST"])
def template_upload(course_id: str, assignment_id: str):
    redir = teacher_required()
    if redir:
        return redir
    cfg = _cfg()
    course = _get_course_or_404(course_id)
    assignment = _assignment_by_id(course, assignment_id)
    if not assignment:
        abort(404)
    form = TemplateUploadForm()
    if not form.validate_on_submit():
        flash("请选择模板文件。", "danger")
        return redirect(url_for("teacher.course_edit", course_id=course_id))
    try:
        metadata = store_assignment_template(
            _course_paths(course_id)["templates"],
            assignment_id,
            form.file.data.filename,
            form.file.data.read(),
            cfg.MAX_TEMPLATE_MB * 1024 * 1024,
        )
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("teacher.course_edit", course_id=course_id))
    for item in course.get("assignments", []):
        if item.get("id") == assignment_id:
            item["template"] = metadata
            break
    save_course_config_atomic(_course_paths(course_id)["config"], course)
    flash("模板已上传。", "success")
    return redirect(url_for("teacher.course_edit", course_id=course_id))


@bp_teacher.route("/courses/<course_id>/assignments/<assignment_id>/template/delete", methods=["POST"])
def template_delete(course_id: str, assignment_id: str):
    redir = teacher_required()
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    assignment = _assignment_by_id(course, assignment_id)
    if not assignment:
        abort(404)
    form = DeleteTemplateForm()
    if not form.validate_on_submit():
        flash("提交无效。", "danger")
        return redirect(url_for("teacher.course_edit", course_id=course_id))
    remove_assignment_template(_course_paths(course_id)["templates"], assignment_id)
    assignment["template"] = None
    save_course_config_atomic(_course_paths(course_id)["config"], course)
    flash("模板已删除。", "success")
    return redirect(url_for("teacher.course_edit", course_id=course_id))


@bp_teacher.route("/courses/<course_id>/assignments/<assignment_id>/status")
def assignment_submission_status(course_id: str, assignment_id: str):
    redir = teacher_required()
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    assignment = _assignment_by_id(course, assignment_id)
    if not assignment:
        abort(404)
    paths = _course_paths(course_id)
    rows = load_roster(paths["roster"])
    manifest = load_manifest(manifest_path_for(paths["storage"], assignment_id))
    status_rows: list[dict] = []
    for row in rows:
        sid = row.get("学号", "").strip()
        st = manifest.get(sid) if sid else None
        status_rows.append(
            {
                "row": row,
                "submitted": bool(st and st.get("filename")),
                "first_upload_at": st.get("first_upload_at", "") if st else "",
                "last_updated_at": st.get("last_updated_at", "") if st else "",
                "filename": st.get("filename", "") if st else "",
            }
        )
    return render_template("teacher/assignment_status.html", assignment=assignment, status_rows=status_rows, course=course)


@bp_teacher.route("/courses/<course_id>/assignments/<assignment_id>/download.zip")
def download_zip(course_id: str, assignment_id: str):
    redir = teacher_required()
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    if not _assignment_by_id(course, assignment_id):
        abort(404)
    paths = _course_paths(course_id)
    rows = load_roster(paths["roster"])
    manifest = load_manifest(manifest_path_for(paths["storage"], assignment_id))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            sid = row.get("学号", "").strip()
            st = manifest.get(sid)
            if st and st.get("filename"):
                fp = paths["storage"] / assignment_id / st["filename"]
                if fp.exists():
                    zf.write(fp, arcname=f"pdfs/{fp.name}")
        ledger = io.StringIO()
        writer = csv.writer(ledger)
        writer.writerow(["学号", "姓名", "专业", "学院", "first_submit_utc", "last_updated_utc", "submitted", "filename"])
        for row in rows:
            sid = row.get("学号", "").strip()
            st = manifest.get(sid)
            submitted = bool(st and st.get("filename"))
            writer.writerow(
                [
                    sid,
                    row.get("姓名", ""),
                    row.get("专业", ""),
                    row.get("学院", ""),
                    st.get("first_upload_at", "") if st else "",
                    st.get("last_updated_at", "") if st else "",
                    "yes" if submitted else "no",
                    st.get("filename", "") if st else "",
                ]
            )
        zf.writestr("ledger.csv", ledger.getvalue().encode("utf-8-sig"))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{course['course_id']}_{assignment_id}.zip")


@bp_teacher.route("/courses/<course_id>/export/full.csv")
def export_full(course_id: str):
    redir = teacher_required()
    if redir:
        return redir
    course = _get_course_or_404(course_id)
    paths = _course_paths(course_id)
    rows = load_roster(paths["roster"])
    assignments = course.get("assignments", [])
    buf = io.StringIO()
    fieldnames = ["学号", "姓名", "专业", "学院"]
    for assignment in assignments:
        aid = assignment["id"]
        fieldnames.extend([f"{aid}_first_submit", f"{aid}_last_updated", f"{aid}_submitted"])
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    manifests = {a["id"]: load_manifest(manifest_path_for(paths["storage"], a["id"])) for a in assignments}
    for row in rows:
        sid = row.get("学号", "").strip()
        out = {"学号": sid, "姓名": row.get("姓名", ""), "专业": row.get("专业", ""), "学院": row.get("学院", "")}
        for assignment in assignments:
            aid = assignment["id"]
            st = manifests[aid].get(sid)
            out[f"{aid}_first_submit"] = st.get("first_upload_at", "") if st else ""
            out[f"{aid}_last_updated"] = st.get("last_updated_at", "") if st else ""
            out[f"{aid}_submitted"] = "yes" if st and st.get("filename") else "no"
        writer.writerow(out)
    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={course_id}_full_export.csv"},
    )


def register_blueprints(app):
    app.register_blueprint(bp_public)
    app.register_blueprint(bp_student)
    app.register_blueprint(bp_teacher)
