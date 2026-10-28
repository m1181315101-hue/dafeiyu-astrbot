#!/bin/sh
# 停翻唱服务，顺带停网易云接口容器 ncm-api
cd "$(dirname "$0")"
if [ -f server.pid ] && kill "$(cat server.pid)" 2>/dev/null; then
  echo "翻唱服务已停止"; rm -f server.pid
else
  echo "翻唱服务没在运行"; rm -f server.pid
fi
docker stop ncm-api >/dev/null 2>&1 && echo "网易云接口 ncm-api 已停止"
