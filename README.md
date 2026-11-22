# 开题手记 v1.0

面向高中科研开题的师生工作台。学生在 Codex 与 AI 教练讨论，在网页核对阶段成果并提交开题稿。老师可以在网页手工审阅，也可以请 Codex 辅助整理建议，再发布正式决定。

## 本地启动

在仓库根目录运行，需 Python 3.12（网站最低支持 3.10）。

```powershell
python -B -m proposal_app.server --db proposal_app/local_data/demo.sqlite3 --port 8767
```

打开 [本地演示站](http://127.0.0.1:8767/)。新建演示库生成学生 `student`、`student2` 和老师 `teacher`，密码均为 `yanjiu123`。如需体验从网页打开 Codex、安装 Research Coach 插件或创建课堂账号，见[运行与打包](proposal_app/README.md)。

## 从哪里开始

| 要做什么 | 入口 |
| --- | --- |
| 了解网站、Codex 和插件如何配合 | [系统架构简介](docs/开题手记-系统架构简介.md) |
| 了解师生怎么用 | [师生使用指南](docs/开题手记-设计思路与师生使用指南.md) · [插件安装与排查](docs/开题手记-插件安装与使用.md) |
| 开发和验收 | [应用流程与数据边界](docs/current-application-flow.md) · [运行、打包及测试](proposal_app/README.md) |
| 修改教学规则 | [学生 Skill](skills/research-proposal-coach/SKILL.md) · [老师 Skill](skills/research-proposal-review/SKILL.md) |

网页资源位于 `proposal_app/static/`。指南所用的三张合成演示截图及 H5 阅读版源文件位于 `docs/h5/`。
