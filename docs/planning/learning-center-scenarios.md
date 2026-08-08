# 学习中心 · 场景设计笔记（ADR-053）

owner 逐关设计，我记录。这份是草稿本，不是 spec。
**编号从 1 开始，内部与用户可见一致。**

## 全局约定

- 教程 = 一个个真实科研任务的"关卡"，像游戏关卡一样一关关设计。能力在任务里顺带学会，不按功能清单排。
- **所有教程里用户都不写代码**，需要的块 / 类型 / plot / 交互块都由教程预先写好，用户点一下就生成。
- 教学素材可以是"假"的（例如 segmentation 的方法选项），但**用户会看源码的地方必须是真的**
  （例如聚类算法）。
- **只能用 core 数据类型**：`Array` / `Series` / `DataFrame` / `Text` / `Artifact` / `CompositeData`。
  `Image`、`Spectrum` 等都属于 package，不能直接用。
- **Collection 不教**。它是内部传输协议，用户不需要知道。
- "坏掉/事故"不是通用设计原则，是某一关自己的剧情。
- 第一关必须零外部配置（ADR-053 §5.2）。
- **每关各自 bootstrap 一个独立项目**。关卡之间靠 My Library 传递成果。
- **ADR-053 会大修订，设计不受现行 ADR 条文限制。**
- **History** 是用户可见名；内部 key 仍是 `lineage`（[TabBar.tsx:39](frontend/src/components/BottomPanel.parts/TabBar.tsx#L39)）。
  架构文档 §9.7 还写着 "Lineage"，属于文档过时。

---

## 关卡 1 · 欢迎来到 SciStudio

**定位**：现有 tutorial 的改进版。教 SciStudio 的基本概念。

**剧情**
1. 拖一个 load 进画布
2. 点"创建 block" → 直接生成一个已经写好的块（用户不写代码）
3. 拖一个 save
4. 点 run → 数据分析出来了
5. 创建一个 plot → 同样是已经写好的 → 运行 → 图出来了
6. 提示 agent 不小心把工作流改错了 → 去 History 复原

**覆盖**：工作流是什么、block 是什么、plot 是什么、History 有什么用

**restore 语义（#2033 已落地，2026-08-07 核对）**：ADR-038 Addendum 1。实际形态比当初记的更宽：

- History 的 "Restore workflow" 改名为 **Restore**，范围从**单个 workflow YAML 扩大到那个 commit 的整棵树**，
  和 Git tab 的 Restore 完全一致。**这正是这一关需要的**——剧情里被改坏的如果只是工作流，
  旧行为也能救；但把块也改坏了就救不回来。现在两条路一样。
- restore 之前会跑**两项建议性检查**：输入文件变没变、环境有没有漂移。**只提示，不阻断**。
- 目标 commit 没有关联运行时（手动提交、`auto: pre-restore` 提交），UI 明说"无法检查"，
  **不会**报告"一切正常"。
- restore / merge / cherry-pick 之后会**刷新块注册表**（以前只有切分支会）。

教程**路由到 History tab**。这一关不再有前置依赖。

**教程要不要触发那两项检查**：剧情里工作流是教程刚改坏的，输入没变、环境没变，
所以检查会返回"没有漂移"。这是干净的——用户第一次见到 restore 就顺带看到它会先检查一下。
不用刻意造漂移，那是另一个话题。

---

## 关卡 2 · 类型是什么

**剧情**
1. 老板派了个图像分析的任务
2. 先看当前支持哪些 data type → 发现没有图像
3. 创建一个 **project 级别的 type：Image**（派生自 `Array`，顺带教子接父）
4. 拖 load，`core_type` 选 Image → 跑 → **撞上真实报错**
   `no load capability is registered for type 'Image'` → 引入 **IOBlock**
5. 再跑 → 读进来了，但**预览面板里看到的不是图像**，是核心 Array previewer 的数字热力表
   → 引入 **previewer**，创建项目级 previewer
6. 加 segmentation，跑一个 threshold → 效果不好
7. 去 **config 换一个方法** → 更差 → 再换回来（教 config；方法可以是假选项）
8. "要不加个交互式的手动改吧" → 创建**交互块**，手动删掉一个多余的 label
   → 顺带提 `interactive_memory`（记住这个决策，已实现，零成本）
9. 导出 DataFrame —— 每个细胞的 area
10. **结尾：My Library** —— 把这一关造的 Image 类型和 segmentation 块存进库

**三个转折全部是产品真实行为，没有一个是编的**
- 选了 Image 去 load → 真的报错（没有 load capability）
- 读进来了 → 真的显示成数字表格（previewer 沿类型链回落到 Array）
- 分割不好 → 真实的科研体验

**My Library 放这里的理由（关键）**
每关是独立项目 → 关卡 3 要复用 Image 类型和 segmentation 块，**用户必须在这一关结尾存进库**，
否则关卡 3 的新项目里根本没有。My Library 因此不是"提一嘴"，而是**两关之间的必经桥梁**：
不存 → 下一关得重造；存了 → 下一关拖出来就在。ADR-053 §3 的立论被用户亲身经历一次。

**已查证的事实**
- 自定义类型注册后**会**出现在 Load 块的 `core_type` 下拉里
  （[_config_enrichment.py:39](src/scistudio/blocks/io/_config_enrichment.py#L39)：剩余注册类型也列出，"never silently drops a type"）
- `format_capabilities` 是 IOBlock 子类的 ClassVar，扫描时注册
  （[io_block.py:98](src/scistudio/blocks/io/io_block.py#L98)、[_scan.py:63](src/scistudio/blocks/registry/_scan.py#L63)）
- 依赖够用：`tifffile>=2024.8` 是核心依赖，真 TIFF 零额外安装可读

**跨 spec 依赖**：第 2、3 步依赖 personal-tool-library spec 的 Data types tab 与"新建自定义类型"GUI 动作

---

## 关卡 3 · 多模态联合分析 + git 分支

**模态组合（已定）**：组织切片 **Image**（复用关卡 2 造的类型）+ **每个空间位置的表达矩阵 DataFrame**（core 内置）
- 对应关系靠**空间共配准**而非 ID join → "必须联合"成立，不可拆
- batch effect 是这个领域的原生词，第二批测序需要不同归一化参数，理由不用编
- 零新类型成本；数据只需示意（一张缩略切片 + 几百位置 × 几十基因）

**剧情**
1. 两个模态各起一条分支 —— **画布第一次出现分叉**，"多模态"在图形上直接可见
2. 图像分支：**直接复用关卡 2 造的 segmentation 块**分出组织区域（预处理缩成一步）
3. 表达分支：normalization
4. 汇入一个**联合分析块**（双输入）：用图像区域聚合落在区域内位置的表达谱，聚类，
   输出带 cluster 标签的表
5. **plot card 复习**：散点按空间坐标画、按 cluster 上色
6. 第二批实验有 batch effect → 两批需要不同 normalization 参数 → **git 建分支**，两个变体长期并存
7. 同一张 plot 在两个分支各跑一次对比 → 用户撞上"切回旧分支图还是旧的"
   → **git 存的是配方不是结果，必须重跑**

**用哪些内置块**
- **PairEditor：用**。双侧 variadic 2–8 端口（[pair_editor.py:80-95](src/scistudio/blocks/process/builtins/pair_editor.py#L80-L95)），
  用户接两个模态时必然碰到加端口，**可变端口自然带过，不用单列**。
  需在数据设计上造出顺序错位（两种导出的命名规则不同，排序自然错开，是真实痛点）。
- **DataRouter：不用**，和 git 分支抢位置。**MergeCollection：不用**，是同类型拼接。
  **MergeBlock：不用**，UI 已不暴露、代码 legacy、只实现了 concat。

**git 的必要性必须和关卡 2 区分**
- 关卡 2 = 试哪个参数好，试完就定（一次性改 config）
- 关卡 3 = 两批各需各的参数，都要长期保留、随时切回比较（两个版本并存）
- 架构 §4.6 原话可当台词：**一个分支代表一个数据情境下的工作流变体，合并往往不是目的**

**聚类要写真的**
- 用户会看源码；假聚类画出来是随机色块，一眼假
- **没有 scikit-learn，没有 scipy** → k-means 用 numpy 手写（约二十行，教程预生成）
- `matplotlib` 是核心依赖；**不要用 seaborn**（架构文档说可用，实际不在依赖列表）
- **聚类放块里，不放 plot 里**。plot 是 preview-only、不进 lineage、下次运行即覆盖（架构 §10.1）

**顺带教：怎么看一个 block 的源码**
- `resolve_block_source` 返回 `{path, source, language, origin}`，**不论核心/包/项目都能看**
  （[_block_source.py:7](src/scistudio/api/_block_source.py#L7) "regardless of origin"）→ 产品没有黑盒
- **"看"和"改"是两条路**：源码视图只读；改项目级块要从项目树打开 `blocks/*.py`（存盘热重载）

---

## 关卡 4 · AI 能帮你做什么（假 AI）

**目的**：告诉用户可以用 AI 做什么。

**核心设计（owner 定）**
- 问题：不知道用户用的什么 AI provider，也不该让用户为教程消耗自己的 token
- 方案：**做一个假的 AI 界面**，只让用户做规定好的操作，**不让自由探索**
- 教程里**明确告诉用户这是假 AI**，只为展示用法
- 结尾**自然弹窗**告诉用户怎么安装 AI
- **import 解锁就接在这一关之后**（"AI 能干这些 → 要不要让它把你整个代码库搬进来"）

**科学任务（已定）**：一批实验测量表，多样本 × 多指标，含离群值和缺失 → 做质控和统计汇总
- **不复用 My Library**（这一关用表格数据，关卡 2 存的 Image / segmentation 用不上）
- 全用 core `DataFrame`，零新类型

**设计标准（比选什么任务更要紧）**
1. **任务必须简单到用户能一眼判断 AI 做得对不对**。这一关的态度教学点是"agent 的产出要你自己看"；
   任务一复杂，用户只能盲信，还会养成盲信习惯。**关卡 4 的科学内容要比关卡 3 简单，不是更复杂。**
2. **数据用表格不用图像**。数字对不对用户自己看得出来，图像的对错要靠专业判断。
3. **debug 那步的错误要"看得见"**：写错列名 → KeyError → 日志里明明白白，用户能跟着推理。
   不要设计成隐蔽的逻辑错误（算出来了但是错的），那样用户只学到"AI 会出错，好可怕"。
4. **调参数要有科学意义**：阈值松紧影响保留多少数据、影响结论，不是"把 3 改成 5"。
5. **AIBlock 的 metadata 推测是全关最真实的痛点**：实验室天天拿到没有说明的 CSV，
   不知道哪列是什么、什么单位。这个用例本身有价值，不只是演示。

**展示哪几件事（按顺序）**
0a. **暖场**：问 AI —— SciStudio 是做什么的
0b. **过渡**：问 AI —— 都有哪些 block（演示 `list_blocks`，顺带让用户知道
    "面板里那些东西 AI 全都知道"，用户会自己想到"那它能不能帮我搭"）
    - 背后还有 MCP 的 `get_project_info` / `search_docs` / `get_doc` / `list_data`，
      加上架构 §7.4 的项目感知 prompt（项目名、根路径、有哪些工作流、装了哪些插件、git 状态）
1. **写一个自定义块**：离群值过滤块（QC filter）—— 简单、可验证
2. **搭一段工作流**：load → QC 过滤 → 统计汇总 → save
3. **debug 一个失败的运行**：agent 写的块列名写错了，跑挂，让它看日志自己修
   （`get_block_logs` / `get_run_status`）—— 报错是用户最无助的时刻，最有说服力
4. **看数据**：过滤后的表，agent 用 `preview_data` / `inspect_data` 看分布
5. **调参数**：离群阈值 3σ → 2σ，agent 看完分布建议调，保留的样本数跟着变
6. **画图**：过滤前后的分布对比（`scaffold_plot`）
7. **AIBlock**：给这批没有说明的原始文件推测 metadata（每列是什么、什么单位）
   —— 演示 AIBlock 与聊天的区别：聊天产出一段对话，
   AIBlock 产出**声明过类型、会被校验、进 lineage 的数据**

**脚本里安排一次 agent 犯错、然后被纠正**（已定）
真 agent 会犯错会来回试；假 AI 若是完美直线，用户装了真的以后会觉得被骗。
这一回合同时教了 ADR-053 §5 的态度：**agent 的产出要你自己看**。

**两处造假，性质不同**
1. **终端回放**（轻）：xterm 组件、AI Chat 标签页、标签条全真，只把字节流来源从 PTY 换成预录脚本。
   每段"回复"后面绑一次真实的文件写入 —— 复用"写文件动作绑在步骤上"那条基建要求。
   **假 AI 必须真的产生副作用**：agent 说加了个块，画布上就得真的多一个块。
2. **AIBlock**（已定方案）：教程提供 `AI Block (tutorial only)`，
   **直接继承 `AIBlock` 并覆写 `run`** 返回预置结果。
   - `_infer_category` 靠 isinstance 沿继承链推，注释明说 "Never reads a ClassVar override"
     （[_spec.py:270-275](src/scistudio/blocks/registry/_spec.py#L270-L275)）→ 图标颜色**抄不出来，只能继承**
   - 白拿：`base_category="ai"`（图标颜色一致）、`config_schema` 经 ADR-030 MRO 合并自动一致
   - 只改 `name` 和 `type_name`；放教程项目的 `blocks/`，不进教程库
   - 教程里明确告诉用户它和真的有区别

**"假 AI 做成一个 provider"这条路不通**（查证结论）
`ProviderDescriptor` 整个围绕"怎么启动并接线一个真 CLI"设计：可执行文件解析、
`CredentialProbe` 凭据探测、MCP 注入策略、system prompt 注入策略。回放用不上任何字段。

**结尾弹窗 = provider 介绍，不只是安装说明**
注册表里五个真 provider（[providers_registry.py:695](src/scistudio/ai/agent/providers_registry.py#L695)）：
**Claude Code / Codex / Kimi Code / Qoder / Qoder 国内版**，外加 `user-terminal` 伪 provider。
已经配好某一个的用户，多半不知道另外几个存在（尤其国内两个）→ 对他们说"还有这些也能用"。
弹窗之后**接 import 解锁**。

---

## 关卡 4 结尾 · import 弹窗

- 关卡 4 结束后弹 import 窗
- 用户可以 **skip for now**
- **跳过时必须告诉用户后面去哪找**：工具栏上常驻的 **"Bring in my work"**
  （work-import spec FR-001：永久可用、不受学习进度限制；FR-002：项目打开时启用）

**已落地（2026-08-08 复核）**：`src/scistudio/api/routes/work_import.py` +
`frontend/src/components/BringInMyWorkDialog.tsx`。教程文案要照实际形态写，两点：

- 对话框是**一页一个问题**的分页形式（#2001 最后几轮把大段说明文字砍掉改成分页的）。
  所以教程里不能说"填一张表"，得说"它会一步步问你几个问题"。
- provider 选择是**一个下拉列出全部**，不可用的**置灰不隐藏**。这和关卡 4 结尾
  "告诉用户有哪些 provider 可以用"是同一个意图 —— 弹窗自己就在做 provider 介绍，
  教程不用另讲一遍，指过去就行。

---

## 关卡 5 · 总结关

**形态（owner 定）**
- 一个 UI 窗口
- 顶部**一句话**讲 SciStudio 的核心概念
- 底下卡片排成 2 行（owner 最初说 6 张，后确认扩为 **8 张**，见下方"八张卡"）

**目的**：给用户做**系统的梳理**，告诉用户**都有什么资源、需要的东西去哪找**

**这一关不是介绍新东西，是给已经用过的东西起名字、排位置。**
六张卡正好对应前四关亲手做过的：workflow（关 1）、block（关 1/2/4）、
data type（关 2）、previewer（关 2）、plot card（关 1/3/4）。
这也顺带解释了纯阅读为什么能算完成 —— 它是**整理**，不是学习。

**与 ADR 冲突已豁免**：ADR-053 §2.2 现行规定"完成只授予跑完，Reading is not progress"，
这一关是纯阅读的 → ADR 大修订时改这条。

**八张卡（已定）**：`workflow` / `block` / `data type` / `previewer` / `plot card` /
`history` / `my library` / `others`

**每张卡点开是一个可翻页的页面。**

### block 卡的页面结构（owner 给的样板）
1. 第一页：block 是什么、做什么用
2. 逐个介绍六种基础类别：**IO / process / code / app / ai / subworkflow**
3. 那几个 built-in 的
4. 最后小提示：**一个 block 最好只做一件事**；交互式 block；让 AI 帮你写

**事实核对**
- 他列的六种正是产品内部的分类。`_infer_category` 注释原话：
  "Always returns one of the 6 base types (io, process, code, app, ai, subworkflow)"
  （[_spec.py:270-275](src/scistudio/blocks/registry/_spec.py#L270-L275)）
  → 总结关的分类 = 产品内部分类，用户建立的心智模型和系统一致
- built-in 实际是六个：**Load、Save、DataRouter、PairEditor、MergeCollection、Split**
  （[builtins/__init__.py](src/scistudio/blocks/process/builtins/__init__.py) 导出五个 process 内置 +
  io 的 `load_data` / `save_data`）。**MergeBlock 排除**：UI 已不暴露、代码 legacy、只实现 concat。
- **IO 类别只有两个块**：Load 和 Save，所有格式靠 capability 挂上去
  （`loaders/` 和 `savers/` 各只有一个块文件）。这是 canonical zone 那一课最具体的产品体现
  ——**"格式不是块，格式是能力"**。放在介绍 IOBlock 那一页讲，比抽象讲有效得多。
- **"一个 block 最好只做一件事"和 `my library` 卡是一体的**：只做一件事的前提是
  "它有地方可去"，否则拆细没有回报 —— 这正是 ADR-053 §3 的原论点。两张卡建议互相指一下。

### workflow 卡的页面结构（owner 定）
1. 什么是 workflow
2. **block 两端 port 的颜色是什么意思**
3. **怎么 run / run from here**
4. **怎么 tidy 和 focus**

**端口颜色的最终规则**（personal-tool-library spec §7.1，已定稿）
- 类型可以**自己声明外观**：填充色 `ui_color` + 环色 `ui_ring_color`（CSS hex），
  和块的 `ui_color` / `ui_icon` 是同一套先例
- 没声明的：核心类型用手工指定颜色，未知/插件类型回落到**确定性哈希色**
- **类型列表接口是全产品颜色的唯一真源**（FR-050）；画布端口颜色解析必须读它（FR-066）
- 连线颜色取自**源端口**的类型；画布上有类型图例列出当前活跃类型

**→ 关卡 2 的零成本增强**：spec 要求新建自定义类型的**模板骨架必须包含颜色字段**
（原文理由："让用户发现声明颜色这件事是可行的"）。所以关卡 2 造 Image 时
**顺手让用户给自己的类型挑个颜色**，到关卡 3 双分支画布上，Image 端口就是他自己选的颜色，
和表达矩阵那条分支一眼可辨。用户会记住"我造的类型，连它在画布上长什么样都是我定的"。

**run 只有两个层次**（#2033 已落地，2026-08-07 核对）
- 重跑**整个工作流**
- **run from here**：从某个块开始跑（基于最新中间状态的 checkpoint）；
  节点上原来那个 restart 就是它

**⚠️ 我当初记的和实际落地的不是一回事，这里更正**：
当初记的是"去掉 block rerun，它和 run from here 是同一件事"。实际落地的是
**整个 Re-run 功能被撤下**（ADR-038 Addendum 1）：`POST /api/runs/{run_id}/rerun` 路由删除、
`r` 快捷键删除、rerun 对话框改成 restore 的确认框、前端 `rerunRun` / `validateRerun` 全部移除。

而 **"Run from here" 完全不受影响**，ADR 明确写了"§3.6a 不受影响，原样保留"。
两者只是名字撞了，`engine/scheduler/_rerun.py` 里装的是 run from here 的 DAG 遍历，
和被撤下的 Re-run 无关。这一点写卡片文案时不能弄混。

**所以"回到过去"现在是两步，这一页要讲清楚**：
**Restore 把当时的状态放回来，然后你自己按 Run。** ADR 的理由值得抄进卡片——
两步是故意的：让用户在任何东西执行之前先看见被恢复的状态，
而且复用他本来就在用的 Run 按钮，不是第二个语义不同的执行入口。

**tidy 和 focus 的关键：都不动科学内容**
- **focus mode** 是纯前端视图状态，把选中节点邻域外的变暗/隐藏，**完全不落盘**
- **tidy** 用 elkjs 算确定性左到右布局，**只写 `node.layout` 元数据**，不碰块和连线
- 这句必须说出来 —— 用户面对"自动整理"的第一反应是"会不会把我的流程弄乱"

---

### data type 卡的页面结构（owner 定）
1. 第一页：什么是 type
2. 介绍**六种 core type**：`Array` / `Series` / `DataFrame` / `Text` / `Artifact` / `CompositeData`
3. **canonical zone** + 扩展名与格式转换
4. 最后一页 tips

**可以白拿的材料**
- **每种类型配一个存储后端，这解释了"为什么正好是这六种"**（架构 §4.3.1）：
  `Array`→Zarr（分块压缩，大数值数据）；`Series`/`DataFrame`→Arrow/Parquet（列式）；
  `Text`→内存或文件系统；`Artifact`→文件系统（保留原文件）；
  `CompositeData`→每个槽位用自己类型的后端。
  有了这条，"六种类型"从记忆负担变成**访问模式决定的设计**。
- canonical zone 那页的核心句：**扩展名不是数据契约，可重放的是 `capability_id`**（架构 §4.3.2）
- metadata fidelity 四级（`pixel_only` / `typed_meta` / `format_specific` / `lossless`）
  回答"存盘会丢什么"——对科学家是真问题
- **注意**：`CompositeData` 前面定了"暂不教"，所以它在总结关是**唯一一个用户从没用过的类型**，
  说明深度会和其他五种不一样。这符合总结关"告诉你还有什么"的定位，但要意识到这个不对称。

### previewer 卡的页面结构（owner 定）
1. 右边的 previewer 用来看每个 block 输出的数据，可以放大
2. previewer 是**连接到 type** 的，一个 type 可以对应一个 previewer
3. previewer **可以自定义**
4. tips：让 AI agent 帮忙写、previewer 可以交互

**补充材料**
- 第 1 页的"全屏"准确说是**放大成浮在画布上的窗口**（#1795）：Esc 关闭，
  换选中的块会自动关掉旧窗口（[DataPreview.tsx:119-140](frontend/src/components/DataPreview.tsx#L119-L140)）
- 第 2 页要补**回落规则**：一个 type 没有自己的 previewer 时，**沿类型链往上找父类的**，
  最后回落到核心。关卡 2 用户亲身撞过这个 —— Image 没 previewer 时显示成 Array 的数字表格。
  另外有 tier 优先级：**project > package > core**（[router.py](src/scistudio/previewers/router.py) 九级优先级）
- 第 4 页"可以交互"要分两层：**纯 Python previewer 只能用核心 viewer 已有的交互**
  （Array 的逐轴切片选择器、DataFrame 的分页排序）；**要自定义交互必须带前端 JS 资产**

### plot card 卡的页面结构（owner 定）
1. 用来出图
2. 可以连接到**任一个 block 的一个输出**
3. 可以用 **Python / R** 写
4. render 函数里收到的 **collection 是什么格式、怎么拿到 data**
5. tips

**补充材料**
- 第 2 页：绑定用 **`node_id` + `output_port`**（稳定身份，不是显示标签，因为标签会重名会漂移）；
  块删了重建会拿到新 node id → plot 标记 **broken** → 用 relink 对话框重新指向（架构 §10.3）
- 第 3 页：Python `def render(collection):` 返回 matplotlib `Figure` 或它写出的图片路径；
  R `render <- function(collection)` 返回 ggplot 对象或画到当前设备，顶层 `figure_size(w, h)` 设尺寸
- 第 4 页：collection 暴露 `types` / `items` / `open()` / `open_one()`，**惰性**——
  render 函数要的时候才物化成原生值（DataFrame、array…）
  - ⚠️ **这是 Collection 唯一必须露面的地方**。全局约定是"Collection 不教"，
    但 render 函数直接收到它。好在这里它以**入参**这个具体形态出现，
    讲"你收到的这个东西怎么用"即可，不必讲传输协议。
- 第 5 页 tips 候选：四种输出格式 **svg（默认）/ png / pdf / jpeg**，每个 plot 有允许清单；
  **plot 是 preview-only** —— 不进 DAG、不进调度器、不进 lineage，产物写进预览缓存、
  下次运行即覆盖。所以**科学结论不要只活在 plot 里**（呼应关卡 3 的"聚类放块里不放 plot 里"）

### history 卡的页面结构（owner 定）
1. **History tab**：可以看之前每一次 run 长什么样、用了哪些参数
2. **restore**
3. **git 是什么、怎么做版本控制**：每次 run 记录一个版本，也可以手动提交
4. **git branch 的用法**
5. tips

**补充材料**
- 第 1 页可讲的"每次 run 记了什么"（说人话版）：用的哪个工作流、当时的版本、
  每个块用了什么参数、跑了多久、成功还是失败、输入输出是哪些数据，
  **还有当时的运行环境**（Python 版本、系统、装了哪些包）。
  记环境这件事有了明确用途：**restore 之前会拿它跟现在比一比**（见第 2 页）。
  跑新的一次不会把旧记录盖掉，历史是往后接的。

- **第 2 页 restore（#2033 已落地，2026-08-07 核对，四条要讲）**
  1. **它恢复的是那次运行对应的整棵项目树**，不只是工作流——块的代码、脚本一起回来。
     这一条要说，因为用户最常见的情况恰恰是"我把块改坏了"。
  2. **恢复之后你自己按 Run。** 产品不替你跑。理由说人话：先让你看见恢复成什么样了，
     再由你决定要不要跑。
  3. **恢复之前它会先检查两件事**：你的输入文件还是不是当初那些、现在的环境跟当初一不一样。
     **只是提醒，不拦你。**
  4. **有件事 restore 做不到，而且它会告诉你**：git 只管你项目文件夹里的东西，
     SciStudio 自己的版本、你装的包、Python 环境**都不在里面**，恢复不回去。
     所以"昨天还好好的今天就挂了"有第二种可能——不是代码变了，是环境变了。
     这是全产品唯一会主动告诉你这件事的地方。
     另外，如果你选的那个版本不是某次运行留下的（是你手动提交的），
     它会说"没法检查"，**而不是说"没问题"**。这句诚实值得单独讲。
- 第 3 页已核实：**每次运行前会自动存一个版本**
  （ADR-039 §3.4 pre-run auto-commit，[_runs.py:362](src/scistudio/api/runtime/_runs.py#L362)），
  提交信息带 `auto` 前缀，SHA 写进那次运行记录。自动提交失败则进入降级模式，
  那次运行没有版本可回溯，且**明确不允许退而记别的 SHA**。
  → `auto` 前缀正好支撑"也可以手动提交"：**自动的是每次运行的留痕，手动的是你认定的里程碑**，历史里分得开。
- 第 4 页：架构 §4.6 那句 —— 一个分支代表一个数据情境下的工作流变体，合并往往不是目的
- tips 候选：① **git 存的是配方不是结果**，切回旧分支要重跑（关卡 3 撞过，这里收口）；
  ② **两个历史的分工**：git 管文件怎么变，History 管哪次跑了什么；
  ③ **methods 导出**（History 面板自带，直接生成方法学描述 —— 对写论文的人可能是整张卡最实用的）；
  ④ git 不可用时运行照常，只是那次没有版本可回溯

### my library 卡的页面结构（owner 定）
1. 这是**你个人可复用的工具箱**，每个 project 都能用
2. 包含 **types、previewers、blocks**
3. **放在 project 里的东西不能用到别的 project 去**

**注意**
- previewer 的用户层**已决定要做但尚未实现**；personal-tool-library spec 的 `scope.out`
  当前明确排除它（"Previewers keep core / package / project discovery only;
  `OwnerKind` is unchanged"）。owner 说这条我不用管，但**学习中心依赖它**：
  关卡 3 复用关卡 2 的 Image 类型显示切片图，若 previewer 只能项目级，
  关卡 3 的新项目里就没有 Image previewer，用户又会看到数字表格。
- 第 3 页是**给关卡 2→3 那次亲身经历命名**，不是告知新知识

### others 卡的内容（owner 定）
1. **有不会的都可以问 AI**
2. **package 系统** —— 告诉他们**可以安装 package 做扩展**（消费方，不是开发方；
   怎么写插件是开发者文档，不进这里）
3. **跑挂了怎么办**：一个块失败下游会被自动跳过、日志在哪看、可以从失败的地方接着跑
4. **更详细的用户文档去哪看**
5. **"Bring in my work" 的常驻入口再提一次**（工具栏，永久可用）——
   关卡 4 结尾选了 skip 的用户，这是他最后一次被告知去哪找的机会

**others 卡的隐含主题是"你不会的东西怎么办"** —— 问 AI、装扩展、看文档。它是出口，不是杂项抽屉。

**不收录**："为什么我的块在排队"——GUI 已有计时和运行标志，用户不会以为卡死。

**其余内容的卡片归属**
- CodeBlock / AppBlock / SubWorkflowBlock → `block`（本来就是它的子类）
- canonical zone / capability / metadata fidelity → `data type`
- DataRouter / PairEditor / MergeCollection / Split → `block` 的 built-in 那一节
- CompositeData → `data type` 的六种类型那页

---

## 关卡 6 · 开始你自己的项目（新增，待设计）

owner 指出"怎么把自己的数据放进项目"和"项目里各个文件夹是干什么的"属于第六关。

**这是个真空**：前五关用户从来没有自己导入过数据，全是教程预置的。学完他知道怎么搭工作流、
造类型、让 AI 干活，但不知道"我自己那批数据怎么进去"—— 而这是他关掉教程后要做的第一件事。

---

## 文档过时记录（写 spec 时要一并修）

1. 架构 §9.7 写 "🔗 Lineage"，实际用户可见名是 **History**
2. 架构把 **pause / resume** 列成执行引擎的通用能力（§4 层级图、§5 那两张表），**该 feature 已移除**。
   注意区分：ADR-051 交互块那个"引擎持有的暂停"是**真的**（架构 §6.4 讲两阶段 worker 那段），别一起删了。
3. ADR-051 spec 把交互块面板资产路径写成 package 专属，实际代码不区分块来自哪一层
4. 架构说 seaborn 可用（§10.2 render 那段、`list_plot_examples` 那行、§13 技术栈表），
   **不在 `pyproject.toml` 里**，2026-08-07 复核仍然如此
5. **新增**：架构 §9.7 那张底部面板表（第 1791 行）写 **"🔗 Lineage"**，且说它
   "owns methods-export and **rerun** dialogs"。两处都过时了——用户可见名是 History，
   rerun 对话框已随 #2033 撤下

（第 1 条复核：`TabBar.tsx` 里 `lineage: tabLabel(Waypoints, "History")`，注释写着
"display label only is History，BottomTab key 和所有代码仍叫 lineage，owner 要求的 UI 改名"。）

---

## 教程内容依赖的在途变更 —— 2026-08-08 对着最新 main 复核

**两条都已落地（#2033，ADR-038 Addendum 1），但实际形态和当初记的有出入，详见各自小节。**

| 当初记的 | 实际落地的 | 影响 |
|---|---|---|
| History / Git 的 restore 统一成"恢复到那次运行对应的 git commit" | ✅ 统一了，而且**范围扩大到整棵树**，外加两项建议性前置检查 | 关卡 1 第 6 步、history 卡第 2 页 |
| block rerun 移除，与 run from here 合并 | ⚠️ **整个 Re-run 功能撤下**（不是"合并"），**run from here 明确不受影响** | workflow 卡 run 那页 |

**关卡 3 不受影响**：那里教的是切分支后要重跑，用的是普通的 Run，本来就不涉及 Re-run。

**其余落地情况（同次复核）**

- **work-import 已落地**：`src/scistudio/api/routes/work_import.py` 和
  `frontend/src/components/BringInMyWorkDialog.tsx` 都在。对话框做成了**一页一个问题**的分页形式，
  不可用的 provider 在下拉里置灰不隐藏。关卡 4 结尾那个弹窗要照这个实际形态写。
- **personal tool library 只落地了管道，没落地界面**：注册表统一（`src/scistudio/core/dropins.py`）、
  drop-in 类型导入缺陷修复、刷新对称性都进去了，配套 parity 测试也有
  （`tests/api/test_registry_provisioning_parity.py`、`test_registry_reload_symmetry.py`）。
  但**用户能看见的那部分一个都没有**：`map_block_origin` 仍把 `tier1` 塌成 `custom`
  （用户层/项目层没分开）、没有 `routes/types.py`、没有 `TypePalette.tsx`。
  → **关卡 2 的"看当前支持哪些 data type"和"新建自定义类型"仍然没有 GUI 入口**，依赖照旧。
- **previewer 用户层仍然没有**，关卡 3 的依赖照旧。
- **`data/processed` 仍然不在脚手架里**（复核 `_projects.py` 的 `for subdir in (...)`）。

## 已确认的基建要求（从场景里长出来的）

1. **教程素材要能携带前端资产**（构建好的 JS 模块 + 可选 CSS）。
   **只有交互块面板需要**，previewer 不需要。
2. **教程的写文件动作要能绑在步骤上**，不只是开局 bootstrap。
   关卡 1 的"agent 改坏了工作流"、关卡 4 假 AI 的每一步副作用，都是这个机制。
3. **教程作用域的用户级库**：教程项目扫一个隔离的库目录（候选
   `~/SciStudio Tutorials/.library/blocks|types/`），真实项目不扫，
   避免教程产物污染用户自己的 `~/.scistudio/blocks|types/`。
   机制现成：注册表本来就靠 `add_scan_dir` 加目录（[_projects.py:64](src/scistudio/api/runtime/_projects.py#L64)）。
   清理时要连库一起删（ADR §8 说教程项目清理尚未设计）。
   教程里要有一句："在你自己的项目里做这个动作，东西会进你的全局库。"

## 前端资产的查证结论

**previewer 可以是纯 Python，不需要任何前端资产。**
- `PreviewerSpec.frontend_manifest` 是**可选**字段
- [PreviewHost.tsx:7-14](frontend/src/components/DataPreview.parts/PreviewHost.tsx#L7-L14)：
  有 manifest → 动态 import JS；**没有 → 按 `envelope.kind` 渲染核心 fallback viewer**
- 核心 viewer 覆盖九种 kind：dataframe / array / series / text / artifact / composite /
  collection / **plot** / error
- core 自带零依赖 PNG 编码器：[_raster.py](src/scistudio/previewers/_raster.py)（stdlib struct + zlib）
- 只有要 LUT / 通道切换 / 缩放平移这类真交互查看器时才需要 JS

**交互块面板确实需要构建好的 JS 模块。**
- `module_url` 为空时按 `panel_id` 查前端内置注册表，内置只有 `DataRouterModal` / `PairEditorModal`
- ADR-051 明确排除"通用运行时渲染的声明式控件 schema"
- 资产后缀白名单 `.js .mjs .css .map .json .svg .woff .woff2`
  （[assets.py:33](src/scistudio/previewers/assets.py#L33)）——**不含 `.tsx` / `.ts`**

## 挪到后面 / 暂不教

- **DataRouter**（交互式手工分流）——和 git 分支抢位置
- **CompositeData**（core 唯一多槽位类型）
- **My Library 的完整用法**——关卡 2 结尾只做桥梁式的一嘴

---

## 关卡 6 · 项目的结构（详细，owner 定）

**目的**：介绍 project 的结构。

**要回答的六个问题**
1. data 放哪里
2. 结果在哪里
3. 项目的 type / block / previewer 在哪里
4. AppBlock 和 CodeBlock 怎么交换数据
5. plot card 怎么导出图
6. 数据怎么保存

**交互形式**：教程给一份**"假装是你自己的"文件夹**，用户点下一步，
教程帮他走一遍导入和保存。既不用他真去找文件，又完整走过一次动作。

**讲法：四分法，别逐个目录念**
- **`data/raw/`** —— 你放进来的
- **`data/processed/`** —— 你要拿走的
- **`data/zarr` / `parquet` / `artifacts`** —— 系统存中间数据的地方，你不用管
- **`data/exchange/`** —— 和外部软件递文件的中转站

科学家关心的只有前两个，其余是"不用管"。

**`data/processed/` 的现状（owner 后续自行处理，文档按"它就是约定"来写）**
- `create_project` 脚手架建的是 `data/raw` / `zarr` / `parquet` / `artifacts` / `exchange`，
  **没有 `processed`**（[_projects.py:178-182](src/scistudio/api/runtime/_projects.py#L178)）
- 但 agent 技能文档把 `data/processed/` 当成保存输出的默认约定
  （`scistudio-build-workflow/SKILL.md` 里的示例全是 `path: data/processed/...`）
- 现状后果：AI 搭的工作流把结果写进 `data/processed/`，用户手工搭时 Save 块路径要自己填、
  没有默认落点 → 同一个项目里人做的和 AI 做的结果散在不同地方

**其余材料**
- **`project.yaml` 是项目的身份证** —— 有它才算 SciStudio 项目，打开没有它的目录会被拒绝
- **`data/` 和 `.scistudio/` 默认不进版本控制** —— 这解释了关卡 3 那个"切回旧分支结果没回来"
- **exchange 说人话**：你的脚本或外部软件看到的就是普通文件，
  SciStudio 负责在这个目录里把数据递出去、再把产物收回来
- **图不在你的项目里**：plot 产物写在 `.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/`
  （[tools_plot/tools.py:281](src/scistudio/ai/agent/mcp/tools_plot/tools.py#L281)），
  是本地运行时缓存、默认不进版本控制、**下次运行就被覆盖**。
  所以"导出"不是锦上添花，是**唯一能把图留下来的办法** —— 用户默认会以为图跟着项目走
- `blocks/` 存盘会热重载；`previewers/` 和 `plots/` 是首次用到才创建

---

# 基建形态的决定

**结论：方案 C —— 声明式 manifest 为主，代码逃生口按来源分级。**

（曾讨论过四种：A 纯声明式 / B Python 类 + entry point / C 混合 / D 项目模板。
六关设计完之后证据比讨论时清楚。）

## 为什么是 C

1. **关卡 5 和 6 几乎不需要判定，关卡 4 主要是回放。** 这三关本质是**内容**，
   用纯 Python 类写会退化成大量样板。
2. **六关暴露出 entry 不是一种形状**：工作流关卡（1/2/3）、纯阅读关卡（5）、
   脚本回放关卡（4）、半动手关卡（6）。manifest 里声明一个 `kind` 很自然，
   用类继承体系表达就重了。
3. **完成条件绝大多数后端可判**：文件存在、注册表里有某类型/某块、git 分支状态、
   运行成功、工作流 YAML 的节点与边、端口有输出、plot 存在。纯前端事件只有少数几个
   （面板打开、预览放大）。词汇表够用。
4. **列目录不能执行代码。** 学习中心要同时列出 core 教程、package 教程、项目级教程的
   标题与封面；若教程是 Python 类，列目录就得 import 每一个 —— 一个坏教程能让整个
   学习中心列不出来。napari 从第一代插件系统迁到 npe2 manifest 就是为了这个；
   VS Code 把 walkthrough 放在 `package.json` 而不是激活扩展后注册，同一理由。
5. **package 作者和 agent 写 yaml 比写类可靠**：能用 schema 校验，存之前就知道对不对。

## 具体形态

**一个教程 = 一个目录**

```
<tutorial-id>/
├── tutorial.yaml          # manifest：元数据 + 步骤
├── cover.png
└── assets/
    ├── data/              # 数据素材
    ├── code/              # 预先写好的 block / type / previewer / plot 源码
    ├── panels/            # 交互块面板（构建好的 JS，仅交互块需要）
    ├── replay/            # 假 AI 的预录脚本（关卡 4）
    └── pages/             # 阅读型内容（关卡 5 的八张卡）
```

**manifest 声明**
- 身份与展示：`id` / `title` / `summary` / `cover` / `order`
- `kind`：`workflow`（1/2/3/6）| `reading`（5）| `replay`（4）
- `requires`：需要哪个 package、需要不需要 agent、最低 SciStudio 版本
- `bootstrap`：建项目、拷素材
- `steps`：步骤列表

**步骤的动作类型（不是判定，是"教程做什么"）**
- `show` —— 显示文案
- `write` —— 把素材写进项目。**可以绑在任意步骤上**，不只是开局
  （关卡 1 的"agent 改坏了工作流"、关卡 4 假 AI 每段回复后的副作用）
- `play` —— 回放预录脚本（关卡 4 的假 AI 终端）
- `page` —— 翻页内容（关卡 5）

**完成条件用固定词汇表**，后端求值为主，少数前端事件。候选词汇（从六关反推）：
`file_exists` / `type_registered` / `block_registered` / `node_exists` / `edge_exists` /
`port_has_output` / `plot_exists` / `run_succeeded` / `git_branch_exists` /
`git_current_branch` / `library_contains` / `config_equals` / `panel_opened`

**逃生口按来源分级**

| 来源 | 元数据/步骤 | bootstrap | 判定 |
|---|---|---|---|
| core | manifest | 词汇表 + 可写 Python | 词汇表 + `checker:` 逃生口 |
| package | manifest | 词汇表 + 可写 Python | 词汇表 + `checker:` 逃生口 |
| 用户 `~/.scistudio/tutorials/` | manifest | **仅词汇表** | **仅词汇表** |
| 项目 `{project}/tutorials/` | manifest | **仅词汇表** | **仅词汇表** |

agent 写的项目级教程**结构上就不可能带任意可执行代码**；package 作者（有签名、
有分发、过 ADR-049 校验器）保留完整能力。这样既有项目级/用户级入口，
又不用为"agent 生成的代码在后台被执行"单独设计防线。

注意这与 drop-in block 的现状是不同取舍：`{project}/blocks/*.py` 现在就是被导入执行的
（沙箱由 #1531 挂账）。教程这边建议不要重复那个欠债 —— 教程代码的执行时机比 block
更早更频繁（列目录就会碰到）。

**分发与发现**
- core 教程：`src/scistudio/tutorials/<id>/`
- package 教程：包内目录 + **第五个 entry point 组 `scistudio.tutorials`**
  （现有四组见 [inventory.py:22-27](src/scistudio/packages/validation/inventory.py)：
  `scistudio.blocks` / `scistudio.types` / `scistudio.previewers` / `scistudio.runners`）。
  ADR-049 的 package 校验器要认这个新面。
- 用户 / 项目教程：`~/.scistudio/tutorials/`、`{project}/tutorials/`

**进度**（owner 已定）
- **按来源分组**，core 也算一组，各组各自 "N of M"，不给跨组总数
- 组内分母随 package 升级变大即可，不做冻结/补偿 —— 读作"有新东西可学"
- key = `(package, tutorial_id)`，允许不同包同名教程
- **存后端** `~/.scistudio/`（不是 localStorage —— 那是渲染进程的浏览器存储，
  Python 端读不到、清缓存即丢、web 与桌面两份）
- 卸载 package 时删除该组进度，重装不恢复（**只有后端存才做得到**）
- **解锁不用百分比阈值**，改为"跑完某个指定教程触发" —— 具体是关卡 4 之后弹 import
- **只有 core 组驱动解锁**；package 组进度纯展示、不驱动任何产品行为（这句要写进 spec，
  不写清楚实现的人会去接）

---

# 开放问题（明天继续）

## 1. package 教程我们管不了它怎么写 —— 这是对上面基建决定的主要挑战

owner 指出：我们只提供**入口**，package 想怎么写自己的教程，我们不好规定。

**问题在哪**
- 判定层已经有逃生口（`checker:`），package 撞到词汇表天花板可以自己写函数
- 但**步骤动作类型**（`show` / `write` / `play` / `page`）**没有逃生口**。
  某个包想要一种我们没设计的步骤形态时，无路可走
- core 教程撞天花板我们可以随手加词汇；package 作者不能改核心词汇表

**三条路**
- **(a) 给 package 一个步骤级逃生口**：manifest 里声明自定义 step 类型，指向包提供的处理器。
  口子开在步骤层，形态仍是 manifest。
- **(b) 接受天花板**：package 教程只能用我们给的动作，把不满足的需求收集起来演进词汇表。
  简单，但会挡住早期的包作者。
- **(c) 把分级从"判定层"扩到"教程形态层"**（我倾向这条）：
  **manifest 永远必需**（为了列目录零执行、拿到 id / 标题 / 封面 / 前置），
  但 manifest 里可以声明"我的步骤由代码驱动"，指向包内的一个教程类。
  这个能力**只对 core 和 package 开放**，用户级和项目级仍然只能用 manifest。

  → 好处：package 想怎么写就怎么写（B 形态的全部自由），
    同时保住"列目录不执行代码"这条硬约束（C 形态的核心收益），
    也保住"agent 写的项目级教程不可能带可执行代码"这条安全性。
    分级规则从"判定的逃生口"自然延伸成"整个教程形态的逃生口"，是同一条原则。

## 2. `data/processed/` 要不要进 `create_project` 脚手架

owner 后续自行处理。现状见关卡 6 那节：脚手架没有它，agent 技能文档把它当默认约定，
导致人做的和 AI 做的结果散在不同地方。

## 3. previewer 用户层与 personal-tool-library spec 的冲突

owner 说"你不用管"，但学习中心依赖它：关卡 3 复用关卡 2 的 Image 类型显示切片图，
若 previewer 只能项目级，关卡 3 的新项目里就没有 Image previewer，用户又会看到数字表格。
需要决定：修订那个已定稿的 spec，还是开 follow-up issue 单独做。排期要在关卡 3 之前。

## 4. 总结关顶部那句"一句话讲 SciStudio 的核心概念"怎么说

owner：后面慢慢改。

## 5. ADR-053 大修订要改的条文

- §2.2 "完成只授予跑完，Reading is not progress" → 总结关是纯阅读的
  （理由可用：总结关是**整理**不是学习 —— 六张卡都是用户亲手做过的东西）
- §4.2 "初始阈值 40% of the catalogue，是配置不是常量" → 改成事件式解锁（跑完关卡 4）
- §8 "Gating a capability behind progress is a bet" 那段跟着改
- §2.1 "generalise 现有单教程实现" → 现行决定是作废重做，只保留场景过程
- import spec 不用动：它第 33 行已把 progress / thresholds / 解锁时机整体推给学习中心 spec
