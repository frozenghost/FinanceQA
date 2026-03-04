@echo off
REM 金融资产问答系统 - Windows 命令脚本

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="install" goto install
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="logs" goto logs
if "%1"=="clean" goto clean
if "%1"=="test" goto test
if "%1"=="kb-refresh" goto kb-refresh
if "%1"=="kb-test" goto kb-test
if "%1"=="status" goto status
goto help

:help
echo 金融资产问答系统 - 可用命令:
echo.
echo   commands.bat install      - 安装所有依赖
echo   commands.bat start        - 启动所有服务
echo   commands.bat stop         - 停止所有服务
echo   commands.bat restart      - 重启所有服务
echo   commands.bat logs         - 查看服务日志
echo   commands.bat clean        - 清理数据和缓存
echo   commands.bat test         - 运行测试
echo   commands.bat kb-refresh   - 刷新知识库
echo   commands.bat kb-test      - 测试知识库数据源
echo   commands.bat status       - 查看服务状态
echo.
goto end

:install
echo 安装后端依赖...
cd backend
call uv sync
cd ..
echo 安装前端依赖...
cd frontend
call bun install
cd ..
echo ✅ 依赖安装完成
goto end

:start
echo 启动所有服务...
docker-compose up -d
echo ✅ 服务已启动
echo 前端: http://localhost:5173
echo 后端: http://localhost:8000
echo API 文档: http://localhost:8000/docs
goto end

:stop
echo 停止所有服务...
docker-compose stop
echo ✅ 服务已停止
goto end

:restart
echo 重启所有服务...
docker-compose restart
echo ✅ 服务已重启
goto end

:logs
docker-compose logs -f
goto end

:clean
echo 清理数据和缓存...
docker-compose down -v
if exist backend\chroma_db rmdir /s /q backend\chroma_db
if exist backend\data\app.db del /f backend\data\app.db
echo ✅ 清理完成
goto end

:test
echo 运行后端测试...
cd backend
call uv run pytest
cd ..
echo 运行前端测试...
cd frontend
call bun test
cd ..
goto end

:kb-refresh
echo 刷新知识库...
cd backend
call uv run python scripts/refresh_knowledge.py --run-now
cd ..
echo ✅ 知识库刷新完成
goto end

:kb-test
echo 测试知识库数据源...
cd backend
call uv run python scripts/test_fetchers.py
cd ..
goto end

:status
echo 服务状态:
docker-compose ps
goto end

:end
