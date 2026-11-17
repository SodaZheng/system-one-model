# THIS/THAT 1.2 — Ubuntu 8C16G 离线包

目标：Linux amd64，Docker Engine + Compose 插件，无显卡。镜像包含全部依赖和 THIS/THAT 1.2 权重。磁盘建议至少空余 15GB。

```bash
sudo ./start.sh
sudo docker compose ps
curl http://127.0.0.1:8080/health
```

启动脚本校验 SHA256、创建 `.env` 密钥（已存在则保留）、`docker load`、`docker compose up -d`。服务使用 8 CPU、14GiB 内存，不使用额外 swap，预留内存给系统。

接入 Jev 文本项目：

```bash
export TYPESAFE_BASE_URL=http://服务器内网IP:8080
export TYPESAFE_API_KEY='此目录 .env 中的 API_KEY'
export TYPESAFE_DEFAULT_MODEL=jev-latest
```

客户端应放宽超时：Python 3600 秒，JS 3600000 毫秒。32K 是包含 state、全部问题、全部选项的完整输入上限。支持 Choice / Noul / Score；不支持图片 / Box。最多 8 个请求排队，一个请求在计算；不要预期长文本或并发达到云端 Jev 的低延迟。

镜像在 Apple Silicon 的 Linux amd64 / Rosetta 下验证；不是目标 Ubuntu 的性能承诺。验证结果见随包 `validation.md`。

调整监听地址 / 端口：`.env` 内设置 `BIND_ADDRESS=内网IP`、`PORT=8080`。Compose 默认监听全部网卡，API 请求必须使用本地 Bearer 密钥。

目标机复测：`sudo python3 verify.py` 验证短请求；`sudo python3 verify.py --long` 验证两个精确 32K 输入，并保存带时间戳的结果文件。
