# 航班订票助理

面向已登录旅客与管理员的智能客服上下文：查询航班、办理订退改、解答手册政策。所有业务数据以 PostgreSQL 为唯一事实来源。

## Language

### 身份与访问

**User（用户）**：
已通过登录认证的旅客账号；每个 User 拥有自己的订单与个人信息。
_Avoid_: 客户、乘客（当指账号时）、account

**Admin（管理员）**：
拥有 elevated 权限的 User，可查看并**代客办理**任意 User 的订单；每次代操作写入 Audit Log，并关联 Trace。
_Avoid_: 超级用户、root

**Audit Log（审计日志）**：
记录**每一次**业务写操作（订票、退票、改签、登录等），不论 Actor 是 User 还是 Admin；Admin 代客时额外标明 `on_behalf_of` 目标 User。
_Avoid_: 日志、history（当指聊天历史时）

**Observability Store（观测库）**：
PostgreSQL `obs` schema，存放 Trace、LLM 全文、思考模式内容、对话、RAG 中间结果与审计；运行期数据的唯一持久化来源。
_Avoid_: 日志文件、Langfuse（当指本项目 A 阶段存储时）

**Session（会话）**：
一次登录后的连续交互周期；绑定一个 User（或 Admin），Agent 在该 Session 内只能访问该身份有权看到的数据。
_Avoid_: 线程、对话（当指鉴权边界时）

**Login（登录）**：
使用 Agent 的前置条件；未登录不得发起订票类对话。
_Avoid_: 选用户（已升级为真实登录，非匿名 Mock）

### 订单与航班

**Booking（订单）**：
User 对某一航班的预订记录，含确认号、座位、状态；归属唯一 User。
_Avoid_: 订票、预约（作名词时）

**Confirmation Number（确认号）**：
订单对客展示的字母数字标识；User 凭此引用自己的 Booking。
_Avoid_: 订单号（若与内部 UUID 混淆时）

**Flight（航班）**：
一次可售卖的运力班次，含起降、余票、票价；不归属 User，被多个 Booking 引用。
_Avoid_: 行程、航段（多段联程时再区分）

**Rebooking（改签）**：
在同一 Booking 上变更所乘 Flight；**确认号不变**；通过 Saga 原地更新订单，成功前不取消原票。
_Avoid_: 换票、改期、退票重订

**Cancellation（退票）**：
终止 Booking，释放座位；原 Booking 状态变为已取消，不再有效。仅当用户明确不要该行程时触发，**不**作为改签的前置步骤。
_Avoid_: 取消航班（Flight 运营层面）

**New Booking（新订）**：
无既有 Booking 时创建全新订单，生成新确认号。与 Rebooking、Cancellation 互斥路径。
_Avoid_: 订票（作名词时用 Booking）

### Agent 边界

**User-scoped Agent（用户专用 Agent）**：
同一套多 Agent 编排（分诊 + 专员），但在 Session 内按 User 身份过滤可见数据；非 Admin 只能看到自己的 Booking 与个人信息。
_Avoid_: 私人 Agent、专属模型

**Handoff（转接）**：
分诊 Agent 将对话交给专员 Agent；不改变 Session 所属 User。
_Avoid_: 路由（当指模型层意图分类时）

### 知识与政策

**Policy Manual（订票手册）**：
面向旅客的静态政策文档集合（行李、改签、退票、补偿等），经 RAG 索引后供 FAQ 类问题检索；非实时航班或订单数据。
**存放路径**：仓库根目录下 `docs/manual/*.md`（由 `python-backend/rag/indexer.py` 索引；`docs/adr/` 等不参与 RAG）。
_Avoid_: FAQ、知识库（当与向量库混淆时）

## Flagged ambiguities

| 术语 | 歧义 | 当前决议 |
|------|------|----------|
| 改签 vs 退票重订 | 用户说「换一个航班」可能是 Rebooking 或 Cancel+新 Booking | **统一 Rebooking（R1）**；确认号不变；禁止「先退后订」作为改签实现 |
| Admin 操作范围 | Admin 是否可代客下单、还是仅查看/排障 | **B：可查 + 代客办理 + audit**；工具 `on_behalf_of_username`（仅 admin）+ `obs.audit_log.on_behalf_of_user_id` |
| 他人确认号查询 | 回复「不存在」还是「无权」 | **X：统一「无法处理该确认号」** |

## Example dialogue

> **旅客**：我不坐 CA1234 了，改 CA5678。  
> **领域专家**：这是 **Rebooking**——**确认号不变**，Saga 在新座位锁定成功后原地更新该 **Booking**；失败则原票仍在。  
>  
> **旅客**：帮我取消。  
> **领域专家**：指 **Cancellation**——该 **Booking** 终止，不是取消整班 **Flight**。
