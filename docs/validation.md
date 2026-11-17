# 本次验收结果

验证日期：2026-11-17。当前目录 `/Users/soda/code/one-system-model`。

## 环境与结论

Apple M5 Pro 上的 Apple `container`，Linux amd64 / Rosetta，8 CPU 配额，14GiB 内存限额，纯 CPU FP32。镜像 `one-system-model:1.2` 内含 THIS/THAT 1.2 固定版本权重，推理时不联网。

**完整 32,768 token 输入已在此限额内验证通过。目标 8C16G Ubuntu 尚未上机，性能不能直接套用 Mac / Rosetta 数据。**

运行参数：`THREADS=8`、`PREFILL_CHUNK_SIZE=512`、单个推理工作线程、最多 8 个等待请求。32K 是共享 state、所有问题、所有选项及格式标记的合计。

## 真实模型 / HTTP 验证

| 项目 | 结果 |
|---|---|
| 短中文请求，32 tokens、1 个 Noul | 预热后 5 次中位数 **0.532 秒**；范围 0.513–0.551 秒 |
| 英文 32K，证据在开头，3 个问题 | **503.90 秒**；Choice、Noul 正确；Score 绝对误差 0.000028 |
| 中文 32K，证据在结尾，3 个问题 | **534.77 秒**；Choice、Noul 正确；Score 绝对误差 0.003443 |
| 超过完整 32K 窗口 | HTTP 422 `max_tokens_exceeded`，没有截断 |
| 3 个并发 HTTP 请求 | 均返回 200，串行推理、其余排队；这是功能验收，不是吞吐基准 |
| 容器 cgroup 峰值内存 | **13.430 GiB**，包括模型、进程和容器计费的文件页缓存 |
| OOM / swap | OOM 0、OOM kill 0；swap.current 0；容器内没有启用 swap 设备 |
| 进程自身峰值 RSS | 11.091 GiB；与上述容器总内存口径不同 |

这些是两个合成长上下文用例和一个短文本重复用例。4 个 Choice/Noul 判断通过、两个 Score 接近标签，不代表全面业务准确率。短请求耗时也不能推广到长文或排队状态。32K 在此环境需要约 **8.4–8.9 分钟**。

## 接口与容器交付

- **12 项协议 / 边界测试通过**：鉴权、结构化 JSON、模型别名、zstd/gzip、解压体积上限、图片/Box 拒绝、队列满 429、异常后的队列恢复、官方置信度公式、单选项、token 边界、255 选项。HTTP 队列及错误分支用轻量替身隔离测试；token 边界使用真实 tokenizer。
- **真实 FP32 权重一致性**：1,172 tokens、3 个问题；分块 prefill 与整段、禁用缓存的前向计算相比，最大概率误差 `4.0745362639427185e-10`，低于 `0.0002`。
- **官方 Python SDK 0.7.5、JS SDK 0.7.0 / 0.5.7**：未改客户端，真实模型调用、模型列表、三种 primitive、zstd 请求全部通过。Python 原始响应及两组长文响应按官方 OpenAPI 校验。
- **实际开源项目 `@jkudish/jev-mcp 0.14.8`**：未改源码，通过 stdio MCP 完成握手和工具调用；注册 12 个工具；`jev_noul` 对退款/发货两个命题返回正确判断。其 HTTP 请求在中文长文之后排队，记录的 277.15 秒包括等待时间，不作为该工具的推理延迟。
- **禁网推理**：用最终镜像、`--network none`、8 CPU、14GiB，完成真实 Choice 判断。
- **Docker 导入**：Docker Engine 28.5.2 实际 `docker load` 成功，识别为 `linux/amd64`。Compose 配置通过 Docker Compose 解析；服务运行验收使用 Apple container，尚未执行目标 Ubuntu 的 Compose 启动。

## 已知边界

只支持文本 Choice / Noul / Score；图片和 Box 明确拒绝，因此不能覆盖全部 Jev 项目的全部功能。Jev 模型名只是兼容别名，返回身份保持 THIS/THAT。概率和任务效果来自 THIS/THAT，不继承 Jev 的模型能力。

一个模型进程串行计算。长请求会阻塞后续短请求；等待队列满则 429。客户端超时需要覆盖推理加排队时间。官方 SDK 环境变量能改变连接地址；项目硬编码的 URL、超时仍需通过其配置入口调整。

## 原始证据

工作区 `artifacts/` 下保存：`contract-tests.log`、`parity.json`、`http-smoke.json`、`short-benchmark.json`、`long-cases.json`、`long-results.json`、`over-limit.json`、`python-sdk.json`、`javascript-sdk.json`、`jev-mcp-result.json`、`resources-after-long.json`、`resource-timeline.jsonl`、`offline-inference.log`、`docker-load.log`、`docker-image-verification.txt`。

离线包的 `verification/` 保留主要 JSON 证据。目标 Ubuntu 可执行 `sudo python3 verify.py`，以及 `sudo python3 verify.py --long` 重新测量；输出带时间戳，不会覆盖本次记录。
