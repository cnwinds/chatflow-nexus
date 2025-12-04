@echo off
setlocal enabledelayedexpansion

REM 小智硬件服务器Windows部署脚本
REM 支持本地构建、测试和云服务器部署

set IMAGE_NAME=aitoys-hardware
set TAG=latest
set CONTAINER_NAME=aitoys-hardware-server
set PORT=8000

REM 颜色定义（Windows CMD不支持ANSI颜色，使用简单的文本）
set INFO=[INFO]
set SUCCESS=[SUCCESS]
set WARNING=[WARNING]
set ERROR=[ERROR]

REM 打印消息函数
:print_info
echo %INFO% %~1
goto :eof

:print_success
echo %SUCCESS% %~1
goto :eof

:print_warning
echo %WARNING% %~1
goto :eof

:print_error
echo %ERROR% %~1
goto :eof

REM 检查命令是否存在
:check_command
where %1 >nul 2>&1
if %errorlevel% neq 0 (
    call :print_error "%1 未安装，请先安装 %1"
    exit /b 1
)
goto :eof

REM 检查Docker环境
:check_docker
call :print_info "检查Docker环境..."
call :check_command docker
if %errorlevel% neq 0 exit /b 1

REM 检查Docker Compose命令
docker-compose version >nul 2>&1
if %errorlevel% equ 0 (
    set COMPOSE_CMD=docker-compose
    call :print_info "使用 docker-compose 命令"
) else (
    docker compose version >nul 2>&1
    if %errorlevel% equ 0 (
        set COMPOSE_CMD=docker compose
        call :print_info "使用 docker compose 命令"
    ) else (
        call :print_error "未找到 docker-compose 或 docker compose 命令"
        exit /b 1
    )
)

REM 检查Docker是否运行
docker info >nul 2>&1
if %errorlevel% neq 0 (
    call :print_error "Docker未运行，请启动Docker Desktop"
    exit /b 1
)

call :print_success "Docker环境检查通过"
goto :eof

REM 构建Docker镜像
:build_image
call :print_info "构建Docker镜像..."

REM 检查必要文件
if not exist "Dockerfile" (
    call :print_error "Dockerfile不存在"
    exit /b 1
)

if not exist "..\src\chat\main.py" (
    call :print_error "src\chat\main.py不存在"
    exit /b 1
)

if not exist "..\src\ota\main.py" (
    call :print_error "src\ota\main.py不存在"
    exit /b 1
)

REM 构建镜像
docker build -t %IMAGE_NAME%:%TAG% -f Dockerfile ..

if %errorlevel% equ 0 (
    call :print_success "Docker镜像构建成功"
) else (
    call :print_error "Docker镜像构建失败"
    exit /b 1
)
goto :eof

REM 本地测试
:test_local
call :print_info "启动本地测试..."

REM 停止可能存在的容器
docker stop %CONTAINER_NAME% >nul 2>&1
docker rm %CONTAINER_NAME% >nul 2>&1

REM 创建必要目录
if not exist "..\docker\runtime\config" mkdir "..\docker\runtime\config"
if not exist "..\docker\runtime\data" mkdir "..\docker\runtime\data"
if not exist "..\docker\runtime\log" mkdir "..\docker\runtime\log"

REM 运行容器
docker run -d --name %CONTAINER_NAME% -p %PORT%:%PORT% -p 8001:8001 -v %cd%\..\docker\runtime\config:/app/docker/runtime/config:ro -v %cd%\..\docker\runtime\data:/app/docker/runtime/data -v %cd%\..\docker\runtime\log:/app/docker/runtime/log %IMAGE_NAME%:%TAG%

if %errorlevel% equ 0 (
    call :print_success "容器启动成功"
    
    REM 等待服务启动
    call :print_info "等待服务启动..."
    timeout /t 10 /nobreak >nul
    
    REM 测试健康检查
    curl -f http://localhost:8001/aitoys/v1/health >nul 2>&1
    if %errorlevel% equ 0 (
        call :print_success "健康检查通过"
    ) else (
        call :print_warning "健康检查失败，请检查日志"
    )
    
    call :print_info "WebSocket服务运行在: ws://localhost:%PORT%"
    call :print_info "健康检查地址: http://localhost:8001/aitoys/v1/health"
    call :print_info "查看日志: docker logs -f %CONTAINER_NAME%"
) else (
    call :print_error "容器启动失败"
    exit /b 1
)
goto :eof

