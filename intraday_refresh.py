# -*- coding: utf-8 -*-
"""
【盘中短线推荐·云端自主刷新】intraday_refresh.py
====================================================
由 GitHub Actions 定时调度（交易日 09:30 / 13:30），在云端自主运行：
  抓取A股全市场实时行情 -> 筛选「确保可买 + 短期增长潜力」短线股
  -> 更新仓库 hugoyeswood/stock-picker 的 short_term_rec.json
前端 PWA 每 15 分钟 fetch 该 JSON 自动刷新推荐目录，无需重新部署。

不依赖豆包定时任务，无额度限制，无需本地设备在线。
================================================================
"""
import os
import sys
import json
import base64
from datetime import datetime

import urllib.request

REPO = "hugoyeswood/stock-picker"
FILE = "short_term_rec.json"
API = f"https://api.github.com/repos/{REPO}/contents/{FILE}"
GH_TOKEN = os.environ.get("GH_TOKEN", "")
if not GH_TOKEN:
    print("FAIL: 未注入 GH_TOKEN，无法写入，停止（不降级其他仓库）")
    sys.exit(1)


def gh_get(path):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{path}",
                                 headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def gh_put(path, content, sha, message):
    body = json.dumps({"message": message, "content": content, "sha": sha}).encode("utf-8")
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{path}",
                                 data=body, headers={"Authorization": f"Bearer {GH_TOKEN}",
                                                      "Accept": "application/vnd.github+json",
                                                      "Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# 题材归类（关键词->热点标签），用于 reason 生成
THEMES = [
    ("AI", ["ai", "智能", "软件", "算力", "chatgpt", "kimi", "大模型", "数据要素", "云", "chatgpt"]),
    ("数字营销", ["营销", "广告", "传媒", "ip", "内容"]),
    ("游戏", ["游戏", "短剧", "动漫", "影视"]),
    ("券商金融", ["证券", "券商", "保险", "银行", "金融", "支付"]),
    ("新能源", ["锂", "电池", "光伏", "储能", "充电", "氢"]),
    ("消费", ["消费", "零售", "食品", "家电", "白酒", "家居"]),
    ("半导体", ["半导体", "芯片", "存储", "光通信", "pcb", "电子"]),
    ("医药", ["医药", "医疗", "生物", "疫苗", "创新药"]),
    ("军工", ["军工", "航天", "国防", "卫星"]),
    ("机器人", ["机器人", "减速器", "伺服", "工业母机"]),
    ("汽车", ["汽车", "整车", "汽配", "智能驾驶", "无人驾驶"]),
    ("房地产", ["房地产", "地产", "基建", "建材"]),
]


def theme_of(name):
    n = name.lower()
    for tag, keys in THEMES:
        for k in keys:
            if k in n:
                return tag
    return "题材"


def main():
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 读当前 JSON（保留 date/market_summary/note）
    try:
        cur = gh_get(FILE)
        old = json.loads(base64.b64decode(cur["content"]).decode("utf-8"))
        old_sha = cur["sha"]
    except Exception as e:
        print("FAIL: 读取当前 short_term_rec.json 失败:", e)
        sys.exit(1)

    if old.get("date") != today:
        print("SKIP: date 不是今天，等待每日 09:00 首版生成后本任务才生效")
        sys.exit(0)

    # 2. 抓取 A 股全市场实时行情（腾讯源，云端可用）
    try:
        import akshare as ak
        import pandas as pd
        df = ak.stock_zh_a_spot_tx()
        df = df.rename(columns={
            "zxj": "现价", "zdf": "今日涨跌%", "lb": "量比", "hsl": "换手率%",
            "zljlr": "主力净流入万", "name": "名称", "code": "代码",
        })
        num = ["现价", "今日涨跌%", "量比", "换手率%", "主力净流入万"]
        for c in num:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    except Exception as e:
        print("FAIL: 行情抓取失败（akshare/腾讯源）:", e)
        sys.exit(1)

    # 3. 筛选
    def 板块_可买(code):
        if code.startswith("sh6"):
            return True
        if code.startswith(("sz000", "sz001", "sz002", "sz003")):
            return True
        return False

    mask = (
        df["代码"].apply(板块_可买)
        & (~df["名称"].astype(str).str.contains("ST", na=False))
        & (df["现价"] >= 0.5)
        & (df["现价"] <= 10.0)
        & (df["今日涨跌%"] >= 0.5)
        & (df["今日涨跌%"] <= 9.0)
        & (df["量比"].fillna(0) >= 1.2)
        & (df["换手率%"].fillna(0) >= 1.0)
        & (df["主力净流入万"].fillna(0) > 0)
    )
    pool = df[mask].copy()
    if pool.empty:
        print("SKIP: 无符合筛选条件的候选（当前时段数据不满足，保留原推荐）")
        sys.exit(0)

    # 4. 评分：涨幅 × 量比 × 换手 × 资金流
    pool["评分"] = (
        pool["今日涨跌%"] * pool["量比"] * (pool["换手率%"] + 1) *
        (pool["主力净流入万"].clip(lower=0) / 10000 + 1)
    )
    top = pool.sort_values("评分", ascending=False).head(3)

    # 5. 组装 stocks
    stocks = []
    for _, r in top.iterrows():
        price = float(r["现价"])
        hands = int(1000 // (price * 100))
        if hands < 1:
            hands = 1
        chg = float(r["今日涨跌%"])
        lb = float(r["量比"])
        hsl = float(r["换手率%"])
        zl = float(r["主力净流入万"])
        th = theme_of(r["名称"])
        reason = (f"{th}短线活跃：今日+{chg:.2f}%放量、量比{lb:.2f}、换手{hsl:.2f}%、"
                  f"主力净流入{zl/10000:.2f}亿居前，价格{price:.2f}元资金占用小，涨幅温和不追高")
        sl = round(price * 0.95, 2)
        tp = round(price * 1.10, 2)
        stocks.append({
            "code": r["代码"],
            "name": r["名称"],
            "price": price,
            "chg": round(chg, 2),
            "qty": f"{hands}手（{hands*100}股）",
            "reason": reason,
            "buy_range": f"{sl}-{price:.2f}",
            "stop_loss": sl,
            "take_profit": tp,
        })

    # 6. 相同则跳过
    if stocks == old.get("stocks", []):
        print("SKIP: 新推荐与旧推荐完全相同，跳过写入")
        sys.exit(0)

    # 7. 组装新 JSON（保留 date/market_summary/note，更新 stocks 与 ts）
    new = dict(old)
    new["stocks"] = stocks
    new["ts"] = datetime.now().strftime("%H:%M")
    payload = json.dumps(new, ensure_ascii=False, indent=1).encode("utf-8")
    b64 = base64.b64encode(payload).decode("ascii")

    # 8. PUT 上传
    msg = f"盘中刷新 {today} {new['ts']}：更新短线推荐 {len(stocks)} 只"
    try:
        gh_put(FILE, b64, old_sha, msg)
    except Exception as e:
        print("FAIL: 写入仓库失败:", e)
        sys.exit(1)

    # 9. 回读验证
    try:
        ver = gh_get(FILE)
        ver_j = json.loads(base64.b64decode(ver["content"]).decode("utf-8"))
        if ver_j.get("ts") == new["ts"] and len(ver_j.get("stocks", [])) == len(stocks):
            print("OK: 已落盘验证通过")
            for s in stocks:
                print(f"  {s['name']}({s['code']}) ¥{s['price']} {s['chg']:+.2f}% {s['qty']} 止损{s['stop_loss']} 止盈{s['take_profit']}")
            print("更新时间:", ver_j.get("ts"))
        else:
            print("FAIL: 落盘验证不一致")
            sys.exit(1)
    except Exception as e:
        print("FAIL: 验证失败:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
