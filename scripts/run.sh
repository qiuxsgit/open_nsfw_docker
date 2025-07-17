#!/bin/bash

# 容器配置参数（可调整）
CONTAINER_NAME="nsfw-api"
PORT_MAPPING="5000:5000"
IMAGE_NAME="nsfw-api"
ENV_VARS=("-e" "GUNICORN_WORKERS=8" "-e" "GUNICORN_TIMEOUT=300")

# 处理 -pf 参数
if [[ "$1" == "-pf" ]]; then
    if [[ -n "$2" && -f "$2" ]]; then
        PASSWORD_FILE="$2"
        VOLUME_MOUNT="-v $PASSWORD_FILE:/py_config/password.txt:ro"
        echo "使用密码文件: $PASSWORD_FILE"
        shift 2
    else
        echo "错误：必须提供有效的密码文件路径"
        echo "用法: $0 -pf /path/to/password.txt"
        exit 1
    fi
else
    echo "错误：必须使用 -pf 参数指定密码文件"
    echo "用法: $0 -pf /path/to/password.txt"
    exit 1
fi

# 检查并移除同名容器
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "发现已存在的容器 [$CONTAINER_NAME]，正在停止并移除..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1
    echo "旧容器 [$CONTAINER_NAME] 已成功移除"
fi

# 运行新容器
echo "正在启动新的容器 [$CONTAINER_NAME]..."
docker run -d \
  -p "$PORT_MAPPING" \
  "${ENV_VARS[@]}" \
  ${VOLUME_MOUNT} \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  "$IMAGE_NAME"

# 检查容器状态
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "容器 [$CONTAINER_NAME] 启动成功！"
    echo "可通过以下命令查看日志：docker logs -f $CONTAINER_NAME"
else
    echo "警告：容器 [$CONTAINER_NAME] 启动可能失败，请检查！"
    exit 1
fi