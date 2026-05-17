# Phase 2.5 Reconciler Report — R2 (Codex)

Date: 2026-05-17  
Role: Independent reconciler R2  
Inputs read:
- Phase 2: `docs/audit/codex/phase-2/2026-05-17-C1-abcd.md`, `2026-05-17-C2-abcd.md`, `2026-05-17-C3-abcd.md`
- Phase 1.5 (6 reports):
  - `docs/audit/codex/phase-1.5/2026-05-17-A-code-1-M01-M02.md`
  - `docs/audit/codex/phase-1.5/2026-05-17-A-code-2-M03-M04.md`
  - `docs/audit/codex/phase-1.5/2026-05-17-A-code-3-M05-M06.md`
  - `docs/audit/codex/phase-1.5/2026-05-17-A-code-4-M07-M08.md`
  - `docs/audit/codex/phase-1.5/2026-05-17-A-diff-all-M01-M09.md`
  - `docs/audit/codex/phase-1.5/2026-05-17-A-docs-all-M01-M09.md`

> Constraint honored: did **not** read any R1 output.

---

## Reconciliation rubric (R2)

- **A**: 文档与实现在该接口项上稳定一致。
- **B**: 主体一致，但存在降级路径、协议弱类型、文档锚点不足或边界耦合，需收敛。
- **C**: 存在显著契约偏差（同一语义在不同上下文下强度明显不同，或文档先行但实现缺口明确）。
- **D**: 阻断级冲突/缺口（当前输入未支持判到 D）。

争议标记规则：
- **LOW**：C1/C2/C3 基本同向。
- **MED**：存在 A↔B 或 B↔C 分歧，但证据可解释。
- **HIGH**：存在 C↔A、D 相关或证据冲突严重。

---

## Unified candidate interface list (module -> interface item)

