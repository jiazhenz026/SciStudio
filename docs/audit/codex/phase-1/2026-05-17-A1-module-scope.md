# Summary

本报告仅执行 Phase 1 的“模块范围”审计：识别哪些模块在下一阶段需要建立接口 / schema / convention 的单一事实来源（SSoT）。本阶段不展开字段级接口细节。

# Module Inventory

| module_id | module_name | why_needs_ssot | authority_anchor |
|---|---|---|---|
| M01 | Core Data Foundation (`src/scieasy/core/types`, `src/scieasy/core/storage`, `src/scieasy/core/meta`, `src/scieasy/core/lineage`) | 是全系统数据语义与持久化语义的根；上层 Block / Engine / API 均依赖其类型与引用约定，需统一 schema 与约定边界 | ARCHITECTURE.md §4 Layer 1 |
| M02 | Block Contracts & Registry (`src/scieasy/blocks/base`, `src/scieasy/blocks/registry.py`, `src/scieasy/blocks/process`, `src/scieasy/blocks/io`, `src/scieasy/blocks/app`, `src/scieasy/blocks/code`, `src/scieasy/blocks/ai`, `src/scieasy/blocks/subworkflow`) | 承担端口类型、执行状态、配置与插件接入契约；若无统一约定会直接导致可组合性与跨模块兼容性退化 | ARCHITECTURE.md §3 Layer 2 |
| M03 | Execution Engine (`src/scieasy/engine`) | 负责 DAG 调度、worker 生命周期、资源/事件与 checkpoint；需要明确运行期协议与状态约定，避免执行行为漂移 | ARCHITECTURE.md §3 Layer 3 |
| M04 | AI Runtime Services (`src/scieasy/ai`, `src/scieasy/ai/agent/mcp`) | AI 生成/编排与运行时验证边界需要明确约束；MCP 工具面向自动化调用，必须有稳定 convention 才能可审计 | ARCHITECTURE.md §3 Layer 4 |
| M05 | API Surface & Realtime Channels (`src/scieasy/api`, `src/scieasy/api/routes`, `src/scieasy/api/ws.py`, `src/scieasy/api/sse.py`, `src/scieasy/api/schemas.py`) | 前后端与外部调用入口；REST/WS/SSE 语义不统一会破坏运行态一致性与可观测性 | ARCHITECTURE.md §3 Layer 5 |
| M06 | Workflow Definition & Validation (`src/scieasy/workflow`) | 工作流图是系统事实源；定义、序列化、校验与布局相关约定必须统一，避免编辑态/执行态分叉 | ARCHITECTURE.md §2.1 + §3 (workflow graph ownership) |
| M07 | Frontend State & Orchestration (`frontend/src/store`, `frontend/src/types`, `frontend/src/lib/api.ts`, `frontend/src/hooks`, `frontend/src/components`) | 前端虽非事实源，但承载编辑与可视化协作；需统一 UI-side contract（尤其 store slice / API typing / realtime handling）以对齐后端语义 | ARCHITECTURE.md §2.1 + §3 Layer 6 |
| M08 | CLI & Project Scaffolding (`src/scieasy/cli`, `src/scieasy/agent_provisioning`) | 负责项目初始化、脚手架与 agent 工作流接入；需要 convention 以保证生成物与核心契约一致 | ARCHITECTURE.md “Plugin ecosystem” + Layer 5/6 toolchain context |
| M09 | Plugin/Test Harness Boundary (`src/scieasy/testing`, `tests/plugins`, `tests/testing`, `tests/architecture`) | 生态扩展与回归验证边界；若无统一测试/兼容约定，插件与核心的契约将不可持续演进 | ARCHITECTURE.md Plugin ecosystem (ADR-025/026 references) |

# Proposed n value for Phase 1.5

建议 `n = 9`（按上述 9 个模块进入 Phase 1.5 的接口/schema/convention 细化）。

# Risks/ambiguities

- `src/scieasy/utils` 为跨层通用能力（constraints/logging/hashing/broadcast 等），其归属可能在 M01/M02/M03 之间存在重叠，需要在 Phase 1.5 先做“归属声明”。
- `src/scieasy/core/versioning` 与 `src/scieasy/api/routes/git.py`、前端 Git 组件存在跨层联动；若不先定义 authority hierarchy，后续容易出现同名语义多点定义。
- `blocks/ai` 与 `ai/agent/mcp` 的职责边界有并行演进风险（同属 AI 相关但位于不同层），Phase 1.5 需要先确认“运行时执行权限”和“建议生成权限”分界。
- 前端 `components` 目录既含纯展示组件也含流程语义组件，建议在 Phase 1.5 先切分“presentation convention”与“workflow-semantics convention”。
