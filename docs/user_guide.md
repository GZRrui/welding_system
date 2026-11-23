# 本地使用手册

## 1. 这次空白页面的排查结论

2026-11-03检查发现：前端node_modules中缺少vite入口；启动日志报Cannot find module；8000端口已有后端，再次启动报10048端口占用。运行中的esbuild还锁住依赖文件，使npm ci报EPERM。页面标题出现仅说明HTML加载，不能说明Vue运行成功。

已停止确认属于本项目的旧前端进程，按package-lock恢复依赖；脚本已增加依赖检查、端口检查、就绪检查，并禁止Vite静默改用其他端口。请勿运行中安装或重建node_modules。

## 2. 每天正常使用（不需要每次安装）

在VS Code通过“文件→打开文件夹”打开 D:\Welding\welding_system。选择“终端→新建终端”，确认是PowerShell，然后执行：

```powershell
cd D:\Welding\welding_system
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

等待“服务检查通过”后打开 http://127.0.0.1:5173 ，使用管理员账户登录。首次运行 v0.2 前按[管理员初始化说明](v0.2.md#初始化和重置管理员)设置密码。首次加载图表可能需要数秒。看到左侧六个功能入口、系统概览与真实样本数，才算页面启动成功。不要通过双击index.html运行。

脚本隐藏启动窗口，可关闭启动终端，后台服务仍运行。重复执行将复用已经运行的本系统服务；若是其他服务占端口则报错，不会强制结束它。脚本不会自动打开浏览器。

停止：

```powershell
cd D:\Welding\welding_system
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

只停止脚本创建且启动时间一致的进程。手动在终端启动的服务，需要在对应终端按Ctrl+C。不要直接关闭所有Python/Node进程。

## 3. 第一次安装或恢复依赖

只有首次安装、依赖缺失或变更锁文件后需要执行。先停止本项目服务；如果手动运行过npm run dev，也在那个终端Ctrl+C，等待返回PS提示符。

```powershell
cd D:\Welding\welding_system\backend
& D:\miniconda3\envs\mywelding\python.exe -m pip install -r requirements.lock.txt
cd ..\frontend
npm ci
```

看到added ... packages且没有npm error后，再按第2节启动。npm ci会重建node_modules，不要与运行中的前端并行执行。不要随意npm update或npm audit fix，模型与依赖已有版本锁。

若解释器安装在别处，启动时指定：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Python "D:\miniconda3\envs\mywelding\python.exe"
```

## 4. 手动启动（排错时使用）

不要和一键启动方式同时使用。需要两个终端，且都保持运行。

终端A（后端）：

```powershell
cd D:\Welding\welding_system\backend
& D:\miniconda3\envs\mywelding\python.exe -m alembic upgrade head
& D:\miniconda3\envs\mywelding\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

看到Application startup complete后，在 http://127.0.0.1:8000/docs 查看接口。健康检查 http://127.0.0.1:8000/api/v1/health 应返回status为ok。

终端B（前端）：

```powershell
cd D:\Welding\welding_system\frontend
npm run dev -- --port 5173 --strictPort
```

浏览器访问终端显示的 http://127.0.0.1:5173 。退出时分别Ctrl+C。

## 5. 完成一次预测

1. 点击“工况预测”，默认增强模型。
2. 输入电流210 A、电压27.2 V、联动环境温度80℃、焊速6 mm/s、顺序1。这只是输入示例，不是预设推荐。
3. 点击“计算工况预测”。修改输入不会自动计算，必须重新点击。
4. 阅读预测值、95%边际区间、V1限值、保守判断与风险提示。界面位移mm，应变无量纲；模型接口位移m、速度m/s。
5. 记录模型运行ID及容差版本。切换旧模型后再次计算会产生新记录，历史不会覆盖。

所有结果都是两条焊缝全部焊完并冷却约90分钟后的最终幅值。顺序1为volume9→7；顺序2相反。温度联动初温、对流环境与参考温度，不能理解为独立改变其中一项。方向位移无正负方向，各最大值不应合成。

## 6. 趋势与顺序比较

