# Jev 兼容范围

## 已实现

| 项目 | 行为 |
|---|---|
| HTTP | `/v1/systemone`、`/v1/models`；Bearer 鉴权 |
| Noul | `{type: "noul", noul: P(true)}`，无独立 confidence |
| Choice | 字符串选项键、概率映射、所选键、官方公式 confidence；1–255 个选项 |
| Score | 1–10 个等级；概率加权分数、原始 legend、官方距离公式 confidence |
| JSON 内容 | 字符串、对象、数组 state；instructions 可为空；criteria 内可嵌套对象/数组 |
| SDK 请求压缩 | zstd、gzip、deflate；压缩前后均有 2MiB 上限 |
| 模型名 | `this-that-model-1.2`、`thisthat`、`thisthat-1.2`、HF 仓库名，以及 `jev` / `jev-latest` / `jev-preview` / `jev-数字版本` 别名 |
| 多问题 | 共享一个完整 prompt，一次逻辑前向计算；长 prompt 分块 prefill，保留注意力和线性状态缓存 |
| 并发 HTTP | 有限队列，模型串行计算；健康接口不会等待推理完成 |
| 超限 | 32,768 tokens 包括 state + 所有问题 + 选项 + 格式；HTTP 422 `max_tokens_exceeded`，不截断 |
| 返回身份 | `model` 始终是 `this-that-model-1.2`，不会冒充官方 Jev 权重 |

最新官方 OpenAPI 快照在 `upstream/typesafe-openapi.json`。真实响应已用该 schema 校验，官方 Python 0.7.5、JS 0.7.0 / 0.5.7 均进行过真实模型调用，并启用 zstd。

## 接入项目时的区别

“接口不改”指调用 `/v1/systemone` 的请求体和返回结构保持兼容。连接配置仍需将官方服务器地址替换成本服务；硬编码官方地址的项目必须提供或补上地址配置。不能通过本地镜像自动改变其他项目的网络目标。

- **官方 Python / JS SDK**：支持 `TYPESAFE_BASE_URL`、`TYPESAFE_API_KEY`、`TYPESAFE_DEFAULT_MODEL`；显式构造参数优先于环境变量。JS `timeout` 单位毫秒，Python 单位秒。
- **jev-mcp**：检查到当前依赖官方 JS SDK `^0.7.0`。实际 npm 0.14.8 已通过 stdio MCP 和本地 HTTP 的端到端 `jev_noul` 调用；无需改源码。设置 `JEV_PROVIDER=typesafe`、`TYPESAFE_BASE_URL` 和 `TYPESAFE_API_KEY`。本次验证两个文本命题，未验证全部 12 个工具或全部业务场景。
- **JevGrep**：检查到其直接实现 TypeSafe wire format，并有 provider `base_url` 配置。把 direct TypeSafe provider 地址指向此服务；其检索流程和质量还需要项目级验证。
- **jevmem、jev-pruner、jevclip、Paper Radar 等**：文本判断功能通常使用这些 primitive；本次验证了标准协议和 SDK，没有逐一部署这些完整项目，也没有修改它们。
- **浏览器或手机自动化项目**：依赖截图 / Box 的路径不可用；仅使用文字状态、DOM、控件列表的路径需要按项目验证。

## 不能等同的能力

THIS/THAT 1.2 仅处理文本；含 `assets` 的图片请求、Box 问题会明确返回 422，multipart 图片请求返回 415。不会把图片 URL 或 base64 当成已理解的图片。

8 核 CPU 下请求串行计算，排队不等于多个模型同时计算。一个很长的请求会让后面的短请求等待，队列满时返回 429。需要低延迟隔离时应使用独立实例/机器和更高内存预算。

相同 API 不等于相同概率、准确率、上下文质量、延迟或吞吐。原模型的校准依赖训练任务；官方 Jev 示例中的置信度阈值应重新验证。
