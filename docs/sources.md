# 来源与固定版本

核对日期：2026-11-17（Asia/Taipei）。

- [THIS/THAT 上游](https://github.com/FLock-io/this-that-model)，本地 vendor commit `6af11c63c8bb260aa4bed2b7717f33f25decd16e`。保留原代码和 MIT LICENSE；使用其 prompt 和 label alphabet，新增本项目的协议转换和分块 CPU runtime，没有修改 vendor。
- [THIS/THAT 1.2 权重](https://huggingface.co/flock-io/this-that-model-1.2)，revision `c4d1c30b8d512d278726de439b8cc81fccc70c8f`。safetensors SHA256 `585295458a6b6e01162d2a72d33ba630c286b51c844869afc35272700c23f199`。
- [TypeSafe OpenAPI](https://api.typesafe.ai/openapi.json)，原始快照 `docs/upstream/typesafe-openapi.json`。
- [TypeSafe confidence 公式](https://docs.typesafe.ai/confidence)，快照 `docs/upstream/confidence.md`。
- [Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python)：验证 PyPI `typesafe-sdk==0.7.5`。
- [JS SDK](https://github.com/typesafe-ai/typesafe-sdk-js)：验证 npm `@typesafe-ai/sdk@0.7.0` 和 `0.5.7`。
- [JevGrep wire adapter](https://github.com/nassim-arifette/jevgrep/blob/main/src/evaluation/jev.ts)、[配置](https://github.com/nassim-arifette/jevgrep/blob/main/src/config.ts)；[jev-mcp 依赖](https://github.com/jkudish/jev-mcp/blob/main/package.json)。JevGrep 只做接口源码核对；另外安装并实际验证了 npm `@jkudish/jev-mcp@0.14.8` 的 `jev_noul` 工具。

`scripts/oci_to_docker.py` 复用本机既有 `/Users/soda/code/jev/src/jev/archive.py` 的转换实现，保留逐层 digest / DiffID 校验。此目录独立构建，不依赖旧 Jev 工作区，未修改旧项目或其配置。
