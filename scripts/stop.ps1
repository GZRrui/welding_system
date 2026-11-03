$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$path=Join-Path $root 'runtime/processes.json'
if(!(Test-Path $path)){Write-Output '没有脚本管理的进程。手动启动的服务请回到对应终端按 Ctrl+C。';exit}
$entries=Get-Content $path -Raw|ConvertFrom-Json
foreach($entry in $entries.PSObject.Properties){
 $record=$entry.Value
 if(!$record.id -or !$record.started){Write-Output '跳过旧格式进程记录，手动启动的服务请在原终端停止。';continue}
 $p=Get-Process -Id $record.id -ErrorAction SilentlyContinue
 if($p -and $p.StartTime.ToUniversalTime().ToString('o') -eq $record.started){
  $children=Get-CimInstance Win32_Process -Filter "ParentProcessId=$($p.Id)"
  foreach($child in $children){if($child.ExecutablePath -eq "$root\frontend\node_modules\@esbuild\win32-x64\esbuild.exe"){Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue}}
  Stop-Process -Id $p.Id
  Write-Output "已停止本脚本管理的 $($entry.Name)"
 }
}
Remove-Item -LiteralPath $path
Write-Output '其他终端或软件启动的服务不在停止范围。'
