# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [1.1.5] - 2026-11-07

### 新增
- CLI 拒答时输出最接近候选（flow/score/conf/命中依据）+ 改进提示（补哪个流程的触发词/说法表、重跑 calibrate）——MCP 侧早有 closest 字段，CLI 漏了；模拟用户实测「我的快递到哪儿了」被拒后无从改进配置，才暴露

## [1.1.4] - 2026-11-07

### 新增
- 边界查询回归测试 7 例（实战自用探测）：空/纯空白、ASCII 大小写触发词、重复字无假命中、emoji 不崩、单字母被门拦住、只报技能名不过门、说法表仍命中

## [1.1.3] - 2026-11-07

### 新增
- README 首屏双语化：英文 Problem + Quick view + 快速命令段（目标用户是非中文的 agent 开发者），中文正文保留
- README 定位声明：明确"适合谁/不适合谁"（无现成流程的新手不是目标用户）
- `SECURITY.md`（安全策略：支持版本、漏洞报告渠道、攻击面说明——本工具无网络无子进程，唯一执行面是本地 config）
- `CODE_OF_CONDUCT.md`（Contributor Covenant 2.1）

## [1.1.1] - 2026-11-07

### 新增
- `.github/workflows/ci.yml`：lint / calibrate / holdout / init / pip 安装冒烟 / bench，Python 3.8 + 3.12 矩阵
- `bench.py`：可复现基准（冷启动 / 单次延迟 p50·p95 / 单线程吞吐），实测 p50≈0.09ms、≈11,700 routes/s
- `tests/`：unittest 正式测试（匹配器行为 + 已修 bug 回归锁 + 说法表/排除条款边界）

### 变更
- README 性能数字改为 `bench.py` 实测背书，移除无背书的"~微秒级"表述

## [1.1.0] - 2026-11-06

### 新增
- Python API：`pip install` 后 `from flow_router import Router`（pyproject.toml 打包）
- MCP server：`flow-router --config flows.json serve-mcp`，stdio JSON-RPC（MCP 2024-11-05 spec），暴露 `route` 工具，agent 一行配置接入
- `init` 脚手架：`flow-router init my-flows.json` 生成 flows.json + eval.json 骨架
- README 重写：问题先行、三种用法、与 semantic-router / llm-intent-router 六维对比表

### 修复
- 说法表被单词包含误触：filler「帮我」出现在模板字符串里直接拿 504 分过门——`_hit_base` 移除说法表档，说法表只按"模板一半以上两字组命中"整条判
- 多字触发词（列表页/抓下来）永远无法精确命中：新增整串精确触发词层

## [1.0.0] - 2026-11-06

### 首个版本
- 五档加权词法路由（触发词精确 34 / 流程名 30 / 触发词包含 26 / 说法表 24 / 挂载技能 20 / 全文 10）× BM25 风格 idf
- 排除条款 `not_for`（单向 n in t 匹配防误伤）
- 双门拒答（置信度门 + 绝对分门）
- `calibrate` 网格搜阈值 / `holdout` 冻结集验收 + 余量报告 / `lint` 结构校验
- 从生产系统 flow-find.py（2987 技能 / 46 项常驻门禁）泛化，配置全外置，纯标准库零依赖
