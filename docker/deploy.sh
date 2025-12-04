#!/bin/bash

# 小智硬件服务器一键部署脚本
# 支持本地构建、测试和云服务器部署

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
IMAGE_NAME="aitoys-hardware"
TAG="latest"
CONTAINER_NAME="aitoys-hardware-server"
PORT=8000

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 未安装，请先安装 $1"
        exit 1
    fi
}

# 检查Docker环境
check_docker() {
    print_info "检查Docker环境..."
    check_command docker
    
    # 检查Docker Compose命令
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
        print_info "使用 docker-compose 命令"
    elif docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
        print_info "使用 docker compose 命令"
    else
        print_error "未找到 docker-compose 或 docker compose 命令"
        exit 1
    fi
    
    # 检查Docker是否运行
    if ! docker info &> /dev/null; then
        print_error "Docker未运行，请启动Docker服务"
        exit 1
    fi
    
    print_success "Docker环境检查通过"
}

# 构建Docker镜像
build_image() {
    print_info "构建Docker镜像..."
    
    # 检查必要文件
    if [ ! -f "Dockerfile" ]; then
        print_error "Dockerfile不存在"
        exit 1
    fi
    
    if [ ! -f "../src/chat/main.py" ]; then
        print_error "src/chat/main.py不存在"
        exit 1
    fi
    
    if [ ! -f "../src/ota/main.py" ]; then
        print_error "src/ota/main.py不存在"
        exit 1
    fi
    
    # 构建镜像
    docker build -t ${IMAGE_NAME}:${TAG} -f Dockerfile ..
    
    if [ $? -eq 0 ]; then
        print_success "Docker镜像构建成功"
    else
        print_error "Docker镜像构建失败"
        exit 1
    fi
}

# 本地测试
test_local() {
    print_info "启动本地测试..."
    
    # 停止可能存在的容器
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
    
    # 创建必要目录
    mkdir -p ../docker/runtime/config
    mkdir -p ../docker/runtime/data
    mkdir -p ../docker/runtime/log
    
    # 运行容器
    docker run -d \
        --name ${CONTAINER_NAME} \
        -p ${PORT}:${PORT} \
        -v $(pwd)/../docker/runtime/config:/app/docker/runtime/config:ro \
        -v $(pwd)/../docker/runtime/data:/app/docker/runtime/data \
        -v $(pwd)/../docker/runtime/log:/app/docker/runtime/log \
        ${IMAGE_NAME}:${TAG}
    
    if [ $? -eq 0 ]; then
        print_success "容器启动成功"
        
        # 等待服务启动
        print_info "等待服务启动..."
        sleep 10
        
        # 测试健康检查
        if curl -f http://localhost:8001/aitoys/v1/health &>/dev/null; then
            print_success "健康检查通过"
        else
            print_warning "健康检查失败，请检查日志"
        fi
        
        print_info "WebSocket服务运行在: ws://localhost:${PORT}"
        print_info "健康检查地址: http://localhost:8001/aitoys/v1/health"
        print_info "查看日志: docker logs -f ${CONTAINER_NAME}"
    else
        print_error "容器启动失败"
        exit 1
    fi
}

# 停止本地服务
stop_local() {
    print_info "停止本地服务..."
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
    print_success "本地服务已停止"
}

# 部署到云服务器
deploy_to_server() {
    local server=$1
    
    if [ -z "$server" ]; then
        print_error "请指定服务器地址 (格式: user@host)"
        exit 1
    fi
    
    print_info "部署到服务器: $server"
    
    # 保存镜像
    local tar_file="${IMAGE_NAME}_${TAG}.tar"
    print_info "保存镜像到文件: $tar_file"
    docker save -o $tar_file ${IMAGE_NAME}:${TAG}
    
    # 传输到服务器
    print_info "传输镜像到服务器..."
    scp $tar_file $server:~/
    
    # 在服务器上加载镜像
    print_info "在服务器上加载镜像..."
    ssh $server "docker load -i ~/$tar_file && rm ~/$tar_file"
    
    # 清理本地文件
    rm $tar_file
    
    print_success "镜像已成功部署到服务器"
    print_info "在服务器上运行: docker run -d --name aitoys-server -p 8000:8000 ${IMAGE_NAME}:${TAG}"
}

