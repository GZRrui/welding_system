# 接口

完整请求模式见运行后的 `/docs` 与 `/openapi.json`。统一前缀 `/api/v1`。登录和健康检查公开。当前会话、退出、改密和业务接口校验会话 Cookie；POST 和 PATCH 请求携带登录或当前会话接口返回的 `csrf_token`，请求头为 `X-CSRF-Token`。登录请求只需 JSON 用户名、密码。

|方法|路径|用途|
|---|---|---|
|GET|health|服务就绪及当前模型包版本|
|POST|auth/login|传入 username 和 password，签发 Cookie 并返回 csrf_token|
|GET|auth/session|返回用户名和 csrf_token，刷新空闲计时|
|POST|auth/logout|撤销当前会话并清除 Cookie|
|POST|auth/password|传入 current_password 和 new_password，成功后撤销全部会话|
|GET|config?model=enhanced|范围、限值、容差版本|
|GET|models|可信登记、新旧指标、区域及水平留出|
|GET|overview|真实样本、批次、业务数量|
|POST|predict|model + current五参数，输出SI值与区间、保守上界|
|POST|trend|同上 + axis + points(2~31)，返回两顺序及精确匹配ANSYS点|
|POST|compare|固定四参数，两顺序差异与区间|
|POST|tasks|steps/max_change/locked/orders，202返回任务ID|
|GET|tasks/{id}|任务状态、结果、候选复核|
|POST|tasks/{id}/retry|重试中断、失败或超时的任务，202 返回新任务 ID|
|GET|history|最近200条持久业务记录|
|PATCH|candidates/{id}|status pending/reviewed/rejected，notes|
|GET|tasks/{id}/exports/{kind}|白名单 recommendations/ansys_verification_queue/all_candidates|

会话无效返回 401，CSRF 校验失败返回 403，登录限流或推荐队列已满返回 429。非法输入 422，缺失 404，未完成导出或当前状态不可重试返回 409。响应含X-Request-ID；内部失败日志记录标识。模型只能 enhanced/baseline，客户端不能指定文件路径。历史与推荐均保留完整模型运行ID、容差摘要ID。复核是人工登记状态，不自动证明ANSYS验证通过。
