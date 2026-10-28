#!/bin/sh
# 后台启动翻唱服务（只听 127.0.0.1:8790），日志在 server.log；顺带启动网易云接口容器 ncm-api
cd "$(dirname "$0")"
if docker start ncm-api >/dev/null 2>&1; then
  echo "网易云接口 ncm-api 已启动"
else
  echo "没有 ncm-api 容器，网易云来源不可用（要用就在项目目录执行 docker compose --profile cover up -d ncm-api）"
fi
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "翻唱服务已经在运行（pid $(cat server.pid)）"; exit 0
fi
nohup .venv/bin/python server.py >> server.log 2>&1 &
echo $! > server.pid
echo "翻唱服务已启动（pid $!）"
