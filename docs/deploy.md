# v0.2.0 内网部署与恢复

## 交付物和主机准备

使用 Linux x86-64、Docker Engine 和 Compose v2。安装 `age`，并准备可信的镜像构建或拉取来源。为 HTTPS 主机名配置内网 DNS，由内部 CA 签发证书，并在使用者浏览器及冒烟机上信任该 CA。准备独立目录保存应用源码、模型发布包和密钥文件。部署记录应保存应用 Git 提交、API 与代理镜像 ID 或仓库 digest、PostgreSQL 镜像 digest、Alembic revision、模型版本及 manifest SHA-256、容差版本。

在 Windows Demo 的 `backend` 下，以当前可信模型和相同锁文件生成发布目录。输出目录的父目录需已存在。

```powershell
$env:ALGORITHM_ROOT = "D:/Welding/weldingproject_v2"
python -m app.model_release --version welding-v1 --output D:/releases/welding-v1
```

通过受控渠道传输整个目录，并通过可信发布记录传递命令输出的 manifest SHA-256。模型源代码、序列化模型、数据、容差配置、报告、依赖锁和黄金工况都受清单校验。容器启动先校验，再加载 Python 模块及 joblib。运行用户只读访问该目录。被登记过的模型 run ID 必须保持原指纹。Python 依赖版本应与发布包匹配。

复制 `deploy/env.example` 为仓库根目录的 `.env`，填写主机名、模型目录与指纹。完成读权限设置后，受控目录应具有以下文件：

| 文件 | 内容 |
| --- | --- |
| `secrets/pg_admin_password` | PostgreSQL 管理口令 |
| `secrets/pg_app_password` | `welding_app` 口令 |
| `secrets/pg_migration_password` | `welding_migrate` 口令 |
| `secrets/app_url` | `postgresql+psycopg://welding_app:<口令>@postgres/welding` |
| `secrets/migration_url` | `postgresql+psycopg://welding_migrate:<口令>@postgres/welding` |
| `secrets/tls.crt`、`secrets/tls.key` | PEM 证书链及私钥 |

单行文件从运维密钥存储写入。URL 中的口令按 URL 编码，或选用高熵十六进制口令。将 `secrets/` 设为仅运维可遍历，两个 URL 文件应允许容器 GID 10001 读取（如 `root:10001`、`0440`）。PostgreSQL 三个口令文件应允许其运行用户读取，官方 Debian 镜像通常为 UID 999，可先运行 `docker run --rm --entrypoint id postgres:17-bookworm postgres` 核实。证书私钥由代理主进程读取。日常 API 使用 DML 权限，迁移用拥有 schema 的独立账号。

## 安装、旧库导入及启动

```sh
mkdir -p runtime/import
docker compose config --quiet
docker compose build api proxy
docker compose up -d --wait postgres
docker compose run --rm migrate
```

需要导入旧库时，将已停止写入的 SQLite 文件放入 `runtime/import/system.db`，允许容器 UID 10001 读源文件、写快照目录。在首次启动 API 前运行：

```sh
docker compose run --rm migrate python -m app.import_history --source /import/system.db --backup /import/pre-import.db
```

旧导出文件按已有任务 UUID 目录复制到导出卷。如下命令通过标准输入复制，容器使用与应用一致的 UID：

```sh
tar -C /srv/legacy/exports -cf legacy-exports.tar .
docker compose run --rm --no-deps -T api tar -C /opt/welding/runtime/exports -xf - < legacy-exports.tar
```

```sh
docker compose run --rm api python -m app.auth
docker compose up -d --wait api proxy
docker compose ps
docker compose logs --tail=100 api proxy postgres
```

访问 `https://<内网域名>`。登录后抽查导入前记录的任务 ID、模型和容差版本、复核状态及 CSV。以下冒烟命令需要安装后端锁文件中的 httpx，交互输入管理员密码：

```sh
python deploy/smoke.py https://welding.example.internal /srv/welding/models/welding-v1/golden.json --ca /srv/ca/internal-ca.crt
```

保存命令返回的预测和推荐 ID。冒烟校验两种真实模型的预测值和区间、约束判定、推荐和候选 CSV，并验证历史可读、退出后拒绝访问。可使用系统 CA 时省略 `--ca`。

## 推荐任务

单 API 进程、单执行器，`TASK_CAPACITY` 限制执行中和排队任务的总数，缺省 8。任务开始执行后由独立子进程承担计算，`TASK_TIMEOUT_SECONDS` 缺省 180 秒。超时终止子进程。服务重启将原先排队或运行的任务标记为中断。超时、失败和中断可在前端显式重试，生成包含原任务 ID 的新记录。历史结果与原导出按原任务 ID 保留。若原模型或容差版本已变更，请用新版本创建新任务。

## 加密备份

在应用目录下以运维账号调度 `deploy/backup.sh`，例如每天维护窗口一次。并发升级或备份应由运维维护窗口协调。系统定时任务可将同一命令的退出状态和日志接入现有监控。每次使用唯一文件名。示例：

```sh
sh deploy/backup.sh /srv/welding/models/welding-v1 age1... "/srv/backup/welding-$(date -u +%Y%m%dT%H%M%SZ).tar.age"
```

脚本停用代理及 API 以获取数据库和导出文件的共同恢复点，原先运行的 API 在脚本退出时恢复。备份含 PostgreSQL 自定义格式快照、导出卷、模型包及当前镜像引用。使用公共接收者加密，私钥由运维异机保存。将密文同步到独立主机并核对大小、SHA-256、日期及任务退出状态；保护备份时创建的临时工作目录。运维另行保管证书私钥、数据库凭据和镜像构建或拉取凭据。 [PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)

## 从备份恢复和升级回退

在干净 Linux 主机或隔离 Compose 项目中演练。使用备份对应的应用 Git 提交、PostgreSQL 主版本以及新的凭据文件。初始化会创建同名角色，因此原备份中的对象所有权和授予权限仍能解析。为演练主机使用独立 DNS 和 TLS 证书。以下流程应在空数据库、空导出卷完成。

```sh
umask 077
mkdir restore
age -d -i /secure/backup-key.txt /srv/backup/welding.tar.age > restore/payload.tar
tar -C restore -xf restore/payload.tar
mkdir -p /srv/welding/models/restored
tar -C /srv/welding/models/restored -xf restore/model.tar
sha256sum /srv/welding/models/restored/manifest.json
```

核对恢复出来的指纹与原记录，更新 `.env`。接着构建或加载备份对应的镜像，启动 PostgreSQL，在 API 启动或运行一次性迁移之前恢复原 schema：

```sh
docker compose up -d --wait postgres
docker compose exec -T postgres pg_restore --exit-on-error --single-transaction -U postgres -d welding < restore/welding.dump
docker compose run --rm --no-deps -T api tar -C /opt/welding/runtime/exports -xf - < restore/exports.tar
docker compose run --rm api python -m app.auth
docker compose up -d --wait api proxy
```

通过 CLI 重置管理员同时撤销备份中恢复的全部会话。启动后校验旧预测、任务、模型、容差、复核和 CSV；再跑一次真实模型冒烟。保存部署机器、镜像 ID、revision、模型 SHA-256、导入计数、恢复计数与测试输出。校验备份恢复演练后安全清理运维主机的明文临时文件。

升级顺序为备份、停止代理和 API、一次性迁移、启动、冒烟。应用回退前核对旧镜像支持现有 schema 与模型包。如果 schema 不兼容，在隔离环境把升级前的备份恢复到上述空库，完成核验后切换流量，并保留故障实例与升级后的数据以便核查。