REM 停止本地服务
:stop_local
call :print_info "停止本地服务..."
docker stop %CONTAINER_NAME% >nul 2>&1
docker rm %CONTAINER_NAME% >nul 2>&1
call :print_success "本地服务已停止"
goto :eof

REM 部署到云服务器
:deploy_to_server
if "%~1"=="" (
    call :print_error "请指定服务器地址 (格式: user@host)"
    exit /b 1
)

call :print_info "部署到服务器: %~1"

REM 保存镜像
set TAR_FILE=%IMAGE_NAME%_%TAG%.tar
call :print_info "保存镜像到文件: %TAR_FILE%"
docker save -o %TAR_FILE% %IMAGE_NAME%:%TAG%

REM 传输到服务器
call :print_info "传输镜像到服务器..."
scp %TAR_FILE% %~1:~/

REM 在服务器上加载镜像
call :print_info "在服务器上加载镜像..."
ssh %~1 "docker load -i ~/%TAR_FILE% && rm ~/%TAR_FILE%"

REM 清理本地文件
del %TAR_FILE%

call :print_success "镜像已成功部署到服务器"
call :print_info "在服务器上运行: docker run -d --name aitoys-server -p 8000:8000 -p 8001:8001 %IMAGE_NAME%:%TAG%"
goto :eof

REM 使用Docker Compose部署
:deploy_with_compose
call :print_info "使用Docker Compose部署..."

if not exist "docker-compose.yml" (
    call :print_error "docker-compose.yml不存在"
    exit /b 1
)

REM 启动服务
%COMPOSE_CMD% up -d

if %errorlevel% equ 0 (
    call :print_success "Docker Compose部署成功"
    call :print_info "查看服务状态: %COMPOSE_CMD% ps"
    call :print_info "查看日志: %COMPOSE_CMD% logs -f"
) else (
    call :print_error "Docker Compose部署失败"
    exit /b 1
)
goto :eof

REM 停止Docker Compose服务
:stop_compose
call :print_info "停止Docker Compose服务..."
%COMPOSE_CMD% down
call :print_success "Docker Compose服务已停止"
goto :eof

REM 清理资源
:cleanup
call :print_info "清理Docker资源..."
docker system prune -f
call :print_success "清理完成"
goto :eof

REM 检查网络连接
:check_network
call :print_info "检查网络连接..."
ping -n 1 8.8.8.8 >nul 2>&1
if %errorlevel% equ 0 (
    call :print_success "网络连接正常"
    exit /b 0
) else (
    call :print_error "网络连接失败"
    exit /b 1
)

REM 推送镜像到Azure Container Registry
:push_image
if "%~2"=="" (
    call :print_error "请提供版本号"
    call :print_error "用法: %0 push ^<version^>"
    call :print_error "示例: %0 push 1.1"
    exit /b 1
)

set VERSION=%~2
set SOURCE_IMAGE=%IMAGE_NAME%:%TAG%
set TARGET_IMAGE=aitoys.azurecr.io/%IMAGE_NAME%:%VERSION%

call :print_info "推送镜像到 Azure Container Registry..."
call :print_info "源镜像: %SOURCE_IMAGE%"
call :print_info "目标镜像: %TARGET_IMAGE%"

REM 检查源镜像是否存在
docker images | findstr "%IMAGE_NAME%.*%TAG%" >nul 2>&1
if %errorlevel% neq 0 (
    call :print_error "源镜像 %SOURCE_IMAGE% 不存在"
    call :print_error "请先运行: %0 build"
    exit /b 1
)

REM 检查网络连接
call :check_network
if %errorlevel% neq 0 (
    call :print_error "网络连接失败，无法推送镜像"
    exit /b 1
)

REM 标记镜像
call :print_info "标记镜像..."
docker tag "%SOURCE_IMAGE%" "%TARGET_IMAGE%"
if %errorlevel% neq 0 (
    call :print_error "镜像标记失败"
    exit /b 1
)

