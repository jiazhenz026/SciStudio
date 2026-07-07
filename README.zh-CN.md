<div align="center">

<img src="desktop/assets/icon.png" alt="SciStudio" width="120" />

# SciStudio

**为你的科研而生:每一份数据,每一个工具,汇于同一条工作流。**

[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/jiazhenz026/SciStudio/actions/workflows/ci.yml/badge.svg)](https://github.com/jiazhenz026/SciStudio/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-blue.svg)](https://jiazhenz026.github.io/SciStudio/)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2.svg?logo=discord&logoColor=white)](https://discord.gg/5b7kTRU2k)

[English](README.md) | **简体中文**

</div>

---

<div align="center">

<!-- Drop the home-page workflow canvas screenshot at docs/assets/scistudio-canvas.png -->
<img src="docs/assets/scistudio-canvas.png" alt="SciStudio workflow canvas" width="820" />

</div>

## SciStudio 是什么?

SciStudio 是一个**面向多模态科学数据的 AI 原生工作流运行时**。
显微成像、LC-MS、光谱、表格、仪器文件——每一种模态往往都需要各自的软件和格式。
SciStudio 把这些散落在桌面上、彼此独立的应用、脚本和文件收拢到同一个工作台上,
让带类型的**区块(blocks)**接线成一条完整的工作流。

- **每种模态,同一张图** —— 成像、LC-MS、光谱、表格与文件共享带类型的数据,
  在同一条工作流中流转。
- **沿用你现有的工具,而不是替换它们** —— 把 R 或 Python 脚本当作普通区块运行,
  也能像区块一样在流程中启动 Fiji 等桌面应用。
- **AI 原生** —— 内置助手(Claude Code 或 Codex)帮你搭建工作流、编写新区块、
  并检视你的数据。
- **手动步骤是一等公民** —— 审阅、标注、审批都是真正的工作流步骤,而非临时变通。
- **可扩展** —— 添加你自己的区块、数据类型和图表,并以可安装的软件包形式分享出去。

## 安装

### 面向使用者

从 [**Releases 页面**](https://github.com/jiazhenz026/SciStudio/releases) 下载最新的
SciStudio 桌面应用 —— macOS 的 `.dmg` 或 Windows 安装包。打开即用;Python 与全部
依赖都已内置,无需另行配置。

随后按 [**快速上手**](https://jiazhenz026.github.io/SciStudio/user-guide/getting-started.html) 操作。

### 面向开发者(从源码运行)

```bash
git clone https://github.com/jiazhenz026/SciStudio.git
cd SciStudio

# Python 后端(使用 conda 环境或 virtualenv)
python -m pip install ".[dev]"

# 前端依赖
npm --prefix frontend install

# 以源码运行桌面应用:
# 前端使用 Vite HMR + SciStudio 后端 + Electron。
npm --prefix desktop run dev
```

前端改动会热更新;后端改动需重启该命令才能生效。打包应用(`.dmg` /
Windows 安装包)的说明见 [`desktop/README.md`](desktop/README.md)。

## 文档

完整文档见 **[jiazhenz026.github.io/SciStudio](https://jiazhenz026.github.io/SciStudio/)**:

- [**用户指南**](https://jiazhenz026.github.io/SciStudio/user-guide/README.html)
  —— 搭建与运行工作流、预览数据、历史与分支、AI 助手,以及编写你自己的区块、
  类型和图表。
- [**快速上手**](https://jiazhenz026.github.io/SciStudio/user-guide/getting-started.html)
  —— 从全新安装到跑通第一条工作流。
- [**API 参考**](https://jiazhenz026.github.io/SciStudio/user-guide/api-reference/index.html)
  —— 你可以依赖的公开 API,附带签名与稳定性分级。
- [**软件包开发**](https://jiazhenz026.github.io/SciStudio/package-development/index.html)
  —— 构建可分发的 SciStudio 软件包(区块、类型、预览器)。
- [**架构**](docs/architecture/ARCHITECTURE.md) —— SciStudio 如何构建,以及为何如此设计。

用户指南与 API 参考和 SciStudio 注入到每个项目里的文档是同一套,因此你在线上读到的
内容与随应用一同发布的内容一致。

## 参与贡献

欢迎各种形式的贡献 —— 缺陷报告、功能建议、文档与代码。请先阅读
[**CONTRIBUTING.md**](CONTRIBUTING.md),完整的开发流程(分支、issue、gate、测试、
文档、评审)见 [`AGENTS.md`](AGENTS.md)。

若你想构建并发布自己的区块(而非改动核心),请参阅
[软件包开发指南](https://jiazhenz026.github.io/SciStudio/package-development/index.html)。

## 社区

在 SciStudio 处于 alpha 阶段期间,我们非常欢迎提问、反馈与缺陷报告:

- [Discord](https://discord.gg/5b7kTRU2k)
- [GitHub Issues](https://github.com/jiazhenz026/SciStudio/issues)

## 状态

SciStudio 目前处于 **alpha** 阶段,正在积极开发中。各版本之间接口与 API 可能发生变化;
[API 参考](https://jiazhenz026.github.io/SciStudio/user-guide/api-reference/index.html)
标注了每个公开符号的稳定性分级。

## 许可证

SciStudio 以 MIT 许可证发布。完整条款见 [LICENSE](LICENSE)。
