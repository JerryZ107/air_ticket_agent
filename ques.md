# 批量后端测试问题集

依据 **MCP 工具**（`mcp_server/server.py`）与 **RAG 手册分块**（`docs/manual/*.md` → `rag/indexer.py` 按标题切分）编写。  
由 `scripts/run_ques_batch.py` 读取下方 JSON，对 `POST /api/auth/login` + `POST /api/chat` 逐条执行。

## 类别说明

| 类别 | 覆盖 |
|------|------|
| `rag-*` | 应触发 `faq_lookup_tool` / RAG，答案来自手册 |
| `tool-list` | `list_bookings` |
| `tool-flight` | `flight_status_tool` |
| `tool-search` | `search_flights` / `get_matching_flights` |
| `tool-seat` | `update_seat`（写操作，默认批量跳过） |
| `tool-rebook` | `rebook_flight`（写操作，默认跳过） |
| `tool-cancel` | `cancel_flight`（写操作，默认跳过） |
| `tool-comp` | `issue_compensation`（演示工具，非 MCP） |
| `auth` | 越权 / admin 全量列表 |
| `admin-on-behalf` | 管理员 `list_customer_bookings`、代客写操作 + `on_behalf_of_username` |
| `triage` | 分诊、查本人订单 |

## 默认账号

密码均为 `demo123`。写操作题目标记 `destructive: true`，批量跑加 `--include-destructive` 才执行。

---

