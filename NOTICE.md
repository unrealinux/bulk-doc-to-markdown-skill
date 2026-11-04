# 来源与归属

本仓库是一个 **Agent Skill**，把文档转成 Markdown。转换引擎是上游开源项目，本仓库不含它的代码：

- 上游仓库：[microsoft/markitdown](https://github.com/microsoft/markitdown)
- 上游许可：MIT，`Copyright (c) Microsoft Corporation`
- 本技能验证的上游版本：**0.1.8**（运行时由 uv 按 `markitdown[docx,xls,xlsx,pptx,pdf]==0.1.8` 安装，装进 uv 缓存，不进本仓库）
- 离线包（`vendor/python/`）里会带上一份 0.1.8 的副本，那是构建产物，不在 git 历史里

## 本仓库做了什么

- `scripts/convert.py`：包装上游，负责 uv 环境、单文件/URL/stdin 输入、批量目录（同一解释器内转换、`--json`、跳过原因上报）、`--extra` 合成依赖、`--style-map` 走 Python API（上游 CLI 表达不了）
- `scripts/package_skill.py`：打成可分发的 zip，含平台上传用的 `--flat` 平铺包
- `scripts/build_offline_bundle.py`：构建自带 CPython 的离线包
- `evals/`：33 条评测与纯标准库夹具
- `SKILL.md` / `references/formats.md`：给模型读的说明与格式边界

## 边界声明

- 本仓库与 **Microsoft 无隶属关系**，非官方项目；上游的 MIT 许可与版权声明予以保留，见 `LICENSE`
- **不做 OCR**：扫描件 PDF、图片里的文字转换后为空，这是上游能力边界，不是本仓库的缺陷
- 上游行为按 0.1.8 校准并钉死版本；升级 markitdown 需要同步复核 `SKILL.md`、`references/formats.md` 与评测里的源码级守卫
- 运行时要联网下载上游包（离线包除外），转换本身不再联网，除非用了 Azure / 音频转写这类服务型后端

## 版权

- 上游 `markitdown`：MIT，`Copyright (c) Microsoft Corporation`，运行时安装，本仓库未复制其源码
- 本仓库（`SKILL.md`、`scripts/`、`evals/`、`README.md`、`NOTICE.md`）：`Copyright (c) 2026 unrealinux`，MIT
