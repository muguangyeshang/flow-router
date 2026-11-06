# flow-router

[![CI](https://github.com/AYAN-2026/flow-router/actions/workflows/ci.yml/badge.svg)](https://github.com/AYAN-2026/flow-router/actions/workflows/ci.yml)

**Problem:** 你的 agent 有 N 条流程/工具，用户说一句大白话，走哪条？靠 LLM 猜，又贵又会自信地答错——把"讲 TCP 三次握手"误判成"走爬虫流程"。

**flow-router 用词法打分 + 双门拒答回答这个问题：** 每条请求给出最高分流程和命中依据；分数或置信度不达标时**明确拒答**而不是硬选一条。拒答是功能，不是失败。

```bash
pip install flow-router
flow-router init my-flows.json          # 生成配置骨架，把示例换成你的业务
flow-router --config my-flows.json find 我要抓一批新闻列表页
# → 爬虫（触发词精确·列表页，score=604 conf=1.0）
```

纯 Python 标准库，零第三方依赖。中文场景：触发词/说法表/排除条款/CJK 两字组 idf。

## 三种用法

```bash
# 1) Python API
from flow_router import Router
r = Router(cfg)                    # cfg 见 init 生成的骨架
r.find("用户原话")                 # {"abstained": bool, "hit": {...}, "ranked": [...]}

# 2) CLI
flow-router --config flows.json --eval eval.json holdout   # 冻结集验收 + 余量报告

# 3) MCP server —— agent 一行配置接入
flow-router --config flows.json serve-mcp
```

MCP 配置（Claude / WorkBuddy / 任何支持 MCP 的 agent）：

```json
{ "mcpServers": { "flow-router": {
    "command": "flow-router", "args": ["--config", "/path/to/flows.json", "serve-mcp"] } } }
```

## 与同类项目对比

| | flow-router | [semantic-router](https://github.com/aurelio-labs/semantic-router) | [llm-intent-router](https://github.com/1084669403/llm-intent-router) |
|---|---|---|---|
| 依赖 | **零**（纯标准库） | embedding 模型 + 向量库 | LLM 调用 |
| 每次路由成本 | **p50≈0.1ms，单线程 ~11,700 routes/s**（`python bench.py` 可复现） | 嵌入推理 | 一次 LLM token |
| 拒答机制 | **双门**（置信度门 + 绝对分门），校准/留出集实测定阈值 | 置信度阈值 | 阈值 |
| 排除条款 not_for | 有（负向词主动排除，单向匹配防误伤） | 无 | 无 |
| 验收体系 | calibrate 网格搜阈值 + holdout 余量报告（余量不足标"脆弱"） | 无 | 无 |
| 可解释性 | 每条结果给出命中档位和词（触发词精确·列表页） | 黑盒向量 | 半黑盒 |

**什么时候选词法而不是语义：** 你有明确触达词（业务流程、工具名、命令词），要求可解释、可回归验收、不引入模型。**什么时候别选：** 用户表述高度多样且无明显关键词——先建负对照集再动手。我们在一个 2987 技能的生产系统上实测过四轮语义方案：正例命中率大胜，但 20 道冻结负对照的假接受数**翻倍**，结论是直接上会更坏。这个对比方法（正例集 + 冻结负对照 + 双门阈值）本仓库的 `calibrate`/`holdout` 直接内置。

## 基准

```bash
python bench.py          # 冷启动 / 单次延迟 p50·p95 / 单线程吞吐，末行 BENCH-DONE
```

参考值（本机实测两轮一致）：冷启动 0.02ms；p50≈0.09ms、p95≈0.18ms；≈11,700 routes/s。数字随机器变化，以你自己跑的为准。

## 机制速览

- **五档加权**：触发词精确(34) > 流程名(30) > 触发词包含(26) > 说法表(24) > 挂载技能(20) > 全文(10)，各档乘 BM25 风格 idf；dominant 聚合防多词堆分
- **说法表**：整句口语模板（"把网站内容弄到表格里"），模板一半以上两字组命中才算，防单字误触
- **排除条款**：`not_for: ["数据库"]` 让"给数据库加索引优化查询"不进爬虫流程——这是匹配算法结构上做不到的事（阈值救不了：因为"采集数据"是合法用法）
- **双门拒答**：只留置信度门会被 filler 词稀释误放行，只留绝对分门会被语料规模漂移打穿——两道都要

## 自验收

```bash
python flow_router.py --config flows.json lint                                  # 结构校验
python flow_router.py --config flows.json --eval eval.json calibrate            # 搜 0 错阈值
python flow_router.py --config flows.json --eval eval.json holdout              # 冻结集 9/9 + 余量报告
```

demo 自带可跑：`lint` 过、`holdout` 9/9 PASS（余量可答侧 +120 / 拒答侧 +300）。

已知边界（不藏）：触发词包含档是缺陷源（「会议室」⊂「会议纪要」），靠排除条款+双门+不可答样本压住；阈值余量 <100 分的尺子对语料规模敏感，加语料就重跑 calibrate。

## License

MIT