<!-- QUESTIONS_JSON -->
```json
[
  {"id":"R01","user":"zhangsan","category":"rag-baggage","source":"01-baggage","text":"经济舱免费托运行李是多少公斤？有几件？"},
  {"id":"R02","user":"zhangsan","category":"rag-baggage","source":"01-baggage","text":"登机行李单件重量上限是多少公斤？"},
  {"id":"R03","user":"zhangsan","category":"rag-baggage","source":"01-baggage","text":"托运行李超重一件怎么收费？美元是多少？"},
  {"id":"R04","user":"zhangsan","category":"rag-rebook","source":"02-rebooking","text":"改签后确认号会变吗？正确流程是什么？"},
  {"id":"R05","user":"zhangsan","category":"rag-rebook","source":"02-rebooking","text":"自愿改签经济舱起飞前2小时以前的改期费是多少？"},
  {"id":"R06","user":"zhangsan","category":"rag-rebook","source":"02-rebooking","text":"能不能先退票再重新订票来代替改签？"},
  {"id":"R07","user":"zhangsan","category":"rag-cancel","source":"03-cancellation","text":"退票退款大概多久原路退回？工作日范围？"},
  {"id":"R08","user":"zhangsan","category":"rag-cancel","source":"03-cancellation","text":"经济舱起飞前7天以上自愿退票手续费比例是多少？"},
  {"id":"R09","user":"zhangsan","category":"rag-delay","source":"04-delay-compensation","text":"延误满3小时餐券补偿大概多少？满4小时过夜酒店券标准？"},
  {"id":"R10","user":"zhangsan","category":"rag-delay","source":"04-delay-compensation","text":"延误补偿需要保留哪些单据？报销时限几天？"},
  {"id":"R11","user":"zhangsan","category":"rag-seat","source":"05-seat-selection","text":"演示航线A320neo经济舱大概多少座？安全出口在第几排？"},
  {"id":"R12","user":"zhangsan","category":"rag-seat","source":"05-seat-selection","text":"安全出口排座椅有什么年龄和语言要求？"},
  {"id":"R13","user":"zhangsan","category":"rag-wifi","source":"06-wifi-amenities","text":"机上Wi-Fi的SSID名称是什么？基础Wi-Fi是否免费？"},
  {"id":"R14","user":"zhangsan","category":"rag-checkin","source":"07-check-in","text":"国内航班网上值机最早提前多久开放？柜台截止多久？"},
  {"id":"R15","user":"zhangsan","category":"rag-checkin","source":"07-check-in","text":"登机口一般提前多久关闭？"},
  {"id":"R16","user":"zhangsan","category":"rag-um","source":"08-unaccompanied-minor","text":"无成人陪伴儿童UM服务要提前多久申请？国内服务费多少？"},
  {"id":"R17","user":"zhangsan","category":"rag-faq","source":"09-faq-general","text":"境内客服电话是多少？投诉邮箱？"},
  {"id":"R18","user":"zhangsan","category":"rag-faq","source":"09-faq-general","text":"改签成功后确认号会不会变？全新订票呢？"},
  {"id":"R19","user":"zhangsan","category":"rag-intl","source":"10-international-travel","text":"携带超过多少人民币等值现金需要海关申报？"},
  {"id":"R20","user":"zhangsan","category":"rag-dangerous","source":"11-dangerous-goods","text":"随身携带充电宝容量超过多少Wh需要航空公司批准？"},
  {"id":"R21","user":"zhangsan","category":"rag-dangerous","source":"11-dangerous-goods","text":"液态物品随身携带每容器最大多少毫升？"},

  {"id":"T01","user":"zhangsan","category":"triage","text":"展示下我最近的订单"},
  {"id":"T02","user":"zhangsan","category":"triage","text":"我有没有订票？帮我列一下订单"},
  {"id":"T03","user":"admin","category":"triage","text":"最近有什么订单？列出最近的"},
  {"id":"T04","user":"lisi","category":"auth","text":"帮我查确认号ABC123的订单详情"},
  {"id":"T05","user":"lisi","category":"tool-list","text":"展示我的订单列表"},

  {"id":"M01","user":"zhangsan","category":"tool-flight","text":"查询航班PA441当前状态和延误情况"},
  {"id":"M02","user":"zhangsan","category":"tool-flight","text":"NY900这个航班现在什么状态？还有多少余票？"},
  {"id":"M03","user":"zhangsan","category":"tool-search","text":"帮我搜从纽约JFK到奥斯汀AUS有哪些可选航班"},
  {"id":"M04","user":"zhangsan","category":"tool-search","text":"从Paris到Austin有没有联程或直飞航班？"},

  {"id":"M05","user":"zhangsan","category":"tool-comp","text":"我航班延误错过后续了，能申请延误补偿吗？政策怎么说？"},
  {"id":"M06","user":"zhangsan","category":"rag-delay","text":"行李额度是多少？如果延误3小时以上有什么餐券？"},

  {"id":"A01","user":"admin","category":"admin-on-behalf","text":"查询旅客zhangsan名下有哪些订单？"},
  {"id":"A02","user":"admin","category":"admin-on-behalf","text":"列出系统里最近订单，并说明每条订单属于哪位旅客用户名"},
  {"id":"A03","user":"lisi","category":"auth","text":"我要代旅客zhangsan查询订单列表"},
  {"id":"A04","user":"admin","category":"admin-on-behalf","text":"帮我查旅客lisi的订单确认号是多少？"},
  {"id":"M07","user":"zhangsan","category":"tool-flight","text":"只问一句：航班PA441现在什么状态？不要帮我改签"},

  {"id":"W01","user":"zhangsan","category":"tool-seat","destructive":true,"text":"把我的订单ABC123座位改成14B"},
  {"id":"W02","user":"zhangsan","category":"tool-rebook","destructive":true,"text":"帮我把确认号ABC123改签到航班NY802，座位尽量靠窗"},
  {"id":"W03","user":"lisi","category":"tool-cancel","destructive":true,"text":"请取消我的订单XYZ789"},
  {"id":"W04","user":"admin","category":"admin-on-behalf","destructive":true,"text":"代旅客zhangsan将确认号ABC123的座位更新为14C（on_behalf_of_username=zhangsan）"},
  {"id":"W05","user":"admin","category":"admin-on-behalf","destructive":true,"text":"代旅客lisi取消确认号XYZ789（on_behalf_of_username=lisi）"}
]
```
<!-- /QUESTIONS_JSON -->
