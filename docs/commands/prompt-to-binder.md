# Command: prompt-to-binder（把 prompt 替换为确定性预处理）

> 触发方式：当需要对一个 Agent 项目做「数据边界/身份绑定/行为约束」重构时，使用本命令。
> 出处：openai-cs-agents-demo 的 Binder 改造（airline/tools + pipeline/binder.py），
> 核心提交 `863e889`。适用语言：Python（OpenAI Agents SDK 或类似框架）。

## 目标

把「靠 prompt 约束模型行为」的代码，重构为「在 Agent 运行前确定性预处理」：
模型拿到的 context 里本来就只有当前用户的数据；身份、权限、可规则化逻辑
不再依赖模型的自觉。

## 核心原则

1. **能从 session / DB 确定性拿到的数据 → 注入 context，不让模型"记得去查"。**
2. **写操作身份与权限 → 工具层 / repository 硬绑定，不靠提示词。**
3. **可规则化的路由 → 直连路径，绕过 Agent（省 token、零旁白、结果稳定）。**
4. **prompt 只保留真正需要模型判断的事**：意图、多步编排、语气、澄清、拒答。

## 扫描：找出可替换的 prompt

在 Agent instructions / system prompt 中搜索这些信号：

| 信号词 | 含义 | 处理 |
|--------|------|------|
| 「先调用 X」「必须先 list_bookings」「勿索要」 | 让模型记得查数据 | 改为入口注入数据 |
| 「必须在工具中传入身份参数」 | 让模型自觉传参 | 改为入口提取 + 工具默认绑定 |
| 「根据城市/关键词加载场景」 | 可规则化选择 | 改为入口关键词预选 |
| 「只根据工具返回回答」 | 正确性约束 | 保留措辞，但数据源改为"注入 + 工具" |
| 「当前会话已绑定用户 X」 | 用提示词假装鉴权 | 删除，改为数据层绑定 |
| 「禁止编造」「手册未收录须拒答」 | 模型判断类 | 保留 |

## 落地步骤

1. **context 加注入字段**：如 `bookings`、`on_behalf_of_username`；
   所有内部字段加入 `public_context` 隐藏集，防止泄漏到前端。
2. **新增 binder 模块**（`pipeline/binder.py`），三个纯函数 + 一个入口：
   - `extract_on_behalf_of_username(text)`：正则提取代客目标；
   - `select_demo_scenario(text)`：关键词选场景；
   - `hydrate_user_data(state)`：登录用户注入全部订单快照 + 主订单；
   - `preprocess_message(state, text)`：身份提取 → 数据注入（未登录则注入演示数据）。
3. **server 入口无条件调用**：在路由/Agent 运行前执行 `preprocess_message`，
   删除原来的"仅非 FAQ 才 hydrate"条件。
4. **逐个 Agent 替换 prompt**：
   - `_login_booking_hint`：注入「系统已注入 N 笔订单（确认号/航班/座位）」，
     删掉「先调用 list_bookings」；
   - `_admin_on_behalf_hint`：有目标时写「系统已识别代客目标 X，写操作已自动绑定」，
     无目标时写「请直接说明旅客用户名，系统会自动绑定」；
   - 删除城市关键词填充指令、删除 MCP 会话绑定提示。
5. **工具层默认绑定**：`normalize_on_behalf_of_username` 在参数为空时
   读取 binder 提取的目标（仅 admin），非 admin 依旧拒绝。
6. **grounding 同步改写**：数据类规则改为「订单与行程以系统注入为准；
   未注入信息才必须先调用工具」。
7. **补测试**：
   - 纯逻辑：提取函数、场景选择、未登录注入（不依赖 DB）；
   - 集成：登录用户注入全部订单、admin 只注入代客目标旅客的数据；
   - 回归：原有路由 / 权限 / Saga 用例全部保持通过。
8. **回归验证**：`pytest` 全绿；批量 E2E（37 题）重跑；
   重点核对本人订单、admin 代客、航班状态三类用例。

## 判断标准：什么不该替换

- 意图分类与 Handoff 决策（开放判断，规则化会爆炸）；
- 越狱/相关性护栏（对抗性输入，LLM 判断 + fail-open）；
- 多步编排（查完航班再转改签）与澄清追问；
- 回复语气与拒答话术。

## 验收

- [ ] `git grep "先调用\|必须先\|勿索要"` 在 prompt 中不再出现数据获取类指令
- [ ] 入口对每个请求无条件执行 binder
- [ ] 写操作身份只来自 session / binder / repository，不来自 prompt
- [ ] 内部字段（bookings、user_id、on_behalf）不出现在 public_context
- [ ] pytest 全绿 + E2E 无回归

## 简历话术（面试时一句话）

> 数据边界靠注入实现，不靠模型自觉：会话身份在入口确定性绑定，
> 用户数据在 Agent 运行前注入 context，写操作在 repository 层硬校验并审计。
> Prompt 只负责模型真正需要判断的事。
