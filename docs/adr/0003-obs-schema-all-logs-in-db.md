# 观测数据全部入库 obs schema，禁止仅写文件或 stdout

所有运行期数据——审计、Trace、LLM 完整请求/响应、思考模式全文、Tool 入参出参、RAG 中间结果、对话轮次、护栏与熔断事件——写入 PostgreSQL `obs` schema 的结构化表。stdout/文件仅可作开发镜像，**持久化唯一事实来源是数据库**。普通 User 的每次写操作同样记入 `obs.audit_log`；Admin 代客时额外填写 `on_behalf_of_user_id`。
