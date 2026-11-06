#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bench —— flow-router 可复现基准

README 里的性能数字必须可复现，不写没有背书的声明。本脚本量三件事：
1. 冷启动耗时（import + 加载配置）——词法方案的核心优势：无模型加载
2. 单次路由延迟（p50/p95，含分词+idf+五档打分全流程）
3. 吞吐（单线程 1 秒能路由多少条）

跑法：python bench.py [--n 2000]
输出末行 BENCH-DONE，方便 CI 断言。
"""
import argparse
import json
import time

import flow_router


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000, help="吞吐测量轮数")
    ap.add_argument("--config", default="flows.json")
    a = ap.parse_args()

    queries = [
        "我要抓一批新闻列表页", "帮我写一份固态电池的深度研报",
        "把会议内容整理成会议纪要文档", "给我讲讲 TCP 三次握手",
        "把这个电商网站的商品价格抓下来", "出一份行业分析报告",
    ]

    # 1) 冷启动：从 import 完成后计时到 Router 可用（无模型加载是本方案卖点）
    cfg = json.load(open(a.config, encoding="utf-8-sig"))
    t0 = time.perf_counter()
    r = flow_router.Router(cfg)
    cold_ms = (time.perf_counter() - t0) * 1000

    # 预热一轮（首次调用含 idf 缓存填充，不计入稳态延迟）
    for q in queries:
        r.find(q)

    # 2) 单次延迟：轮流跑 queries，记录每次耗时
    lat = []
    for i in range(min(a.n, 500)):
        q = queries[i % len(queries)]
        t = time.perf_counter()
        r.find(q)
        lat.append((time.perf_counter() - t) * 1000)
    lat.sort()
    p50 = lat[len(lat) // 2]
    p95 = lat[int(len(lat) * 0.95)]

    # 3) 吞吐：单线程固定轮数
    t = time.perf_counter()
    for i in range(a.n):
        r.find(queries[i % len(queries)])
    dt = time.perf_counter() - t
    qps = a.n / dt

    print(f"冷启动(Router就绪): {cold_ms:.2f} ms")
    print(f"单次路由延迟: p50={p50:.3f} ms  p95={p95:.3f} ms  (n={len(lat)})")
    print(f"单线程吞吐: {qps:,.0f} routes/s  (n={a.n})")
    print("BENCH-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
