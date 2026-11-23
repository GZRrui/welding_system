param([string]$Python="D:\miniconda3\envs\mywelding\python.exe")
$ErrorActionPreference="Stop"
$root=Split-Path $PSScriptRoot -Parent
$logs=Join-Path $root 'runtime/logs'
New-Item -ItemType Directory -Force $logs | Out-Null
if(!(Test-Path $Python)){throw "Python不存在：$Python。请用 -Python 指定解释器。"}
$vite=Join-Path $root 'frontend/node_modules/vite/bin/vite.js'
if(!(Test-Path $vite)){throw "前端依赖缺失。先停止本项目前端，再在 frontend 运行 npm ci，成功后重新启动。"}
$node=(Get-Command node.exe -ErrorAction Stop).Source
$managed=@{}
$statePath=Join-Path $root 'runtime/processes.json'
if(Test-Path $statePath){$old=Get-Content $statePath -Raw|ConvertFrom-Json;foreach($prop in $old.PSObject.Properties){$managed[$prop.Name]=$prop.Value}}
function Wait-Ready([string]$url,$process){
 for($i=0;$i -lt 60;$i++){
  if($process -and $process.HasExited){throw "服务提前退出，请查看 $logs"}
  try{$res=Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2;if($res.StatusCode -eq 200){return}}catch{}
  Start-Sleep -Milliseconds 500
 }
 throw "服务启动超时：$url，请查看 $logs"
}
function Remember([string]$name,$process){$managed[$name]=@{id=$process.Id;started=$process.StartTime.ToUniversalTime().ToString('o')}}
$apiPort=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if($apiPort){
 try{$info=Invoke-RestMethod 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 5}catch{throw '8000端口已被其他服务占用，未停止该服务。'}
 if(!$info.paths.'/api/v1/tasks' -or !$info.paths.'/api/v1/compare'){throw '8000端口不是本系统接口，未停止该服务。'}
 Write-Output '后端已运行，复用现有服务。'
}else{
 Push-Location "$root/backend"
 try{& $Python -m alembic upgrade head;if($LASTEXITCODE -ne 0){throw '数据库迁移失败'}}finally{Pop-Location}
 $env:SESSION_SECURE="false"
 $api=Start-Process $Python -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory "$root/backend" -WindowStyle Hidden -RedirectStandardOutput "$logs/api.stdout.log" -RedirectStandardError "$logs/api.stderr.log" -PassThru
 Remember 'api' $api
 $managed|ConvertTo-Json|Set-Content $statePath
 Wait-Ready 'http://127.0.0.1:8000/api/v1/health' $api
}
$uiPort=Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if($uiPort){
 try{$page=Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 5}catch{throw '5173端口已占用，无法确认服务，请检查。'}
 if($page.Content -notmatch '/src/main.ts'){throw '5173端口不是本系统页面，未停止该服务。'}
 Write-Output '前端已运行，复用现有服务。'
}else{
 $ui=Start-Process $node -ArgumentList 'node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort' -WorkingDirectory "$root/frontend" -WindowStyle Hidden -RedirectStandardOutput "$logs/ui.stdout.log" -RedirectStandardError "$logs/ui.stderr.log" -PassThru
 Remember 'ui' $ui
 $managed|ConvertTo-Json|Set-Content $statePath
 Wait-Ready 'http://127.0.0.1:5173/src/main.ts' $ui
}
Write-Output "服务检查通过。页面 http://127.0.0.1:5173 / 接口 http://127.0.0.1:8000/docs / 日志 $logs"
Write-Output '如果页面空白，按 Ctrl+F5；若仍失败，查看页面错误提示和使用手册。'
