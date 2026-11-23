# 架构与数据库

```mermaid
flowchart LR
 UI[Vue3 + Pinia + Element Plus + ECharts] --> API[FastAPI /api/v1]
 API --> H[服务端会话与操作审计]
 H --> DB
 API --> S[业务服务 / 单执行器与有超时的计算子进程]
 S --> A[可信模型适配层]
 A --> F[只读发布包 / 模型 / CSV / 容差]
 S --> DB[(SQLAlchemy / SQLite 或 PostgreSQL)]
 S --> E[受控CSV导出]
```

```mermaid
erDiagram
 MODEL_VERSIONS ||--o{ RECORDS : model_id
 TOLERANCES ||--o{ RECORDS : tolerance_id
 RECORDS ||--o{ CANDIDATES : task_id
 BATCHES { string id PK json metadata_json }
 MODEL_VERSIONS { string id PK json metadata_json }
 TOLERANCES { string id PK json config }
 RECORDS { string id PK string kind string status json request json result string created }
 CANDIDATES { string id PK json data string review_status string notes }
```

采用紧凑模块而非大量空目录：core配置、ml模型适配、schemas请求校验、services业务与任务、db ORM、main接口。业务查询和会话状态直接使用 SQLAlchemy。记录不可静默重算；容差ID包含配置摘要。候选记录包含完整结果和复核状态。CSV、二进制与全部仿真表格在文件系统，数据库仅存元信息与业务记录。

生产部署使用单个 Uvicorn worker。推荐串行执行，队列上限覆盖运行中和等待的任务。单次计算使用有超时限制的子进程。重启把 queued/running 标记为 interrupted，显式重试生成带原任务 ID 的新记录。任务候选上限 20,000，入口预估先拒绝过密网格。

模型自定义类通过 importlib 按可信源目录登记 welding、validate、enhanced、decision 模块，模型按版本缓存。业务路由不修改sys.path。环境与模型依赖需匹配。仅固定版本可信文件可加载。

数据库使用显式 Alembic 迁移。001 冻结原业务表，002 增加管理员、会话与审计。开发默认 SQLite，生产使用 PostgreSQL 和独立的应用及迁移账号。既有历史可按部署文档导入。
