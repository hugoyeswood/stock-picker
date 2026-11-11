# -*- coding: utf-8 -*-
"""
盘中实时刷新 short_term_rec.json（在 GitHub Actions 里每 10 分钟跑一次）
- 只改数据，不重新构建页面
- 不依赖 AI，纯规则：价格/涨幅/换手 + 题材权重打分
- 现有推荐只要没涨停、没破位就保留，只更新实时价与止盈止损，避免频繁换股
"""
import json
import os
import sys
import urllib.request
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    TZ = None

REC_FILE = "short_term_rec.json"
QT = "https://qt.gtimg.cn/q="

# 候选池：低价（<=10元）、流动性合格、当日热门题材（AI应用/传媒/半导体/机器人/汽车链）
# 值 = 题材权重（用于打分；热门主线权重高）
POOL = {
    # AI应用 / 传媒 / 短剧
    "sz300459": ("汤姆猫", 1.15),
    "sz300315": ("掌趣科技", 1.15),
    "sh600986": ("浙文互联", 1.10),
    "sz002354": ("天娱数科", 1.10),
    "sz002400": ("省广集团", 1.05),
    "sz002131": ("利欧股份", 1.05),
    "sz300291": ("百纳千成", 1.10),
    "sh601599": ("浙文影业", 1.05),
    "sh600715": ("文投控股", 1.05),
    "sh600892": ("大晟文化", 1.00),
    "sz000782": ("恒申新材", 1.00),
    "sh603825": ("ST华扬", 0.90),
    # 半导体 / 消费电子 / 通信
    "sz002388": ("新亚制程", 1.10),
    "sz002313": ("日海智能", 1.10),
    "sz002632": ("道明光学", 1.00),
    "sz002324": ("普利特", 1.05),
    "sz002953": ("日丰股份", 1.00),
    "sz300349": ("金卡智能", 1.00),
    "sz002405": ("四维图新", 1.05),
    "sh603660": ("苏州科达", 1.05),
    # 机器人 / 汽车链 / 设备
    "sz002488": ("金固股份", 1.10),
    "sz002892": ("科力尔", 1.05),
    "sh603809": ("豪能股份", 1.05),
    "sz000541": ("佛山照明", 1.00),
    "sz002248": ("华东数控", 0.95),
    "sz002825": ("纳尔股份", 0.95),
    # 其他低位活跃
    "sh600609": ("金杯汽车", 1.00),
    "sh600829": ("人民同泰", 0.95),
    "sz002081": ("金螳螂", 0.95),
    "sh600278": ("东方创业", 0.95),
    "sz002086": ("东方海洋", 1.00),
    "sh600589": ("大位科技", 1.00),
    "sz002578": ("闽发铝业", 1.00),
}


def now_cn():
    if TZ is not None:
        return datetime.now(TZ)
    return datetime.utcnow()


def in_session(dt):
    if dt.weekday() >= 5:
        return False
    hm = dt.hour * 60 + dt.minute
    return (9 * 60 + 25 <= hm <= 11 * 60 + 35) or (12 * 60 + 55 <= hm <= 15 * 60 + 5)


def fetch_quotes(codes):
    out = {}
    codes = list(codes)
    for i in range(0, len(codes), 60):
        batch = codes[i:i + 60]
        url = QT + ",".join(batch)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
        raw = urllib.request.urlopen(req, timeout=15).read().decode("gbk", "ignore")
        for line in raw.split(";"):
            line = line.strip()
            if "~" not in line or "=" not in line:
                continue
            f = line.split("~")
            if len(f) < 45:
                continue
            try:
                code_full = line.split("=")[0].replace("v_", "").strip()
                price = float(f[3] or 0)
                prev = float(f[4] or 0)
                chg = float(f[32] or 0)
                high = float(f[33] or 0)
                low = float(f[34] or 0)
                turn = float(f[38] or 0)
                ts = f[30]
                if price <= 0:
                    continue
                out[code_full] = dict(name=f[1], price=price, prev=prev, chg=chg,
                                      high=high, low=low, turn=turn, ts=ts)
            except Exception:
                continue
    return out


