# 金融资产问答系统 - PowerShell 命令脚本

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

function Show-Help {
    Write-Host "金融资产问答系统 - 可用命令:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  .\commands.ps1 install      - 安装所有依赖"
    Write-Host "  .\commands.ps1 start        - 启动所有服务"
    Write-Host "  .\commands.ps1 stop         - 停止所有服务"
    Write-Host "  .\commands.ps1 restart      - 重启所有服务"
    Write-Host "  .\commands.ps1 logs         - 查看服务日志"
    Write-Host "  .\commands.ps1 clean        - 清理数据和缓存"
    Write-Host "  .\commands.ps1 test         - 运行测试"
    Write-Host "  .\commands.ps1 kb-refresh   - 刷新知识库"
    Write-Host "  .\commands.ps1 kb-test      - 测试知识库数据源"
    Write-Host "  .\commands.ps1 status       - 查看服务状态"
    Write-Host ""
}

function Install-Dependencies {
    Write-Host "安装后端依赖..." -ForegroundColor Yellow
    Set-Location backend
    uv sync
    Set-Location ..
    
    Write-Host "安装前端依赖..." -ForegroundColor Yellow
    Set-Location frontend
    bun install
    Set-Location ..
    
    Write-Host "✅ 依赖安装完成" -ForegroundColor Green
}

function Start-Services {
    Write-Host "启动所有服务..." -ForegroundColor Yellow
    docker-compose up -d
    Write-Host "✅ 服务已启动" -ForegroundColor Green
    Write-Host "前端: http://localhost:5173" -ForegroundColor Cyan
    Write-Host "后端: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "API 文档: http://localhost:8000/docs" -ForegroundColor Cyan
}

function Stop-Services {
    Write-Host "停止所有服务..." -ForegroundColor Yellow
    docker-compose stop
    Write-Host "✅ 服务已停止" -ForegroundColor Green
}

function Restart-Services {
    Write-Host "重启所有服务..." -ForegroundColor Yellow
    docker-compose restart
    Write-Host "✅ 服务已重启" -ForegroundColor Green
}

function Show-Logs {
    docker-compose logs -f
}

function Clean-Data {
    Write-Host "清理数据和缓存..." -ForegroundColor Yellow
    docker-compose down -v
    
    if (Test-Path "backend\chroma_db") {
        Remove-Item -Recurse -Force "backend\chroma_db\*"
    }
    
    if (Test-Path "backend\data\app.db") {
        Remove-Item -Force "backend\data\app.db"
    }
    
    Write-Host "✅ 清理完成" -ForegroundColor Green
}

function Run-Tests {
    Write-Host "运行后端测试..." -ForegroundColor Yellow
    Set-Location backend
    uv run pytest
    Set-Location ..
    
    Write-Host "运行前端测试..." -ForegroundColor Yellow
    Set-Location frontend
    bun test
    Set-Location ..
}

function Refresh-KnowledgeBase {
    Write-Host "刷新知识库..." -ForegroundColor Yellow
    Set-Location backend
    uv run python scripts/refresh_knowledge.py --run-now
    Set-Location ..
    Write-Host "✅ 知识库刷新完成" -ForegroundColor Green
}

function Test-KnowledgeBase {
    Write-Host "测试知识库数据源..." -ForegroundColor Yellow
    Set-Location backend
    uv run python scripts/test_fetchers.py
    Set-Location ..
}

function Show-Status {
    Write-Host "服务状态:" -ForegroundColor Cyan
    docker-compose ps
}

# 主逻辑
switch ($Command.ToLower()) {
    "help" { Show-Help }
    "install" { Install-Dependencies }
    "start" { Start-Services }
    "stop" { Stop-Services }
    "restart" { Restart-Services }
    "logs" { Show-Logs }
    "clean" { Clean-Data }
    "test" { Run-Tests }
    "kb-refresh" { Refresh-KnowledgeBase }
    "kb-test" { Test-KnowledgeBase }
    "status" { Show-Status }
    default { 
        Write-Host "未知命令: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
    }
}
