# THIS/THAT 1.2 内网部署

此目录提供单模型、纯 CPU、完全离线运行的 THIS/THAT 1.2 服务，兼容 TypeSafe / Jev 的文本 System One HTTP 接口。镜像内含权重；运行时不访问 Hugging Face，也不调用 TypeSafe 云端。

- 固定权重：`flock-io/this-that-model-1.2`，revision `c4d1c30b8d512d278726de439b8cc81fccc70c8f`。
- 平台：Linux amd64；面向 8 核 / 16GiB Ubuntu，无需 GPU。
- 默认资源：8 CPU、14GiB 容器内存，留约 2GiB 给系统；一个模型进程、FP32。
- 完整输入窗口：**32,768 tokens**，包含共享 state、全部问题、全部选项及格式标记；不截断。
- 并发：一个请求在计算，最多 8 个请求排队；队列满时 HTTP 429 + `Retry-After`。
- 支持 Choice、Noul、Score、结构化 state / instructions / criteria、最多 255 个 Choice 选项、256 个问题。
- **没有图像、Box、音视频模型能力。接口兼容不代表模型效果或速度与 Jev 相同。**

## 当前 Mac 使用

服务地址：`http://127.0.0.1:8080`。当前电脑使用 Apple `container` 运行 Linux amd64 / Rosetta，**不是 macOS Metal 加速，也不是原生 Ubuntu 性能**。

```bash
curl http://127.0.0.1:8080/health
container logs one-system-model
```

本地访问密钥保存在本目录 `.env` 的 `API_KEY`，不要提交到 Git。首次初始化不会覆盖已有文件。

若容器已删除，可重新启动：

```bash
./scripts/run_apple.sh
```

Apple `container` 不接受 Docker 的 `/tmp:size=...` 挂载语法，因此本机启动脚本使用普通可写容器根目录；Ubuntu Compose 使用只读根目录和单独的 `/tmp`。

## Ubuntu 离线部署

传输当前已打包的 `artifacts/one-system-model-1.2-amd64-offline.tar.xz` 即可，内含镜像、启动脚本及验证文件；同名 `.sha256` 文件可用于检查传输是否完整。在 Ubuntu 上解压并启动：

```bash
sha256sum -c one-system-model-1.2-amd64-offline.tar.xz.sha256
tar -xJf one-system-model-1.2-amd64-offline.tar.xz
cd one-system-model-offline
sudo ./start.sh
```

压缩只减少传输体积，解压后是原始镜像。目标机器需要已安装 Docker Engine 和 Compose 插件，以及 `xz-utils`（供 `tar -xJf` 使用），预留至少 15GB 空闲磁盘。离线包不含本机密钥，启动时生成新的密钥。

也可将整个 `artifacts/offline/` 目录复制到 Ubuntu，再在复制后的目录运行：

```bash
cd /opt/one-system-model
sudo ./start.sh
sudo docker compose ps
curl http://127.0.0.1:8080/health
```

`start.sh` 校验 SHA256、导入 Docker 格式镜像、生成本机 `.env`、启动 Compose。首次模型加载需等待一会儿。镜像包含权重和依赖，不需要下载任何模型。Compose 将服务发布到内网机器的 8080 端口。

如需绑定特定内网地址，在 `.env` 增加 `BIND_ADDRESS=192.168.x.x`；修改端口用 `PORT=8080`。已有同名业务容器请先检查后再运行；Compose 会按此配置管理 `one-system-model`。

在目标机复验：

```bash
sudo docker compose logs --tail 30
sudo docker stats --no-stream one-system-model
sudo python3 verify.py
sudo python3 verify.py --long   # 两个 32K 用例，可能需要十几分钟
```

此交付的本机验证不能替代目标 Ubuntu CPU 的延迟测量。其他服务也消耗内存时，应确保这台机器确实能为容器保留 14GiB。

## 接入现有 Jev 项目

支持以下标准端点：

- `POST /v1/systemone`
- `GET /v1/models`
- `GET /health`（无需密钥）

为现有项目设置 **API 根地址、本地密钥和足够的超时**，问题格式、SDK 调用和结果读取方式可保持不变：

