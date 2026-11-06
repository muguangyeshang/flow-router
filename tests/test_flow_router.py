#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flow-router 正式测试（纯标准库 unittest，python -m unittest discover tests 跑）。

CI 里的 lint/calibrate/holdout 是"配置对不对"的验收；这里测的是"匹配器行为
对不对"——每条用例对应一个已知边界或修过的 bug，回归时一眼知道坏在哪。
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flow_router  # noqa: E402

CFG = json.load(open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "flows.json"), encoding="utf-8-sig"))


def router():
    return flow_router.Router(json.loads(json.dumps(CFG)))


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.r = router()

    # —— 核心路由行为 ——
    def test_exact_trigger_routes(self):
        res = self.r.find("我要抓一批新闻列表页")
        self.assertFalse(res["abstained"])
        self.assertEqual(res["hit"]["flow"], "爬虫")

    def test_alias_template_routes(self):
        res = self.r.find("帮我把网站上的内容整理到表格里")
        self.assertFalse(res["abstained"])
        self.assertEqual(res["hit"]["flow"], "爬虫")

    def test_unanswerable_abstains(self):
        res = self.r.find("给我讲讲 TCP 三次握手")
        self.assertTrue(res["abstained"])

    def test_no_hit_reason(self):
        res = self.r.find("xyzzy 完全不相关的内容")
        self.assertTrue(res["abstained"])
        self.assertEqual(res["reason"], "no_hit")

    def test_result_has_why(self):
        res = self.r.find("我要抓一批新闻列表页")
        self.assertIn("触发词", res["hit"]["why"])

    def test_ranked_sorted_desc(self):
        res = self.r.find("抓取数据写报告")
        scores = [x["score"] for x in res["ranked"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    # —— 已知边界的回归锁：这些是修过的 bug，改坏必红 ——
    def test_filler_word_not_routed_via_alias_string(self):
        """filler「帮我」出现在说法表字符串里，不得因此命中说法表档（bug 回归）。"""
        res = self.r.find("帮我看看天气")
        if res["ranked"]:
            for x in res["ranked"]:
                self.assertNotIn("说法表·帮我把示例", x["why"])

    def test_multichar_trigger_exact_layer(self):
        """多字触发词「列表页」要靠整串精确层命中，两字组永远够不到精确档（bug 回归）。"""
        res = self.r.find("列表页")
        self.assertFalse(res["abstained"])
        self.assertEqual(res["hit"]["flow"], "爬虫")

    def test_not_for_penalizes(self):
        """含排除词的查询分数应低于不含排除词的同类查询。"""
        hit = self.r.find("抓取商品价格")
        blocked = self.r.find("数据库索引优化抓取")
        if blocked["ranked"]:
            self.assertLess(blocked["ranked"][0]["score"], hit["hit"]["score"])

    def test_not_for_is_one_directional(self):
        """排除条款单向 n in t：合法查询含排除词的父串时不得被误伤。"""
        # 「数据库」⊃「数据」：爬虫的合法查询含「数据」不应被打折（数据不是排除词，
        # 但「索引优化」是）——本用例锁单向行为本身
        res = self.r.find("把这个网站的数据抓下来")
        self.assertFalse(res["abstained"])

    def test_idf_monotone_in_df(self):
        """idf 随文档频率单调递减：出现越多篇，权重越低（防 filler 堆分的根性质）。"""
        r = flow_router.Router({"flows": [{"name": "a", "triggers": ["x1", "x2", "x3"],
                                           "doc": "common word alpha"},
                                          {"name": "b", "triggers": ["y1", "y2", "y3"],
                                           "doc": "common word beta"}],
                                "corpus_extra": ["common word gamma"]})
        # common 在 3 篇语料里都有，alpha/beta/gamma 各只在 1 篇
        self.assertLess(r.idf("common"), r.idf("alpha"))

    def test_gate_thresholds_respected(self):
        """双门都要生效：把门槛拉满后任何查询都应被拒。"""
        self.r.abstain_min, self.r.score_min = 1.0, 10**9
        self.assertTrue(self.r.find("我要抓一批新闻列表页")["abstained"])


class TestCjkBigrams(unittest.TestCase):
    def test_ascii_token_whole(self):
        self.assertIn("tcp", flow_router.cjk_bigrams("讲讲 TCP"))

    def test_cjk_bigram(self):
        self.assertIn("爬虫", flow_router.cjk_bigrams("爬虫工具"))

    def test_single_char_kept(self):
        self.assertIn("爬", flow_router.cjk_bigrams("爬"))

    def test_mixed(self):
        out = flow_router.cjk_bigrams("用spider抓数据")
        self.assertIn("spider", out)
        self.assertIn("抓数", out)


class TestLint(unittest.TestCase):
    def test_demo_config_passes(self):
        self.assertEqual(flow_router.cmd_lint(router()), 0)

    def test_duplicate_triggers_flagged(self):
        bad = flow_router.Router({"flows": [{"name": "a", "triggers": ["x", "x", "y"],
                                             "doc": "doc text here"}]})
        self.assertEqual(flow_router.cmd_lint(bad), 1)

    def test_not_for_conflict_flagged(self):
        bad = flow_router.Router({"flows": [{"name": "a", "triggers": ["x", "y", "z"],
                                             "not_for": ["x"], "doc": "doc"}]})
        self.assertEqual(flow_router.cmd_lint(bad), 1)


if __name__ == "__main__":
    unittest.main()