# 使用Docker Compose部署
deploy_with_compose() {
    print_info "使用Docker Compose部署..."
    
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml不存在"
        exit 1
    fi
    
    # 检查并修复可能的镜像问题
    print_info "检查镜像兼容性..."
    if docker images | grep -q "${IMAGE_NAME}"; then
        print_info "发现本地镜像，检查是否需要重建..."
        # 强制重新构建镜像以避免兼容性问题
        $COMPOSE_CMD build --no-cache
    fi
    
    # 清理可能的问题容器
    print_info "清理可能的问题容器..."
    $COMPOSE_CMD down --remove-orphans 2>/dev/null || true
    
    # 启动服务
    print_info "启动服务..."
    if $COMPOSE_CMD up -d; then
        print_success "Docker Compose部署成功"
        print_info "查看服务状态: $COMPOSE_CMD ps"
        print_info "查看日志: $COMPOSE_CMD logs -f"
    else
        print_error "Docker Compose部署失败"
        print_error "尝试修复方案："
        print_error "1. 清理所有容器和镜像: $0 cleanup-all"
        print_error "2. 重新构建镜像: $0 build"
        print_error "3. 使用新版本Docker Compose"
        exit 1
    fi
}

# 停止Docker Compose服务
stop_compose() {
    print_info "停止Docker Compose服务..."
    $COMPOSE_CMD down
    print_success "Docker Compose服务已停止"
}

# 清理资源
cleanup() {
    print_info "清理Docker资源..."
    docker system prune -f
    print_success "清理完成"
}

# 深度清理所有资源
cleanup_all() {
    print_info "深度清理所有Docker资源..."
    
    # 停止所有容器
    print_info "停止所有容器..."
    docker stop $(docker ps -aq) 2>/dev/null || true
    
    # 删除所有容器
    print_info "删除所有容器..."
    docker rm $(docker ps -aq) 2>/dev/null || true
    
    # 删除所有镜像
    print_info "删除所有镜像..."
    docker rmi $(docker images -q) 2>/dev/null || true
    
    # 清理所有卷
    print_info "清理所有卷..."
    docker volume prune -f
    
    # 清理网络
    print_info "清理网络..."
    docker network prune -f
    
    # 系统清理
    print_info "系统清理..."
    docker system prune -af
    
    print_success "深度清理完成"
}

# 检查网络连接
check_network() {
    print_info "检查网络连接..."
    if ping -c 1 8.8.8.8 &>/dev/null; then
        print_success "网络连接正常"
        return 0
    else
        print_error "网络连接失败"
        return 1
    fi
}

# 推送镜像到Azure Container Registry
push_image() {
    local version="$1"
    
    if [[ -z "$version" ]]; then
        print_error "请提供版本号"
        print_error "用法: $0 push <version>"
        print_error "示例: $0 push 1.1"
        exit 1
    fi
    
    local source_image="${IMAGE_NAME}:${TAG}"
    local target_image="aitoys.azurecr.io/${IMAGE_NAME}:$version"
    
    print_info "推送镜像到 Azure Container Registry..."
    print_info "源镜像: $source_image"
    print_info "目标镜像: $target_image"
    
    # 检查源镜像是否存在
    if ! docker images | grep -q "${IMAGE_NAME}.*${TAG}"; then
        print_error "源镜像 $source_image 不存在"
        print_error "请先运行: $0 build"
        exit 1
    fi
    
    # 检查网络连接
    if ! check_network; then
        print_error "网络连接失败，无法推送镜像"
        exit 1
    fi
    
    # 标记镜像
    print_info "标记镜像..."
    if ! docker tag "$source_image" "$target_image"; then
        print_error "镜像标记失败"
        exit 1
    fi
    
    # 推送镜像
    print_info "推送镜像到注册表，这可能需要几分钟时间..."
    if docker push "$target_image"; then
        print_success "镜像推送成功"
        print_info "镜像地址: $target_image"
        
        # 清理本地标记的镜像
        print_info "清理本地标记镜像..."
        docker rmi "$target_image" || print_warning "清理本地标记镜像失败，但不影响推送结果"
    else
        print_error "镜像推送失败"
        print_error "可能的原因："
        print_error "1. 未登录到 Azure Container Registry"
        print_error "2. 网络连接问题"
        print_error "3. 权限不足"
        print_info "建议解决方案："
        print_info "1. 登录到 ACR: docker login aitoys.azurecr.io"
        print_info "2. 检查网络连接"
        print_info "3. 确认推送权限"
        
        # 清理失败的标记镜像
        docker rmi "$target_image" 2>/dev/null || true
        exit 1
    fi
}

