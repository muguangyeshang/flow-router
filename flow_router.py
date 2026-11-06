#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flow-router —— 中文任务路由器（词法打分 + 双门拒答 + 校准/留出集验收）

从生产系统 flow-find.py 泛化而来，配置外置（JSON），纯标准库，无第三方依赖。

核心机制（每一条都是生产环境踩坑换来的，注释里写为什么）：
- 五档加权：触发词精确 > 触发词包含 > 流程名 > 挂载技能 > 全文命中
- dominant 聚合：最高档 + 其余打折（DISCOUNT），抑制多词堆分
- 排除条款 not_for：负向词出现在查询里 → 整条打折。单向匹配（n in t），
  反向（t in n）会因子串关系误伤所有合法查询
- 双门拒答：confidence < ABSTAIN_MIN（比值门）或 score < SCORE_MIN（绝对分门）
  两道门都不能省：只留比值门会被 filler 词稀释误放行，只留绝对分门会被
  语料规模漂移打穿
- calibrate：用可答/不可答样本网格搜阈值；holdout：冻结集验收 + 余量报告，
  余量 < 阈值视为脆弱（语料一变就可能翻盘）

用法：
  python flow_router.py --config flows.json find 把这个网站的价格抓下来
  python flow_router.py --config flows.json --eval eval.json calibrate
  python flow_router.py --config flows.json --eval eval.json holdout
  python flow_router.py --config flows.json lint
