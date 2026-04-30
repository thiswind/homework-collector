from flask_wtf import FlaskForm
from wtforms import FileField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired


class StudentLoginForm(FlaskForm):
    student_id = StringField("学号", validators=[DataRequired()])
    password = PasswordField("密码", validators=[DataRequired()])
    submit = SubmitField("登录")


class EnrollForm(FlaskForm):
    student_id = StringField("学号", validators=[DataRequired()])
    name = StringField("姓名", validators=[DataRequired()])
    submit = SubmitField("验证并生成初始密码")


class TeacherLoginForm(FlaskForm):
    username = StringField("用户名", validators=[DataRequired()])
    password = PasswordField("密码", validators=[DataRequired()])
    submit = SubmitField("登录")


class AddStudentForm(FlaskForm):
    seq = StringField("序号")
    college = StringField("学院", validators=[DataRequired()])
    major = StringField("专业", validators=[DataRequired()])
    student_id = StringField("学号", validators=[DataRequired()])
    name = StringField("姓名", validators=[DataRequired()])
    submit = SubmitField("添加")


class RosterImportForm(FlaskForm):
    file = FileField("CSV 文件", validators=[DataRequired()])
    submit = SubmitField("上传导入")


class DeleteRowForm(FlaskForm):
    submit = SubmitField("删除")


class ResetPasswordForm(FlaskForm):
    submit = SubmitField("重置密码")


class CourseSaveForm(FlaskForm):
    course_id = StringField("课程代码 course_id", validators=[DataRequired()])
    course_title = StringField("课程名称", validators=[DataRequired()])
    submit = SubmitField("保存课程配置")

