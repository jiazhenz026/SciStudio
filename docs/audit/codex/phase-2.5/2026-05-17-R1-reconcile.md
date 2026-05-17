# Phase 2.5 Reconcile (R1) — Unified Candidate Interface List

Date: 2026-05-17  
Role: Phase 2.5 reconciler R1 (Codex)  
Inputs used (strict):
- Phase 2: `docs/audit/codex/phase-2/2026-05-17-C1-abcd.md`, `...C2...`, `...C3...`
- Phase 1.5 evidence backtrace: all six reports under `docs/audit/codex/phase-1.5/`

---

## Reconcile policy

- 优先采用“最保守且可证据回溯”的统一结论：当 C2/C3 给出更高风险等级且能被 phase-1.5 证据支撑时，倾向更严格等级。
- `action` 语义：
  - `code-change`: 需要实现侧收敛。
  - `docs-fix`: 主要是文档锚点/契约说明不足。
  - `none`: 当前无需改动。
- `争议标记`：
  - `yes`: C1/C2/C3 存在等级分歧或解释分歧。
  - `no`: 基本一致。

---

## 统一候选接口清单（模块 -> 接口项）

| 模块 | 接口项 | 最终ABCD | 关键证据（phase-2 + phase-1.5回溯） | 建议 action | 争议标记 |
|---|---|---|---|---|---|
| M01 Core Data Foundation | DataObject 三槽元数据 + typed object contract | **B** | C1=A；C2=B；C3=B。phase-1.5 `A-code-1-M01-M02` 显示核心类型契约稳定；`A-diff-all` 指出引用语义/重建路径张力。 | docs-fix | yes |
| M01 Core Data Foundation | lineage 与 git 双层历史（`workflow_git_commit` join） | **A** | C1=A 且给出架构锚点；C2/C3 未提出该项冲突；phase-1.5 `A-docs-all` 与 `ARCHITECTURE`口径一致。 | none | no |
| M02 Block Contracts & Registry | Block 基础契约（typed ports, `run(inputs, config)`, lifecycle） | **A** | C1=A；C2/C3整体给B但未否定基础契约本体。phase-1.5 `A-code-1-M01-M02` 与 `A-docs-all` 均有明确接口面。 | none | yes |
| M02 Block Contracts & Registry | 动态/变长端口（`dynamic_ports` / effective ports） | **A** | C1=A；phase-1.5 code+docs 双证据一致；C2/C3未给出针对该子项的漂移证据。 | none | no |
| M02 Block Contracts & Registry | registry 严格校验 vs fallback/warning 降级路径 | **B** | C1=B；C2=B；C3=B。phase-1.5 `A-code-1-M01-M02` 与 `A-diff-all` 均指向强弱约束并存。 | docs-fix | no |
| M03 Execution Engine | DAG 调度 + block 生命周期事件协议 | **A** | C1=A；C2/C3给B主要因职责面偏宽，不是该接口缺失。phase-1.5 `A-code-2-M03-M04` 证明协议面完整。 | none | yes |
| M03 Execution Engine | checkpoint wire schema（collection/storage_ref 结构） | **B** | C1=B（字段级文档锚点不足）；C2/C3 维持B。phase-1.5 `A-code-2-M03-M04` 有实现形状但 docs 集中度不足。 | docs-fix | no |
| M04 AI Runtime Services | “AI proposal, runtime validate/execute”边界 | **A** | C1=A；C2/C3=B但主要担忧运行路径复杂度。phase-1.5 `A-code-2-M03-M04` + `A-docs-all` 对原则一致。 | none | yes |
| M04 AI Runtime Services | 双通道运行（loopback + in-process fallback）审计可解释性 | **B** | C1=B；C2=B；C3=B。phase-1.5 `A-diff-all` 指出双通道复杂度，文档未充分结构化声明。 | docs-fix | no |
| M05 API Surface & Realtime | REST block/workflow schema 契约暴露 | **A** | C1=A；C2/C3 的风险集中在 realtime/stringly & 跨层耦合，而非 REST 主契约缺失。phase-1.5 `A-code-3-M05-M06` 支撑接口存在。 | none | yes |
| M05 API Surface & Realtime | WS/SSE 事件帧 schema 类型化程度（stringly-typed 风险） | **C** | C1=B；C2=C；C3=B。phase-1.5 `A-code-3-M05-M06` + `A-diff-all` 对字符串协议与耦合点有直接证据；按保守策略上调为C候选。 | code-change | yes |
| M06 Workflow Definition & Validation | Workflow graph 作为 SoT + `validate_workflow` | **B** | C1=A；C2=B；C3=C。phase-1.5 `A-code-3-M05-M06` 明确 registry 可用性影响校验深度；SoT 原则成立但强度非一致。 | docs-fix | yes |
| M06 Workflow Definition & Validation | registry 有/无导致校验强度分层（strict vs warning/fallback） | **C** | C1=B；C2=B；C3=C（重点项）。phase-1.5 `A-code-3-M05-M06` 与 `A-diff-all` 直接支撑“同图不同深度诊断”。 | code-change | yes |
| M07 Frontend State & Orchestration | 前端仅编辑/展示层（非运行时真相） | **B** | C1=A；C2=C；C3=B。phase-1.5 `A-code-4-M07-M08` 支持前端投影定位，但 `A-diff-all` 给出反向耦合迹象。 | docs-fix | yes |
| M07 Frontend State & Orchestration | 后端 watcher/协议对前端字段形状耦合 | **C** | C1=B；C2=C；C3=B。phase-1.5 `A-diff-all` 明确提示协议耦合；按保守策略定C候选。 | code-change | yes |
| M08 CLI & Scaffolding | CLI install / mcp-bridge（claude/codex, user/project） | **A** | C1=A；C3=A；C2=B（偏文档集中度）。phase-1.5 `A-code-4-M07-M08` 与 `A-docs-all` 对契约本体一致。 | none | yes |
| M08 CLI & Scaffolding | scaffold 生成物持续对齐 core contract 的可验证规则 | **B** | C1=B；C2=B；C3对M08整体更乐观但未反驳该子项。phase-1.5 `A-diff-all`/`A-docs-all` 指向规则化锚点不足。 | docs-fix | yes |
| M09 Plugin/Test Harness | 插件入口（blocks/types/apps entry points）+ 测试边界 | **B** | C1=A；C2=B；C3=B。phase-1.5 `A-docs-all` 显示能力存在，但“失败分层/索引集中度”不足。 | docs-fix | yes |
| M09 Plugin/Test Harness | `IOBlock.supported_extensions`（文档先行，待补齐） | **C** | C1=C 明确标注；C2/C3未给出反证。phase-1.5 `A-docs-all` 直指“文档已定义、实现后续补齐”。 | code-change | yes |

---

## 汇总视图（候选）

- **A（6项）**：M01-2, M02-1, M02-2, M03-1, M05-1, M08-1
- **B（8项）**：M01-1, M02-3, M03-2, M04-2, M06-1, M07-1, M08-2, M09-1
- **C（5项）**：M05-2, M06-2, M07-2, M09-2, （保守上调项见表）
- **D（0项）**：当前输入范围内无阻断级直接证据

---

## 争议焦点（供下一阶段仲裁）

1. **M05/M07 是否从 B 升 C**：C2更激进，C1/C3相对保守；但 phase-1.5 diff 证据确有跨层耦合与 stringly 协议风险。
2. **M06 是否整体升 C**：C3将“校验强度随 registry 变化”视为显著偏差；C1保持B。建议把该子项（M06-2）先按 C 处理。
3. **M08/M09 的“能力存在 vs 文档集中度”**：实现多为可用，争议主要在文档是否足够成为“单一权威入口”。