REM 推送镜像
call :print_info "推送镜像到注册表，这可能需要几分钟时间..."
docker push "%TARGET_IMAGE%"
if %errorlevel% equ 0 (
    call :print_success "镜像推送成功"
    call :print_info "镜像地址: %TARGET_IMAGE%"
    
    REM 清理本地标记的镜像
    call :print_info "清理本地标记镜像..."
    docker rmi "%TARGET_IMAGE%" >nul 2>&1
    if %errorlevel% neq 0 (
        call :print_warning "清理本地标记镜像失败，但不影响推送结果"
    )
) else (
    call :print_error "镜像推送失败"
    call :print_error "可能的原因："
    call :print_error "1. 未登录到 Azure Container Registry"
    call :print_error "2. 网络连接问题"
    call :print_error "3. 权限不足"
    call :print_info "建议解决方案："
    call :print_info "1. 登录到 ACR: docker login aitoys.azurecr.io"
    call :print_info "2. 检查网络连接"
    call :print_info "3. 确认推送权限"
    
    REM 清理失败的标记镜像
    docker rmi "%TARGET_IMAGE%" >nul 2>&1
    exit /b 1
)
goto :eof

REM 从Azure Container Registry拉取镜像
:pull_image
if "%~2"=="" (
    call :print_error "请提供版本号"
    call :print_error "用法: %0 pull ^<version^>"
    call :print_error "示例: %0 pull 1.1"
    exit /b 1
)

set VERSION=%~2
set REMOTE_IMAGE=aitoys.azurecr.io/%IMAGE_NAME%:%VERSION%
set LOCAL_IMAGE=%IMAGE_NAME%:%VERSION%

call :print_info "从 Azure Container Registry 拉取镜像..."
call :print_info "远程镜像: %REMOTE_IMAGE%"
call :print_info "本地镜像: %LOCAL_IMAGE%"

REM 检查网络连接
call :check_network
if %errorlevel% neq 0 (
    call :print_error "网络连接失败，无法拉取镜像"
    exit /b 1
)

REM 拉取镜像
call :print_info "拉取镜像，这可能需要几分钟时间..."
docker pull "%REMOTE_IMAGE%"
if %errorlevel% equ 0 (
    call :print_success "镜像拉取成功"
    
    REM 标记为本地镜像
    call :print_info "标记为本地镜像..."
    docker tag "%REMOTE_IMAGE%" "%LOCAL_IMAGE%"
    if %errorlevel% equ 0 (
        call :print_success "镜像标记成功"
        call :print_info "本地镜像: %LOCAL_IMAGE%"
        
        REM 清理远程镜像标签
        call :print_info "清理远程镜像标签..."
        docker rmi "%REMOTE_IMAGE%" >nul 2>&1
        if %errorlevel% neq 0 (
            call :print_warning "清理远程镜像标签失败，但不影响拉取结果"
        )
    ) else (
        call :print_error "镜像标记失败"
        exit /b 1
    )
) else (
    call :print_error "镜像拉取失败"
    call :print_error "可能的原因："
    call :print_error "1. 未登录到 Azure Container Registry"
    call :print_error "2. 网络连接问题"
    call :print_error "3. 镜像不存在或权限不足"
    call :print_info "建议解决方案："
    call :print_info "1. 登录到 ACR: docker login aitoys.azurecr.io"
    call :print_info "2. 检查网络连接"
    call :print_info "3. 确认镜像版本存在"
    call :print_info "4. 检查拉取权限"
    exit /b 1
)
goto :eof

REM 运行指定版本的镜像
:run_version
if "%~2"=="" (
    call :print_error "请提供版本号"
    call :print_error "用法: %0 run ^<version^>"
    call :print_error "示例: %0 run 1.1"
    exit /b 1
)

set VERSION=%~2
set RUN_IMAGE=%IMAGE_NAME%:%VERSION%
set VERSION_CONTAINER_NAME=%CONTAINER_NAME%-%VERSION%

call :print_info "运行版本 %VERSION% 的镜像..."

REM 检查镜像是否存在
docker images | findstr "%IMAGE_NAME%.*%VERSION%" >nul 2>&1
if %errorlevel% neq 0 (
    call :print_warning "本地镜像 %RUN_IMAGE% 不存在，尝试从远程拉取..."
    call :pull_image "pull" "%VERSION%"
    if %errorlevel% neq 0 (
        call :print_error "无法获取镜像 %RUN_IMAGE%"
        exit /b 1
    )
)

REM 停止可能存在的同版本容器
docker stop %VERSION_CONTAINER_NAME% >nul 2>&1
docker rm %VERSION_CONTAINER_NAME% >nul 2>&1

REM 创建必要目录
if not exist "..\docker\runtime\config" mkdir "..\docker\runtime\config"
if not exist "..\docker\runtime\data" mkdir "..\docker\runtime\data"
if not exist "..\docker\runtime\log" mkdir "..\docker\runtime\log"