# 从Azure Container Registry拉取镜像
pull_image() {
    local version="$1"
    
    if [[ -z "$version" ]]; then
        print_error "请提供版本号"
        print_error "用法: $0 pull <version>"
        print_error "示例: $0 pull 1.1"
        exit 1
    fi
    
    local remote_image="aitoys.azurecr.io/${IMAGE_NAME}:$version"
    local local_image="${IMAGE_NAME}:$version"
    
    print_info "从 Azure Container Registry 拉取镜像..."
    print_info "远程镜像: $remote_image"
    print_info "本地镜像: $local_image"
    
    # 检查网络连接
    if ! check_network; then
        print_error "网络连接失败，无法拉取镜像"
        exit 1
    fi
    
    # 拉取镜像
    print_info "拉取镜像，这可能需要几分钟时间..."
    if docker pull "$remote_image"; then
        print_success "镜像拉取成功"
        
        # 标记为本地镜像
        print_info "标记为本地镜像..."
        if docker tag "$remote_image" "$local_image"; then
            print_success "镜像标记成功"
            print_info "本地镜像: $local_image"
            
            # 清理远程镜像标签
            print_info "清理远程镜像标签..."
            docker rmi "$remote_image" || print_warning "清理远程镜像标签失败，但不影响拉取结果"
        else
            print_error "镜像标记失败"
            exit 1
        fi
    else
        print_error "镜像拉取失败"
        print_error "可能的原因："
        print_error "1. 未登录到 Azure Container Registry"
        print_error "2. 网络连接问题"
        print_error "3. 镜像不存在或权限不足"
        print_info "建议解决方案："
        print_info "1. 登录到 ACR: docker login aitoys.azurecr.io"
        print_info "2. 检查网络连接"
        print_info "3. 确认镜像版本存在"
        print_info "4. 检查拉取权限"
        exit 1
    fi
}

# 显示帮助信息
show_help() {
    echo "小智硬件服务器部署脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  build                   构建Docker镜像"
    echo "  test                    本地测试"
    echo "  stop                    停止本地服务"
    echo "  deploy <user@host>      部署到云服务器"
    echo "  compose                 使用Docker Compose部署"
    echo "  stop-compose            停止Docker Compose服务"
    echo "  push <version>          推送镜像到Azure Container Registry"
    echo "  pull <version>          从Azure Container Registry拉取镜像"
    echo "  cleanup                 清理Docker资源"
    echo "  cleanup-all             深度清理所有Docker资源"
    echo "  fix                     修复ContainerConfig错误"
    echo "  all                     完整流程：构建->测试->部署"
    echo "  help                    显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 build                构建镜像"
    echo "  $0 test                 本地测试"
    echo "  $0 deploy user@server   部署到服务器"
    echo "  $0 push 1.1             推送镜像到Azure ACR"
    echo "  $0 pull 1.1             从Azure ACR拉取镜像"
    echo "  $0 cleanup-all          深度清理所有Docker资源"
    echo "  $0 fix                  修复ContainerConfig错误"
    echo "  $0 all                  完整部署流程"
}

# 完整部署流程
full_deploy() {
    print_info "开始完整部署流程..."
    
    check_docker
    build_image
    test_local
    
    print_success "完整部署流程完成！"
    print_info "WebSocket服务运行在: ws://localhost:${PORT}"
    print_info "健康检查地址: http://localhost:8001/aitoys/v1/health"
    print_info "使用 '$0 stop' 停止服务"
}

# 主函数
main() {
    case "$1" in
        "build")
            check_docker
            build_image
            ;;
        "test")
            check_docker
            test_local
            ;;
        "stop")
            stop_local
            ;;
        "deploy")
            check_docker
            deploy_to_server "$2"
            ;;
        "compose")
            check_docker
            deploy_with_compose
            ;;
        "stop-compose")
            stop_compose
            ;;
        "push")
            check_docker
            push_image "$2"
            ;;
        "pull")
            check_docker
            pull_image "$2"
            ;;
        "cleanup")
            cleanup
            ;;
        "cleanup-all")
            cleanup_all
            ;;
        "fix")
            if [ -f "fix_container_config.sh" ]; then
                print_info "运行ContainerConfig错误修复脚本..."
                ./fix_container_config.sh all
            elif [ -f "fix_container_config.bat" ]; then
                print_info "运行Windows版ContainerConfig错误修复脚本..."
                ./fix_container_config.bat all
            else
                print_error "修复脚本不存在，请手动执行以下步骤："
                print_error "1. 清理所有Docker资源: $0 cleanup-all"
                print_error "2. 重新构建镜像: $0 build"
                print_error "3. 升级Docker Compose到最新版本"
                print_error "4. 重新部署: $0 compose"
                print_error ""
                print_error "或者手动执行以下命令："
                print_error "docker system prune -af"
                print_error "docker-compose down --remove-orphans"
                print_error "docker build --no-cache -t aitoys-hardware:latest -f Dockerfile .."
                print_error "docker-compose up -d"
            fi
            ;;
        "all")
            full_deploy
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        "")
            show_help
            ;;
        *)
            print_error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@" 