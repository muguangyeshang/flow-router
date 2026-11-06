# 贡献指南

## 开发环境

Python 3.8+，无第三方依赖。克隆即用：

```bash
git clone <repo-url> && cd flow-router
python -m unittest discover tests -v          # 全部测试
python flow_router.py --config flows.json lint
python flow_router.py --config flows.json --eval eval.json holdout
python bench.py --n 200
```

## 提交前必须全绿

| 命令 | 判据 |
|---|---|
| `python -m unittest discover tests` | 全部通过 |
| `flow_router.py --config flows.json lint` | 结构校验：全部通过 |
| `flow_router.py --config flows.json --eval eval.json holdout` | 退出码 0，余量 ≥ 100 |
| `flow_router.py --config flows.json --eval eval.json calibrate` | 0 错组合存在 |

## 改动规范

1. **改匹配器必加回归测试**。`tests/test_flow_router.py` 里每个用例对应一个已知边界或修过的 bug（见文件头注释），新 bug 修复必须先写红再修绿。
2. **改配置/样本必重跑 calibrate + holdout**。阈值余量 < 100 分视为脆弱（holdout 会标），不许带着"脆弱"结论合并。
3. **注释写"为什么"，不写"是什么"**。本仓库的关键行注释几乎全部来自生产环境踩坑记录，这是它最重要的资产，新增代码沿用这个习惯。
4. **纯标准库红线**：runtime 代码（`flow_router.py`）不引入任何第三方依赖；测试和 CI 也不引入（用 unittest，不用 pytest）。依赖一旦进来，"零依赖可嵌入 agent"这个卖点就没了。
5. **配置外置**：任何新的可调参数进 `flows.json`（gate 层）或函数参数，不写死在代码里。
6. **性能敏感路径标复杂度**：`score()` 对每条查询是 O(词数 × 流程数)，这是设计内的，改动若引入更差复杂度须在注释里说明理由。

## 提交信息

用中文一句话讲清"做了什么、为什么"。格式参考 git log：

```
v1.1: Python API+pip打包(pyproject)+MCP server(stdio纯标准库)+init脚手架+README对标竞品重写
修复: 说法表被单词包含误触（filler「帮我」直接拿504分过门）
```

## 不接受的方向

- 语义/embedding 匹配层：本项目定位是"词法可解释、零依赖、可回归验收"。要上语义请先建冻结负对照集并证明假接受不劣化（我们在生产系统实测过：语义方案让负对照假接受翻倍）。相关讨论开 issue 附数据。
