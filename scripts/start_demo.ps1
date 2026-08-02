# 一键本地体验（Windows PowerShell）
# 用法: .\scripts\start_demo.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Docker Postgres + Adminer"
docker compose up -d
docker compose ps

Write-Host "==> 检查 8001 端口"
$on8001 = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
if ($on8001) {
    Write-Host "    8001 已被占用，跳过启动后端（若需重启请先结束该进程）"
} else {
    Write-Host "==> 启动后端 (新窗口)"
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$Root\python-backend'; uvicorn main:app --host 127.0.0.1 --port 8001"
    )
}

Write-Host "==> 检查 3000 端口"
$on3000 = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
if ($on3000) {
    Write-Host "    3000 已被占用，跳过启动前端"
} else {
    Write-Host "==> 启动前端 (新窗口)"
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$Root\ui'; npm run dev"
    )
}

Write-Host ""
Write-Host "体验入口: http://localhost:3000/login"
Write-Host "账号: zhangsan / demo123  (订单 ABC123)"
Write-Host "      lisi / demo123      (越权测 ABC123)"
Write-Host "      admin / demo123"
Write-Host "Adminer: http://localhost:8080  (库 airline / airline / airline)"
Write-Host ""
Write-Host "推荐对话:"
Write-Host "  1. 退票政策是什么？          (RAG / FAQ)"
Write-Host "  2. 帮我查确认号 ABC123       (自己的订单)"
Write-Host "  3. 取消确认号 ABC123         (zhangsan 可退；lisi 应被拒)"
Write-Host "  4. 把 ABC123 改签到 NY900    (改签，确认号不变)"
Write-Host ""
Write-Host "验收: python eval\run_eval.py"