"""
import argparse
import json
import math
import re
import sys

# —— 五档基准分（权重再乘 idf）。数值沿用生产库 2026-10-27 校准结果 ——
W_TRIGGER = 34   # 触发词逐字相等
W_SUB = 26       # 触发词被查询词包含（已知缺陷源：日常词是专业词子串就能拿分，见 not_for/门）
W_NAME = 30      # 查询词出现在流程名里
W_ALIAS = 24     # 说法表模板命中（低于触发词包含，因为模板更宽）
W_SKILL = 20     # 挂载技能名命中
W_BLOB = 10      # 流程正文全文包含
DISCOUNT = 0.3   # dominant 聚合：非最高档得分打 7 折
NOTFOR_PENALTY = 0.35  # 排除条款命中后的整体折价
ALIAS_SIM = 0.5  # 说法表模板一半以上两字组出现才算命中
_LABEL = {W_TRIGGER: "触发词", W_SUB: "触发词包含", W_NAME: "流程名",
          W_ALIAS: "说法表", W_SKILL: "挂载技能", W_BLOB: "全文"}


def cjk_bigrams(s):
    """分词：ASCII 连续段整取，CJK 段切两字组。中文检索的两字组是性价比最高的粒度。"""
    out = []
    for run in re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]+', s):
        if not ('\u4e00' <= run[0] <= '\u9fff'):
            out.append(run.lower())
        elif len(run) == 1:
            out.append(run)
        else:
            out += [run[i:i + 2] for i in range(len(run) - 1)]
    return out


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


class Router:
    def __init__(self, cfg):
        gate = cfg.get("gate", {})
        self.abstain_min = float(gate.get("abstain_min", 0.10))
        self.score_min = int(gate.get("score_min", 0))
        self.flows = cfg["flows"]
        for f in self.flows:
            f["_trig"] = [t.lower() for t in f.get("triggers", [])]
            f["_alias"] = list(f.get("alias", []))
            # not_for 只收长度>=2 的词：单字排除会误伤面太大
            f["_nots"] = [n.lower() for n in f.get("not_for", []) if len(n) >= 2]
            f["_skl"] = [s.lower() for s in f.get("skills", [])]
            f["_blob"] = f.get("doc", "")
        # idf 语料 = 各流程正文 + 触发词 + 技能名，可再补 corpus_extra
        # 为什么需要 idf：常见词（"数据""内容"）不该和专有触发词同权重
        self.corpus = [
            f["_blob"] + " " + " ".join(f.get("triggers", [])) + " " + " ".join(f.get("skills", []))
            for f in self.flows
        ]
        self.corpus += list(cfg.get("corpus_extra", []))

    def idf(self, t, cache=None):
        if cache is None:
            cache = {}
        if t in cache:
            return cache[t]
        df = sum(1 for d in self.corpus if t in d.lower())
        # BM25 风格 idf，整数化（生产库同款），df 越高分越低
        v = max(1, round(10 * math.log((len(self.corpus) + 1) / (df + 0.5))))
        cache[t] = v
        return v

    def _hit_base(self, t, f):
        """单词在某流程里的最高命中档位，None 表示不命中。
        注意：不含说法表档——说法表只按"模板一半以上字组命中"整条判，
        单词出现在模板字符串里就算命中会放过"帮我"这类 filler（实测踩坑）。"""
        if t in f["_trig"]:
            return W_TRIGGER
        if any(t in tr for tr in f["_trig"]):
            return W_SUB
        if t in f["name"].lower():
            return W_NAME
        if any(t in s for s in f["_skl"]):
            return W_SKILL
        if t in f["_blob"].lower():
            return W_BLOB
        return None

    def score(self, q):
        ql = q.lower()
        terms = uniq(cjk_bigrams(q))
        tset = set(terms)
        cache = {}
        # —— 精确触发词层：多字触发词（列表页/抓下来）整串出现在查询里。
        # 只靠两字组永远够不到"精确"档，多字触发词等于白配。
        exact_by_flow = []
        scope_trigs = set()
        for f in self.flows:
            hits = [tr for tr in dict.fromkeys(f["_trig"]) if tr in ql]
            exact_by_flow.append(hits)
            scope_trigs.update(hits)
        # ideal 只统计"在任一流程语料里够得着"的词。
        # 原版教训：把 filler（我想/这个/的）也进分母，会系统性压低大白话查询的
        # confidence，造成长度偏置——短关键词反而容易过门。
        in_scope = [W_TRIGGER * self.idf(tr, cache) for tr in scope_trigs]
        for t in terms:
            base = None
            for f in self.flows:
                base = self._hit_base(t, f)
                if base:
                    break
            if base:
                in_scope.append(base * self.idf(t, cache))
        if not in_scope:
            return []
        ideal = max(in_scope) + DISCOUNT * (sum(in_scope) - max(in_scope))

        ranked = []
        for fi, f in enumerate(self.flows):
            pairs, why = [], ""
            # 排除条款：单向 n in t。不能反向 t in n——"数据"会成为"数据库"的
            # 子串，误伤所有含"数据"的合法查询（生产实测）。
            blocked = [t for t in terms if any(n in t for n in f["_nots"])]
            for tr in exact_by_flow[fi]:
                pairs.append(W_TRIGGER * self.idf(tr, cache))
                why = why or f"触发词精确·{tr}"
            for t in terms:
                base = self._hit_base(t, f)
                if base:
                    pairs.append(base * self.idf(t, cache))
                    why = why or f"{_LABEL[base]}·{t}"
            # 说法表按模板整体判：模板一半以上两字组出现在查询里才算一次命中
            for a in f["_alias"]:
                bg = [b for b in uniq(cjk_bigrams(a)) if len(b) == 2]
                if not bg:
                    continue
                ov = sum(1 for b in bg if b in tset)
                if ov / len(bg) >= ALIAS_SIM:
                    pairs.append(W_ALIAS * self.idf(bg[0], cache))
                    why = why or f"说法表·{a[:12]}"
            if not pairs:
                continue
            s = max(pairs) + DISCOUNT * (sum(pairs) - max(pairs))
            if blocked:
                s = round(s * NOTFOR_PENALTY)
                why = f"排除条款·{'/'.join(blocked[:2])}（原 {round(s / NOTFOR_PENALTY)}）"
            ranked.append({
                "flow": f["name"],
                "score": round(s),
                "conf": round(s / ideal, 3) if ideal else 0.0,
                "why": why,
            })
        ranked.sort(key=lambda r: (-r["score"], r["flow"]))
        return ranked

    def find(self, q):
        """带拒答语义的匹配。abstained=True 时 hit 不存在。"""
        ranked = self.score(q)
        if not ranked:
            return {"ranked": [], "abstained": True, "reason": "no_hit"}
        top = ranked[0]
        if top["conf"] < self.abstain_min:
            return {"ranked": ranked, "abstained": True,
                    "reason": f"low_confidence({top['conf']}<{self.abstain_min})"}
        if top["score"] < self.score_min:
            return {"ranked": ranked, "abstained": True,
                    "reason": f"low_score({top['score']}<{self.score_min})"}
        return {"ranked": ranked, "abstained": False, "reason": "", "hit": top}


# —————————————————————— 验收/校准 ——————————————————————

def _wrong(ev, r):
    """返回 (误拒数, 误答数)。误拒=可答被拒/答错流程；误答=不可答过了门。"""
    miss = fa = 0
    for q, want in ev.get("answerable", []):
        res = r.find(q)
        if res["abstained"] or res["hit"]["flow"] != want:
            miss += 1
    for q in ev.get("unanswerable", []):
        if not r.find(q)["abstained"]:
            fa += 1
    return miss, fa


def cmd_calibrate(r, ev):
    """网格搜阈值。教训：阈值必须实测得出，不是拍的。"""
    best = []
    for i in range(1, 19):
        th = round(0.05 * i, 2)
        for sf in range(0, 2600, 200):
            r.abstain_min, r.score_min = th, sf
            miss, fa = _wrong(ev, r)
            if miss + fa == 0:
                best.append((th, sf))
    if not best:
        print("无 0 错组合：样本或匹配器需要改，调阈值救不了（生产库原话：这是词法方法的天花板）")
        return 1
    print(f"0 错组合共 {len(best)} 个；最紧 = th={best[0][0]}, sf={best[0][1]}"
          f" ｜ 最宽松 = th={best[-1][0]}, sf={best[-1][1]}")
    return 0


def cmd_holdout(r, ev, fragile_margin):
    """冻结留出集验收 + 余量报告。余量不足 = 语料一漂移就翻盘，必须扩样本重定。"""
    bad, lo_ans, hi_una = [], None, None
    for q, want in ev.get("answerable", []):
        res = r.find(q)
        got = None if res["abstained"] else res["hit"]["flow"]
        sc = res["hit"]["score"] if not res["abstained"] else (res["ranked"][0]["score"] if res["ranked"] else 0)
        ok = got == want
        if ok and not res["abstained"] and (lo_ans is None or sc < lo_ans[0]):
            lo_ans = (sc, q)
        print(f"  {'✓' if ok else '✗'} want={str(want):<6} got={got} score={sc}  {q}")
        if not ok:
            bad.append(q)
    for q in ev.get("unanswerable", []):
        res = r.find(q)
        ok = res["abstained"]
        sc = res["ranked"][0]["score"] if res["ranked"] else 0
        if not ok and (hi_una is None or sc > hi_una[0]):
            hi_una = (sc, q)
        verdict = "拒答" if ok else f"误答→{res['hit']['flow']}"
        print(f"  {'✓' if ok else '✗'} want=拒答   got={verdict} score={sc}  {q}")
        if not ok:
            bad.append(q)
    n = len(ev.get("answerable", [])) + len(ev.get("unanswerable", []))
    print(f"\n留出集 {n - len(bad)}/{n}（ABSTAIN_MIN={r.abstain_min} SCORE_MIN={r.score_min}）")
    if lo_ans:
        print(f"  可答侧最紧：{lo_ans[1]}  score={lo_ans[0]}  距下限 {lo_ans[0] - r.score_min:+d}")
    if hi_una:
        print(f"  拒答侧最紧：{hi_una[1]}  score={hi_una[0]}  距下限 {hi_una[0] - r.score_min:+d}")
    fragile = (lo_ans and lo_ans[0] - r.score_min < fragile_margin) or \
              (hi_una and r.score_min - hi_una[0] < fragile_margin)
    if fragile:
        print(f"  余量 < {fragile_margin} 视为脆弱：阈值一改就可能翻盘，必须扩充样本重定")
    print("结论：PASS" if not bad else "结论：FAIL")
    return 0 if not bad else 1


def cmd_lint(r):
    """配置结构校验：防'路由按配置走、人按文档审'的两套答案。"""
    errs = []
    if not r.flows:
        errs.append("flows 为空")
    names = set()
    for f in r.flows:
        n = f.get("name", "?")
        if n in names:
            errs.append(f"流程名重复：{n}")
        names.add(n)
        tr = f.get("triggers", [])
        if len(set(tr)) < 3:
            errs.append(f"{n}: 触发词少于 3 个")
        if len(set(tr)) != len(tr):
            errs.append(f"{n}: 触发词有重复")
        for a in f.get("alias", []):
            if a in tr:
                errs.append(f"{n}: 说法表与触发词重复：{a}")
        for x in f.get("not_for", []):
            if x in tr:
                errs.append(f"{n}: not_for 与触发词冲突：{x}")
    if errs:
        print("\n".join("  ✗ " + e for e in errs))
        print("结构校验：FAIL")
        return 1
    print(f"  {len(r.flows)} 条流程，结构校验：全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="中文任务路由器（词法 + 双门拒答）")
    ap.add_argument("--config", required=True, help="流程配置 JSON")
    ap.add_argument("--eval", help="验收样本 JSON（calibrate/holdout 需要）")
    ap.add_argument("--fragile", type=int, default=100, help="余量低于该值视为脆弱（holdout）")
    ap.add_argument("cmd", choices=["find", "calibrate", "holdout", "lint"])
    ap.add_argument("query", nargs="*", help="find 模式的查询")
    a = ap.parse_args()

    r = Router(json.load(open(a.config, encoding="utf-8-sig")))
    if a.cmd == "find":
        if not a.query:
            sys.exit("find 需要 query")
        res = r.find(" ".join(a.query))
        for x in res["ranked"][:5]:
            print(f"  {x['score']:>5}  conf={x['conf']:.3f}  {x['flow']}  | {x['why']}")
        if res["abstained"]:
            print(f"\n→ 拒答（{res['reason']}）：明确说库里没有，不给错的")
        else:
            print(f"\n→ {res['hit']['flow']}")
        return 0
    if a.cmd == "lint":
        return cmd_lint(r)
    if not a.eval:
        sys.exit(f"{a.cmd} 需要 --eval")
    ev = json.load(open(a.eval, encoding="utf-8-sig"))
    return cmd_calibrate(r, ev) if a.cmd == "calibrate" else cmd_holdout(r, ev, a.fragile)


if __name__ == "__main__":
    sys.exit(main())