| 模块 | 接口项（candidate） | 最终ABCD | 证据（phase-1.5/phase-2） | 建议 action | 争议 |
|---|---|---:|---|---|---|
| M01 | DataObject typed contract + 三槽元数据（framework/meta/user） | **A** | C1=A；C2/B、C3/B 主要担心“口径与耦合”，未否定契约存在；A-code-1 与 A-docs-all均列为核心稳定面 | **none** | MED |
| M01 | lineage 与 git dual-history（`workflow_git_commit` 作为 join） | **A** | C1=A 明确；C2/C3 未给反证；A-docs-all 与架构锚点一致引用 | **none** | LOW |
| M02 | Block 基础契约（typed ports / `run(inputs, config)` / state machine） | **A** | C1=A；C2/C3总体B但均承认契约完整；A-code-1 说明接口可枚举且稳定 | **none** | MED |
| M02 | 动态/变长端口（`dynamic_ports` / effective ports） | **A** | C1=A；C2/C3未提出该子项冲突；A-code-1 + A-docs-all 都有对齐描述 | **none** | LOW |
| M02 | Registry/validator 严格性与 fallback 共存（强约束等级） | **B** | C1=B、C2=B、C3=B 同向；A-code-1 + A-diff 均提到降级/软化路径 | **docs-fix** | LOW |
| M03 | DAG 调度 + 生命周期事件协议（READY/RUNNING/PAUSED...） | **A** | C1=A；C2/C3虽给模块B，但未否定协议存在；A-code-2 给出清晰执行接口面 | **none** | MED |
| M03 | Checkpoint wire schema（collection/storage_ref 字典形状） | **B** | C1=B（字段级文档锚点不足）；C2/C3未反驳；A-code-2有实现细节，A-docs-all 粒度偏高 | **docs-fix** | LOW |
| M03 | Scheduler 职责面偏宽（跨职责聚合） | **B** | C2/B、C3/B 共识；A-code-2 与 A-diff 有“职责面较宽”信号 | **code-change** | LOW |
| M04 | AI propose / runtime validate（AI不可绕过契约） | **A** | C1=A；C2/C3均承认主原则成立；A-code-2 + A-docs-all 对齐架构原则 | **none** | LOW |
| M04 | AI runtime 双通道（loopback + in-process fallback）审计复杂度 | **B** | C1=B、C2=B、C3=B 一致；A-code-2 + A-diff 均提双路径 | **docs-fix** | LOW |
| M05 | REST block/workflow schema 暴露接口 | **A** | C1=A；C2/C3 对模块整体更保守但未否定 REST 契约；A-code-3 与 A-docs-all 支持 | **none** | MED |
| M05 | WS/SSE 事件帧 schema（stringly-typed 程度） | **B** | C1=B、C3/B（明确 stringly-typed）；C2给模块C（跨层耦合）但该子项仍偏协议结构问题 | **code-change** | MED |
| M05 | API 层跨层动作（如 runtime refresh）/ watcher 反向耦合信号 | **C** | C2=模块C 的核心依据；C1在 M07 给出耦合B；C3也给出实时耦合风险；A-diff 为主证据 | **code-change** | MED |
| M06 | Workflow graph 为 SoT + `validate_workflow` 主契约 | **A** | C1=A；C2/B、C3/C 主要针对“强度分层”而非 SoT 原则本身；A-code-3 + A-docs-all 均确认主契约 | **none** | MED |
| M06 | validator 严格性随 registry 可用性变化（同图不同诊断深度） | **C** | C3= C 明确；C1/B、C2/B 承认该现象但降级判定；A-code-3 + A-diff 支持“上下文依赖强度差” | **code-change** | MED |
| M07 | 前端仅编辑/展示层（非运行时真相） | **A** | C1=A；C2/C3虽保守但未否认该原则；A-code-4 + A-docs-all 与架构主张一致 | **none** | MED |
| M07 | 后端 watcher/WS 对前端字段形状反向依赖 | **B** | C1=B；C2=模块C、C3=模块B 都指向同一风险；A-diff 提供耦合证据 | **docs-fix** | MED |
| M08 | CLI install / mcp-bridge 配置契约（claude/codex/user|project） | **A** | C1=A、C3=A；C2虽B但理由偏“文档集中度”；A-code-4 + A-docs-all 对齐充分 | **none** | LOW |
| M08 | scaffold 生成物与核心 contract 的可验证规则 | **B** | C1=B、C2=B；A-diff/A-docs-all 均提示“原则有，规则化校验锚点弱” | **docs-fix** | LOW |
| M09 | 插件入口（blocks/types/apps）+ 测试边界（harness/tests） | **B** | C1=A、C2/B、C3/B；A-docs-all 显示存在但“总表/失败分层”集中度不足 | **docs-fix** | MED |
| M09 | `IOBlock.supported_extensions`（文档先行，实现待补） | **C** | C1= C 明确标注；C2/C3未直接反证该子项；A-docs-all 明示“文档定义、实现后续补齐” | **code-change** | LOW |

---

## R2 synthesis notes

1. **Final distribution (R2)**
   - A: 9
   - B: 8
   - C: 3
   - D: 0

2. **Where C2/C3 are stricter than C1**
   - M05（跨层耦合）与 M06（validator 强度上下文依赖）是升级风险中心。
   - R2 在“原则项 vs 机制项”上拆分判定：原则仍可 A，但机制缺口可独立给 B/C。

3. **Action policy**
   - **code-change**: 仅用于会改变运行时语义一致性或跨层边界的项（M03职责聚合、M05耦合、M06强度漂移、M09实现缺口）。
   - **docs-fix**: 用于契约已在实现中存在，但文档锚点/强制等级/协议结构说明不足的项。
   - **none**: 对齐稳定、且无新增冲突证据。

4. **No-D rationale**
   - 现有输入未显示“阻断级边界破坏”或“无法工作级缺口”；主要问题为一致性强度与可解释性负担。

