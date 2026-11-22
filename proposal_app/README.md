# 运行、打包与测试

从[仓库首页](../README.md)启动本地演示。网站使用 Python 标准库与 SQLite。需要提取有文字层的 PDF 时，在所用 Python 环境安装 `python -m pip install -r proposal_app/requirements-pdf.txt`。

## 连接 Codex

项目 v1.0 使用 Research Coach 插件 1.3.15。从仓库根目录构建站点所用的包，`--origin` 填师生电脑能访问的实际站点地址。本地试用可用以下命令。

```powershell
python -B -m proposal_app.build_plugin_pilot --target macos --origin http://127.0.0.1:8767 --output deliverables/research-coach-macos-8767.zip
python -B -m proposal_app.build_plugin_pilot --target windows --origin http://127.0.0.1:8767 --output deliverables/research-coach-windows-8767.zip
python -B -m proposal_app.server --db proposal_app/local_data/demo.sqlite3 --port 8767 --plugin-origin http://127.0.0.1:8767 --plugin-package deliverables/research-coach-windows-8767.zip --plugin-macos-package deliverables/research-coach-macos-8767.zip
```

Windows 包需在 Windows x64 上以 CPython 3.12 构建，将 Python 一同打包。macOS 包可跨平台构建，使用者需自行安装 Python 3.12 或更新版。两端都需安装并登录 Codex，打开网站的「插件」页按[安装指南](../docs/开题手记-插件安装与使用.md)连接。用 `/api/plugin-downloads` 核对实际提供的版本。

课堂实例使用独立数据库。先按角色创建账号，再用 `--no-demo` 启动。校内多台电脑共享时，按[局域网试教搭建指南](../docs/lan-https.md)配置 IP、HTTPS 和对应插件包。

```powershell
python -B proposal_app/classroom.py --db proposal_app/local_data/classroom.sqlite3 --role teacher --username teacher01 --name 张老师
```

将 `--role` 改为 `student` 可创建学生账号。模型和推理强度见[运行配置](配置说明.md)。

## 代码入口

| 要维护的功能 | 文件 |
| --- | --- |
| 路由、会话和 SQLite | `server.py` |
| 阶段、教学语境和研究对象 | `workflow.py`、`teaching_context.py`、`research_service.py`、`research_store.py` |
| 学生交接、固定稿及老师审阅 | `stage_handoff.py`、`stage_review.py`、`deliverables.py` |
| 站点连接、MCP 与插件打包 | `plugin_site.py`、`pilot_client.py`、`coach_mcp.py`、`review_mcp.py`、`build_plugin_pilot.py` |
| 网页 | `static/` |

## 运行回归

```powershell
python -B -m unittest discover -s proposal_app -t . -p 'test_*.py' -q
node --test proposal_app/test_plugin_frontend.cjs proposal_app/test_research_workspace.cjs proposal_app/test_review_form.cjs
```

浏览器回归需要 Node.js、Google Chrome 和 Playwright。在仓库根目录运行 `npm ci`，然后运行 `node proposal_app/test_stage_review_browser.cjs`。Windows 上构建上述两个安装包后，可再运行 `node proposal_app/test_install_connection.cjs` 验证连接向导。
