# flow-router

中文任务路由器：把用户的口语化请求路由到预定义的「流程/技能组」，答不了就明确拒答——**拒答是功能，不是失败**。

从一套跑了数月的生产检索系统（2987 技能 / 5 流程 / 46 项常驻门禁）中泛化而来，纯 Python 标准库，零依赖。

## 特性

- **五档加权打分**：触发词精确(34) > 流程名(30) > 触发词包含(26) > 说法表(24) > 挂载技能(20) > 全文(10)，各档乘 BM25 风格 idf
- **说法表**：不是每个人都说「爬虫」，有人说「把网站内容弄到表格里」。模板一半以上两字组命中才算，防单字误触
- **排除条款 `not_for`**：「给数据库加索引优化查询」不该进爬虫流程——调阈值救不了，因为「采集数据」是合法用法。排除条款做的是匹配算法结构上做不到的事：主动排除
- **双门拒答**：比值门（confidence）+ 绝对分门（score）。只留一道门都会被特定查询形状绕过（实测教训）
- **calibrate**：用可答/不可答样本网格搜出阈值，不拍脑袋
- **holdout**：冻结留出集验收 + 余量报告，余量不足直接标「脆弱」
- **lint**：触发词重复/冲突、说法表污染，结构坏立刻红

## 快速开始

```bash
# 结构校验
python flow_router.py --config flows.json lint

# 路由
python flow_router.py --config flows.json find 我要抓一批新闻列表页
# → 爬虫  score=... conf=...（触发词·列表页）

# 拒答
python flow_router.py --config flows.json find 给我讲讲 TCP 三次握手
# → 拒答（no_hit）

# 校准阈值（改了配置/样本后跑）
python flow_router.py --config flows.json --eval eval.json calibrate

# 留出集验收（冻结样本，别用它们调参）
python flow_router.py --config flows.json --eval eval.json holdout
```

要求：Python 3.8+，无第三方依赖。

## 配置格式

`flows.json`：

```jsonc
{
  "gate": { "abstain_min": 0.10, "score_min": 450 },   // 双门阈值，用 calibrate 实测定
  "flows": [
    {
      "name": "爬虫",
      "triggers": ["爬虫", "抓取", "抓新闻", "列表页"], // ≥3 个，lint 查重
      "alias": ["把网站内容弄到表格里"],                // 说法表，不算触发词
      "not_for": ["数据库", "ppt"],                     // 排除条款，命中整条打 0.35 折
      "skills": ["scrape-define"],                      // 挂载技能名（可选）
      "doc": "网站数据采集流程……"                       // 全文语料（必填，也是 idf 语料）
    }
  ],
  "corpus_extra": []   // 追加 idf 语料（可选），例如常见 filler 文本
}
```

`eval.json`：

```jsonc
{
  "answerable":   [["我要抓一批新闻列表页", "爬虫"]],
  "unanswerable": ["给我讲讲 TCP 三次握手"]
}
```

## 已知边界（不藏）

- 触发词包含档是**已知缺陷源**：日常词是专业词的子串就能拿分（「会议室」⊂「会议纪要」）。
  缓解手段是排除条款 + 双门 + 不可答样本压测；覆盖率打折的修法实测会一起杀掉合法短查询，不要试。
- 阈值余量只有几十分的尺子对语料规模敏感：加了新流程/新语料就重跑 calibrate 和 holdout。
- 语义（embedding）方案在该生产系统上实测过四轮：流程层正例大胜但负对照假接受翻倍，**未采用**。
  想做语义层的，先建负对照集再动手。

## 来源

生产库 `flow-find.py`（2026-10-27 起 46 项门禁中 6 项属于它，留出集 8/8、
流程负对照拒答 14/20）的泛化版：抽出匹配引擎，去掉对具体仓库的耦合，配置全外置。

## License

MIT