“参数趋势”：选择横轴，固定其他参数，点击计算。改变横轴后需再次计算。总应变、塑性应变、位移和辅助输出分图展示，两种顺序各有预测曲线与区间带。ANSYS点只取其他连续参数完全匹配的数据，没有匹配时不显示点。悬浮查看、图例开关、图右上角导出图片。

“顺序比较”：输入相同四个连续参数后计算，查看顺序1/2、区间与绝对差异。差异小于误差范围时，不能宣称某个顺序显著更优。

## 7. 工艺参数推荐

1. 设置当前工况。默认步长为开发设定，尚未确认设备分辨率。
2. 设置四项步长与允许调整幅度。注意该区域速度步长/幅度用原始m/s：0.0005 m/s = 0.5 mm/s；当前工况焊速输入仍为mm/s。
3. 可锁定参数；锁定值必须位于从训练下界起算的步长网格上。若提示Locked value outside bounds/change/step，需调整步长或锁定值。
4. 不允许换顺序时取消对应勾选。提交后查看queued→running→completed。刷新可恢复最近任务，历史页也能重新打开。
5. 推荐依据：预测值+max(项目误差预算,校准半径)≤项目限值。表格_upper是保守上界，adjustment_cost是归一化调整成本，risk_note是风险说明。
6. 当前工况满足约束时如实提示无需调整；无解表示设定网格与范围内没有可行候选，可合理扩大调整范围或修改步长，但不要为了“有解”修改项目限值。
7. 导出recommendations为推荐表，ansys_verification_queue为新工况复核队列，all_candidates为全部候选。CSV使用原始SI单位，位移m、速度m/s。
8. 获得真实ANSYS复核依据后，选择复核状态、输入备注并保存。人工登记“已复核”不等于实验验证或产品验收。

候选最多 20,000。中断、失败或超时任务可点“重试任务”，重试会保留原记录并生成新的任务 ID。

## 8. 模型与历史

查看新旧历史指标、区域误差及参数水平留出，表格可横向滚动。历史测试已用于诊断，不是全新独立验收集。内部水平留出为插值压力测试，两端为边界外推压力测试。历史最多列出最近200条；查看记录不重新运行模型。

## 9. 常见错误

|现象|处理|
|---|---|
|页面空白或停在加载提示|先Ctrl+F5强刷；检查前端是否正常运行、依赖是否完整；F12的Console首条红色错误可定位加载失败|
|Cannot find module ...vite.js / vite不是命令|停止本项目前端，在frontend运行npm ci，成功后重启|
|npm ci报EPERM / esbuild.exe|前端或构建进程占用文件，先在本项目终端Ctrl+C或stop脚本停止；不要重复并行安装|
|8000端口10048 / address already in use|已有服务，不要再次手动启动；使用脚本复用；确认不是其他服务后再处理|
|5173被占用|脚本不再自动跳5174；确认当前运行服务，避免打开错误端口|
|界面出现500或模型加载失败|查看backend.log与api.stderr.log，确认原算法目录存在，使用mywelding解释器|
|422 / Outside trained bounds|参数超范围或格式非法，按配置范围输入|
|候选规模过大|增大步长、缩小调整幅度或锁定更多参数|
|interrupted / timed_out / failed|任务已结束，可在任务详情显式重试|

日志位于 D:\Welding\welding_system\runtime\logs：ui.stdout.log/ui.stderr.log是前端，api.stdout.log/api.stderr.log是后端启动，backend.log记录请求与任务错误。一键启动会重用这些文件，排错时可先另存旧日志。

## 10. 数据位置与边界

数据库runtime/db/system.db保存历史与复核信息，不要当缓存删除。导出位于runtime/exports/<任务ID>。模型及仿真CSV仍在原算法目录；不要移动、覆盖原模型目录。默认路径由项目相邻关系解析；迁移电脑通过ALGORITHM_ROOT配置。

.env.example仅是示例，不自动加载；在启动终端使用 `$env:ALGORITHM_ROOT='新目录'` 设置后再启动。Windows 启停脚本监听本机，使用管理员登录。内网发布见 [Linux 容器部署](deploy.md)。