```bash
export TYPESAFE_BASE_URL=http://内网服务器IP:8080
export TYPESAFE_API_KEY='从目标服务器 .env 取得的 API_KEY'
export TYPESAFE_DEFAULT_MODEL=jev-latest
```

API 根地址通常不带 `/v1`；为兼容已有配置，也接受 `/v1/v1/systemone`、`/v1/v1/models`。`jev-latest`、`jev-preview`、`jev-1.14` 等版本名作为本地别名使用，返回的 `model` 如实标明 `this-that-model-1.2`。

**32K 的 CPU 推理可能需要数分钟。** 官方 JS SDK 默认超时为 10 秒，需要在调用项目的超时设置里调大，例如 3,600 秒。环境变量不一定能覆盖项目代码中显式设置的 URL、模型或超时，具体见 [兼容说明](docs/compatibility.md)。

Python（官方 `typesafe-sdk==0.7.5`）：

```python
from typesafe_sdk import Noul, TypeSafeClient

with TypeSafeClient(timeout=3600) as client:
    result = client.system_one(
        state={"ticket": "请取消订单并退款"},
        questions={"refund": Noul(instructions="客户要求退款吗？")},
    )
    print(result.nouls["refund"].noul)
```

JavaScript（官方 `@typesafe-ai/sdk`）：

```javascript
import { TypeSafeClient } from '@typesafe-ai/sdk';
const client = new TypeSafeClient({ timeout: 3_600_000 });
const result = await client.systemOne({
  state: { ticket: '请取消订单并退款' },
  questions: { refund: { type: 'noul', instructions: '客户要求退款吗？' } },
});
console.log(result.answers.refund.noul);
```

Score 返回按概率加权的浮点分数及原始 `legend`；Choice / Score 的 `confidence` 使用 TypeSafe 当前公布的公式。概率来自 THIS/THAT，不能继承 Jev 的准确率或校准保证。

## 重建和验证

```bash
python3 scripts/download_model.py   # 下载固定版本并校验官方哈希
python3 scripts/init_env.py         # 只在 .env 不存在时创建
container build --platform linux/amd64 -t one-system-model:1.2 .
# 或在可联网 Ubuntu 上：
docker build --platform linux/amd64 -t one-system-model:1.2 .
```

依赖固定在 `requirements.lock`，模型文件和 SHA256 位于 `models/this-that-1.2/manifest.json`。上游代码来源记录见 [来源说明](docs/sources.md)。

```bash
# 不加载权重的协议、错误、队列和 token 边界测试：
container run --rm --arch amd64 --cpus 2 --memory 3G \
  -v "$PWD:/workspace" -w /workspace \
  -e PYTHONPATH=/workspace:/workspace/vendor/this-that-model \
  one-system-model:1.2 python -m unittest discover -s tests -v

# 对正在运行的真实 HTTP 服务验证：
python3 scripts/verify_http.py
# 生成精确 32K 用例后执行；可在任意带模型 tokenizer 的环境中生成：
container run --rm --arch amd64 --cpus 2 --memory 3G \
  -v "$PWD:/workspace" -w /workspace -e PYTHONPATH=/workspace \
  one-system-model:1.2 python scripts/make_long_cases.py
python3 scripts/verify_http.py --long
```

测试输出位于 `artifacts/`。`docs/validation.md` 记录本次实测结果及其边界。长文本用例用于验证容量、证据位置和基本判断，不是综合准确率评测。

官方 SDK 复验（需联网安装测试客户端；推理仍走本地服务）：

```bash
python3 -m venv artifacts/sdk-python/venv
artifacts/sdk-python/venv/bin/python -m pip install -r tests/requirements-sdk.txt
artifacts/sdk-python/venv/bin/python scripts/verify_sdk.py
npm ci --prefix tests/sdk-js --ignore-scripts
node scripts/verify_sdk.mjs
```

重新导出离线交付目录：`./scripts/export_offline.sh artifacts/export-new`。目标目录中的同名镜像 tar 必须不存在，转换器不会覆盖已有交付。