REM 运行容器
call :print_info "启动容器 %VERSION_CONTAINER_NAME%..."
docker run -d --name %VERSION_CONTAINER_NAME% -p %PORT%:%PORT% -p 8001:8001 -v %cd%\..\docker\runtime\config:/app/docker/runtime/config:ro -v %cd%\..\docker\runtime\data:/app/docker/runtime/data -v %cd%\..\docker\runtime\log:/app/docker/runtime/log %RUN_IMAGE%

if %errorlevel% equ 0 (
    call :print_success "容器启动成功"
    
    REM 等待服务启动
    call :print_info "等待服务启动..."
    timeout /t 10 /nobreak >nul
    
    REM 测试健康检查
    curl -f http://localhost:8001/aitoys/v1/health >nul 2>&1
    if %errorlevel% equ 0 (
        call :print_success "健康检查通过"
    ) else (
        call :print_warning "健康检查失败，请检查日志"
    )
    
    call :print_info "WebSocket服务运行在: ws://localhost:%PORT%"
    call :print_info "健康检查地址: http://localhost:8001/aitoys/v1/health"
    call :print_info "查看日志: docker logs -f %VERSION_CONTAINER_NAME%"
    call :print_info "停止服务: docker stop %VERSION_CONTAINER_NAME%"
) else (
    call :print_error "容器启动失败"
    exit /b 1
)
goto :eof

REM 显示帮助信息
:show_help
echo 小智硬件服务器部署脚本
echo.
echo 用法: %0 [选项]
echo.
echo 选项:
echo   build                   构建Docker镜像
echo   test                    本地测试
echo   stop                    停止本地服务
echo   deploy ^<user@host^>      部署到云服务器
echo   compose                 使用Docker Compose部署
echo   stop-compose            停止Docker Compose服务
echo   push ^<version^>           推送镜像到Azure Container Registry
echo   pull ^<version^>           从Azure Container Registry拉取镜像
echo   run ^<version^>            运行指定版本的镜像（自动拉取如果不存在）
echo   cleanup                 清理Docker资源
echo   all                     完整流程：构建-^>测试-^>部署
echo   help                    显示此帮助信息
echo.
echo 示例:
echo   %0 build                构建镜像
echo   %0 test                 本地测试
echo   %0 deploy user@server   部署到服务器
echo   %0 push 1.1             推送镜像到Azure ACR
echo   %0 pull 1.1             从Azure ACR拉取镜像
echo   %0 run 1.1              运行版本1.1的镜像
echo   %0 all                  完整部署流程
goto :eof

REM 完整部署流程
:full_deploy
call :print_info "开始完整部署流程..."

call :check_docker
if %errorlevel% neq 0 exit /b 1

call :build_image
if %errorlevel% neq 0 exit /b 1

call :test_local
if %errorlevel% neq 0 exit /b 1

call :print_success "完整部署流程完成！"
call :print_info "WebSocket服务运行在: ws://localhost:%PORT%"
call :print_info "健康检查地址: http://localhost:8001/aitoys/v1/health"
call :print_info "使用 '%0 stop' 停止服务"
goto :eof

REM 主函数
if "%~1"=="build" (
    call :check_docker
    if %errorlevel% neq 0 exit /b 1
    call :build_image
) else if "%~1"=="test" (
    call :check_docker
    if %errorlevel% neq 0 exit /b 1
    call :test_local
) else if "%~1"=="stop" (
    call :stop_local
) else if "%~1"=="deploy" (
    call :check_docker
    if %errorlevel% neq 0 exit /b 1
    call :deploy_to_server "%~2"
) else if "%~1"=="compose" (
    call :check_docker
    if %errorlevel% neq 0 exit /b 1
    call :deploy_with_compose
) else if "%~1"=="stop-compose" (
    call :stop_compose
) else if "%~1"=="push" (
    call :check_docker
    if %errorlevel% neq 0 exit /b 1
    call :push_image "%~1" "%~2"
) else if "%~1"=="pull" (
    call :check_docker
    if %errorlevel% neq 0 exit /b 1
    call :pull_image "%~1" "%~2"
) else if "%~1"=="run" (
    call :check_docker
    if %errorlevel% neq 0 exit /b 1
    call :run_version "%~1" "%~2"
) else if "%~1"=="cleanup" (
    call :cleanup
) else if "%~1"=="all" (
    call :full_deploy
) else if "%~1"=="help" (
    call :show_help
) else if "%~1"=="" (
    call :show_help
) else (
    call :print_error "未知选项: %~1"
    call :show_help
    exit /b 1
)

endlocal 