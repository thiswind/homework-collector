# Homework Collector

Homework Collector 是一个文件存储的 Flask 收作业系统，用于多门课程同时收集学生 PDF 作业。系统不依赖数据库；课程、学生名册、作业配置、模板文件、学生提交记录都保存在运行时数据目录中，便于在普通 Linux 服务器上用 Python 虚拟环境部署。

## 当前能力

- 多课程管理：教师可以创建课程，分别维护课程名称、学生名册、作业列表和作业标题。
- 学生注册与登录：学生按课程使用学号和姓名注册，系统生成一次性初始密码，之后登录提交作业。
- 作业提交：学生按作业上传或替换 PDF，也可以删除自己的提交。
- 作业模板：教师可为每次作业上传模板，支持 `.pdf`、`.doc`、`.docx`、`.xls`、`.xlsx`、`.ppt`、`.pptx`、`.zip`。
- 教师管理：教师可查看每门课的提交状态，导出 CSV，下载单次作业 ZIP 包，导入/维护名册，重置学生密码。
- openEuler 部署：已按 openEuler 22.03、Python 3.9、venv + gunicorn + nginx 的形态验证。

## 数据目录结构

运行时状态默认保存在 `DATA_DIR` 下：

```text
DATA_DIR/
  courses.yaml
  courses/
    <course_id>/
      course.yaml
      roster.csv
      templates/
        <assignment_id>/
          <template file>
      storage/
        <assignment_id>/
          _manifest.json
          *.pdf
```

说明：

- `courses.yaml` 是课程注册表。
- 每门课有独立的 `course.yaml`、`roster.csv`、模板目录和提交目录。
- `_manifest.json` 保存每次作业的提交记录。
- 首次启动时，如果还没有课程注册表，系统会从 `config/course.yaml` 创建默认课程，并在存在 `点名册.csv` 时初始化名册。

不要把 `DATA_DIR`、真实名册、作业模板、学生提交文件或 `.env` 提交到仓库。

## 页面流程

### 学生

1. 打开首页，选择课程。
2. 使用“学生注册”输入学号和姓名。
3. 系统生成初始密码，学生保存后使用该密码登录。
4. 在作业列表中下载教师模板，上传对应 PDF 作业。
5. 如需修改，可重新上传覆盖；如需撤回，可删除自己的提交。

### 教师

1. 访问教师入口并登录。
2. 在课程列表中创建或进入课程。
3. 为课程维护学生名册和作业设置。
4. 为每次作业上传模板文件。
5. 查看提交状态、导出汇总 CSV、下载作业 ZIP 包。
6. 必要时为学生重置密码。

## 本地开发

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export SECRET_KEY="dev-secret"
export TEACHER_PASSWORD="your-teacher-password"
flask --app app:create_app run --debug
```

打开：

```text
http://127.0.0.1:5000
```

健康检查：

```text
http://127.0.0.1:5000/health
```

## 测试

```bash
pytest
```

测试覆盖范围包括课程注册表、教师课程管理、作业提交状态、教师重置密码和模板文件存储。

## 环境变量

参考 `.env.example`。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FLASK_ENV` | `development` | Flask 运行环境。生产部署时设为 `production`。 |
| `SECRET_KEY` | 无安全默认值 | Flask 会话密钥，生产环境必须设置强随机值。 |
| `DATA_DIR` | `data` | 运行时数据根目录。 |
| `COURSES_REGISTRY` | `data/courses.yaml` | 课程注册表路径。 |
| `COURSES_ROOT` | `data/courses` | 多课程数据根目录。 |
| `TEACHER_USERNAME` | `teacher` | 教师账号用户名。 |
| `TEACHER_PASSWORD` | `change-teacher-password` | 教师账号密码，生产环境必须在仓库外设置。 |
| `MAX_UPLOAD_MB` | `20` | 学生 PDF 上传大小限制。 |
| `MAX_TEMPLATE_MB` | `50` | 教师模板文件上传大小限制。 |
| `DISPLAY_TZ` | `Asia/Shanghai` | 页面显示时间使用的时区。 |
| `PERMANENT_SESSION_LIFETIME` | `28800` | 会话有效期，单位秒。 |
| `WTF_CSRF_ENABLED` | `true` | 是否启用 CSRF 防护。 |

以下旧变量仍保留用于迁移兼容，但新课程操作使用 `DATA_DIR/courses/` 布局：

- `ROSTER_PATH`
- `STORAGE_ROOT`
- `COURSE_CONFIG`

## openEuler 服务器部署

已验证的目标形态：

- openEuler 22.03
- Python 3.9
- 无 Docker/Podman 依赖
- 不要求服务器安装 git
- 使用源码包上传、venv、gunicorn、nginx、systemd 或手工进程管理

非破坏性的应用 smoke 启动示例：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt gunicorn
env DATA_DIR=/home/thiswind/homework-data \
  SECRET_KEY='replace-with-strong-random' \
  TEACHER_PASSWORD='replace-with-strong-password' \
  .venv/bin/gunicorn -b 127.0.0.1:18080 'app:create_app()'
```

服务器本机检查：

```bash
curl -sfS http://127.0.0.1:18080/health
```

推荐生产访问路径：

```text
browser -> nginx:80/443 -> gunicorn:127.0.0.1:18080
```

不要把 gunicorn 端口直接暴露到公网或不可信网络。正式部署时应使用 HTTPS 或可信反向代理，并限制 `DATA_DIR` 的文件系统访问权限。

## 当前预览部署记录

本项目已在 openEuler 服务器上按以下方式验证：

- 应用目录：`/home/thiswind/homework-preview/release-20260605`
- 数据目录：`/home/thiswind/homework-preview-data`
- gunicorn：`127.0.0.1:18080`
- nginx：公网/内网 `:80` 反向代理到 gunicorn
- 健康检查：`/health`

该预览环境用于人工测评，不应视为永久生产配置。

## 安全注意事项

- 生产环境必须设置强 `SECRET_KEY`。
- 生产环境必须在仓库外设置强 `TEACHER_PASSWORD`。
- 不要提交 `.env`、`data/`、真实课程目录、学生名册、模板、提交文件或导出的 ZIP/CSV。
- 运行时数据目录应只对应用进程和运维用户可读写。
- 真实部署应使用 HTTPS 或可信反向代理。
- gunicorn 建议只绑定 `127.0.0.1`，由 nginx 对外提供服务。

## 仓库说明

仓库中仍保留早期 Docker/Fly 相关文件，但当前主要部署路线是 openEuler 上的 venv + gunicorn + nginx。Docker/Fly 文件不代表当前服务器的推荐部署方式。
