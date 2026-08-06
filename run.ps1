# 智序者 v1 · 启动器
# 用法: .\run.ps1    （PowerShell 右键运行，或在终端执行）

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          智序者 zhixuzhe v1         ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 检查 .env
if (-not (Test-Path ".env")) {
    Write-Host "  首次运行，需要设置 DeepSeek API Key。" -ForegroundColor Yellow
    Write-Host "  获取 Key: https://platform.deepseek.com/api_keys" -ForegroundColor DarkGray
    Write-Host ""
    $key = Read-Host "  请输入 DEEPSEEK_API_KEY"
    if (-not $key) {
        Write-Host "  错误: 未输入 Key，退出。" -ForegroundColor Red
        Read-Host "按 Enter 关闭"
        exit 1
    }
    "DEEPSEEK_API_KEY=$key" | Out-File -FilePath ".env" -Encoding utf8
    Write-Host "  已保存到 .env" -ForegroundColor Green
    Write-Host ""
}

# 检查 Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  错误: 未找到 Python，请先安装 Python 3.10+." -ForegroundColor Red
    Read-Host "按 Enter 关闭"
    exit 1
}

# 启动
python -m engine.core

# 退出后暂停（双击运行时有用）
if ($host.Name -match "ConsoleHost") {
    Write-Host ""
    Read-Host "按 Enter 关闭"
}
