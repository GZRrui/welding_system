# 接口

完整请求模式见运行后的 `/docs` 与 `/openapi.json`。统一前缀 `/api/v1`。

|方法|路径|用途|
|---|---|---|
|GET|health|服务存活|
|GET|config?model=enhanced|范围、限值、容差版本|
|GET|models|可信登记、新旧指标、区域及水平留出|
|GET|overview|真实样本、批次、业务数量|
|POST|predict|model + current五参数，输出SI值与区间、保守上界|
|POST|trend|同上 + axis + points(2~31)，返回两顺序及精确匹配ANSYS点|
|POST|compare|固定四参数，两顺序差异与区间|
|POST|tasks|steps/max_change/locked/orders，202返回任务ID|
|GET|tasks/{id}|任务状态、结果、候选复核|
|GET|history|最近200条持久业务记录|
|PATCH|candidates/{id}|status pending/reviewed/rejected，notes|
|GET|tasks/{id}/exports/{kind}|白名单 recommendations/ansys_verification_queue/all_candidates|

非法输入422，缺失404，未完成导出409。响应含X-Request-ID；内部失败日志记录标识。模型只能 enhanced/baseline，客户端不能指定文件路径。历史与推荐均保留完整模型运行ID、容差摘要ID。复核是人工登记状态，不自动证明ANSYS验证通过。
