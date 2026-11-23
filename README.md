# 薄板焊接预测与工艺决策系统

v0.2 内网部署版默认使用增强模型，也支持旧模型对照。Linux 交付使用只读模型发布包，Windows Demo 可继续读取原算法目录。

详细步骤、逐页操作和排错见 [本地使用手册](docs/user_guide.md)。日常使用无需重复安装依赖。

[Linux 安装、升级和恢复](docs/deploy.md) · [v0.2 管理员与迁移说明](docs/v0.2.md)

## 启动

后端复用 `D:/miniconda3/envs/mywelding/python.exe`；前端 Node 22。后端完整依赖见 `backend/requirements.lock.txt`，前端用 `npm ci` 恢复锁文件依赖。

```powershell
cd D:/Welding/welding_system/backend
D:/miniconda3/envs/mywelding/python.exe -m pip install -r requirements.lock.txt
cd ../frontend
npm ci
cd ..
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

首次启动前按 [管理员初始化](docs/v0.2.md#初始化和重置管理员) 设置密码。

访问 http://127.0.0.1:5173 ，OpenAPI http://127.0.0.1:8000/docs 。停止使用 `scripts/stop.ps1`，只停止脚本登记的进程。日志 `runtime/logs`，数据库 `runtime/db/system.db`，导出 `runtime/exports/<任务UUID>`。启动前确保8000/5173空闲，禁止同一数据库多实例运行。

环境变量见 `.env.example`（示例文件不自动加载，需设置进程环境变量）。本地缺省使用 SQLite，通过 DATABASE_URL 连接 PostgreSQL。Windows Demo 的原算法目录由 ALGORITHM_ROOT 配置。

验证：后端 `python -m pytest`、`python -m ruff check app tests`；前端 `npm run build`、`npm test`、`npm run lint`。

模型登记记录来源、SHA256与加载依赖，可信本地文件加载，无上传接口。版本由原运行目录唯一标识，禁止覆盖已有目录的模型。迁移运行 `python -m alembic upgrade head`。系统不会自动替换默认模型。

详见 docs 下架构、数据、接口和验收说明。