def main():
    dt = now_cn()
    if not in_session(dt):
        print("非交易时段，跳过：%s" % dt.strftime("%Y-%m-%d %H:%M"))
        return

    today = dt.strftime("%Y-%m-%d")
    hhmm = dt.strftime("%H:%M")

    if not os.path.exists(REC_FILE):
        print("缺少 %s，退出" % REC_FILE)
        return
    with open(REC_FILE, encoding="utf-8") as fp:
        rec = json.load(fp)

    if rec.get("date") != today:
        print("JSON 日期 %s 非今日 %s，等待盘前首版，跳过" % (rec.get("date"), today))
        return

    quotes = fetch_quotes(POOL.keys())
    if not quotes:
        print("行情抓取失败，跳过")
        return

    old = rec.get("stocks") or []

    # 1) 现有推荐：未涨停且未破位则继续保留（保持推荐稳定性）
    keep = []
    for s in old:
        c = ("sh" if str(s["code"]).startswith("6") else "sz") + str(s["code"])
        q = quotes.get(c)
        if not q:
            keep.append(s)
            continue
        chg = q["chg"]
        if chg >= 9.6:          # 已涨停/接近封板 -> 让位给新的低位活跃股
            print("淘汰(涨停) %s %s %.2f%%" % (s["code"], s["name"], chg))
            continue
        if chg <= -3.0:         # 破位止损 -> 淘汰
            print("淘汰(破位) %s %s %.2f%%" % (s["code"], s["name"], chg))
            continue
        keep.append(s)

    # 2) 从候选池补充/换入
    used = {str(s["code"]) for s in keep}
    cand = []
    for c, (nm, w) in POOL.items():
        code = c[2:]
        if code in used:
            continue
        q = quotes.get(c)
        if not q:
            continue
        if q["price"] > 10.0 or q["price"] <= 0:
            continue
        if not (0.5 <= q["chg"] <= 9.0):
            continue
        if q["turn"] < 1.0 or q["turn"] > 30.0:
            continue
        if "ST" in q["name"] or "退" in q["name"]:
            continue
        score = (q["chg"] ** 1.1) * (q["turn"] ** 0.5) * w
        cand.append((score, code, q))
    cand.sort(reverse=True)

    stocks = []
    for s in keep:
        c = ("sh" if str(s["code"]).startswith("6") else "sz") + str(s["code"])
        q = quotes.get(c, {})
        price = q.get("price") or s["price"]
        stocks.append({
            "code": str(s["code"]), "name": s["name"],
            "price": round(price, 2),
            "chg": round(q.get("chg", s.get("chg", 0)), 2),
            "qty": s.get("qty", "1手（100股）"),
            "reason": s.get("reason", ""),
            "buy_range": "%.2f~%.2f" % (round(price * 0.99, 2), round(price * 1.03, 2)),
            "stop_loss": round(price * 0.95, 2),
            "take_profit": round(price * 1.10, 2),
            "seed": True,
        })

    for score, code, q in cand:
        if len(stocks) >= 3:
            break
        price = q["price"]
        lots = int(1000 // (price * 100))
        if lots < 1:
            continue
        nm, w = POOL[("sh" if code.startswith("6") else "sz") + code]
        hot = "主线题材" if w >= 1.1 else "活跃低位"
        stocks.append({
            "code": code, "name": q["name"],
            "price": round(price, 2),
            "chg": round(q["chg"], 2),
            "qty": "%d手（%d股）" % (lots, lots * 100),
            "reason": "✅ 可买理由：盘中实时筛出，%.2f元/%d元一手买得起，涨幅%.2f%%未涨停、换手%.2f%%资金活跃，属%s，短线仍有上冲空间。" % (
                price, int(price * 100), q["chg"], q["turn"], hot),
            "buy_range": "%.2f~%.2f" % (round(price * 0.99, 2), round(price * 1.03, 2)),
            "stop_loss": round(price * 0.95, 2),
            "take_profit": round(price * 1.10, 2),
            "seed": False,
        })

    if not stocks:
        print("无可用推荐，跳过写入")
        return

    rec["stocks"] = stocks
    rec["ts"] = hhmm
    rec["live_ts"] = dt.strftime("%H:%M:%S")
    if not rec.get("market_summary"):
        rec["market_summary"] = "盘中实时刷新，数据来源腾讯行情。"

    with open(REC_FILE, "w", encoding="utf-8") as fp:
        json.dump(rec, fp, ensure_ascii=False, indent=1)

    print("已刷新 %s" % rec["live_ts"])
    for s in stocks:
        print("  %s %s %.2f %+.2f%% %s 止盈%.2f 止损%.2f" % (
            s["code"], s["name"], s["price"], s["chg"], s["qty"], s["take_profit"], s["stop_loss"]))


if __name__ == "__main__":
    main()
