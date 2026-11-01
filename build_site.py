# -*- coding: utf-8 -*-
"""
【你的自动选股小助手】手机版 + 云端版 + 买卖点 + 资金账户  build_site.py
====================================================
每天自动：拉全市场数据 -> 筛选 -> 为候选算买卖点 -> 生成手机页面 index.html + 数据 data.json

功能：
  1. 资金账户：从 wallet.json 读取"当前可用资金"，按最新资金筛选"买得起的股"；
     想加钱用 add_fund.py（资金转入端口）。
  2. 买卖点：每只候选给出 该买/等回踩/观望 + 买入参考价/止损/止盈 +
     建议买入区间 + 追高风险提示 + 买入前确认清单。
  3. 安全：所有写入页面的文字都会做转义，防止网页注入问题。
     本工具不保存任何账号密码，只读公开免费行情。

数据源自动切换：腾讯 -> 东方财富 -> 新浪。
====================================================
"""
import akshare as ak
import pandas as pd
import json
import html
from datetime import datetime, timedelta

# ============ 1. 可调的"选股口味" ============
BUDGET_DEFAULT = 1000.0   # 没有资金账户文件时用的默认资金
TOP_N    = 20             # 每天最多推几只
MIN_PRICE = 0.5
MAX_PRICE = 10.0

# ============ 2. 读取资金账户 ============
def load_wallet():
    """从 wallet.json 读当前可用资金；文件不存在或出错时用默认值"""
    try:
        with open("wallet.json", encoding="utf-8") as f:
            w = json.load(f)
        return float(w.get("available", BUDGET_DEFAULT)), w.get("ledger", [])
    except Exception:
        return BUDGET_DEFAULT, []

WALLET_AMT, WALLET_LEDGER = load_wallet()
BUDGET = WALLET_AMT

# ============ 3. 多数据源自动切换 ============
def normalize(df, source):
    if source == "腾讯":
        ren = {"zxj":"price","zdf":"chg","zdf_d5":"chg5","zdf_d10":"chg10",
               "zdf_d20":"chg20","zdf_d60":"chg60","lb":"lb","hsl":"hsl",
               "pe_ttm":"pe","zljlr":"mflow","ltsz":"ltsz","stock_type":"stype"}
    elif source == "东财":
        ren = {"最新价":"price","涨跌幅":"chg","量比":"lb","换手率":"hsl",
               "市盈率-动态":"pe","总市值":"ltsz","股票代码":"code","股票简称":"name"}
    else:
        ren = {"最新价":"price","涨跌幅":"chg"}
    df = df.rename(columns=ren)
    for col in ["chg5","chg10","chg20","chg60","lb","hsl","pe","mflow","ltsz"]:
        if col not in df.columns:
            df[col] = float("nan")
    for col in ["price","chg","chg5","chg10","chg20","chg60","lb","hsl","pe","mflow","ltsz"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["source"] = source
    return df

def fetch_all():
    for source, fn in [("腾讯", ak.stock_zh_a_spot_tx),
                       ("东财", ak.stock_zh_a_spot_em),
                       ("新浪", ak.stock_zh_a_spot)]:
        try:
            df = fn()
            print(f"[数据源] 用 {source}")
            return normalize(df, source), source
        except Exception as e:
            print(f"[数据源] {source} 失败({str(e)[:50]})，换下一个...")
    raise RuntimeError("所有数据源都失败")

# ============ 4. 算买卖点（拉历史K线） ============
def calc_trade(code, price):
    """拉近250天历史，算均线/支撑，给出买卖点。失败返回带兜底信息的字典"""
    fallback = {"state": "未知", "advice": "历史数据暂缺，建议先看该股K线再决定",
                "buy_ref": round(price, 2), "stop_loss": None, "take_profit": None,
                "ma5": None, "ma20": None, "low20": None,
                "buy_low": round(price, 2), "buy_high": round(price, 2),
                "risk_note": "", "confirm": "历史数据暂缺，买入前请人工确认趋势"}
    try:
        end = datetime.now()
        start = end - timedelta(days=250)
        hist = ak.stock_zh_a_hist_tx(symbol=code,
                                     start_date=start.strftime("%Y%m%d"),
                                     end_date=end.strftime("%Y%m%d"),
                                     adjust="")
        if hist is None or hist.empty or price is None:
            return fallback
        close = pd.to_numeric(hist["close"], errors="coerce")
        low   = pd.to_numeric(hist["low"],  errors="coerce")
        high  = pd.to_numeric(hist["high"], errors="coerce")
        open_ = pd.to_numeric(hist["open"], errors="coerce")
        ma5  = close.tail(5).mean()
        ma20 = close.tail(20).mean()
        low20 = low.tail(20).min()
        if pd.isna(ma20):
            return fallback
        # 最近30天K线数据（用于画图）
        kline_data = []
        try:
            dates = hist["date"].tail(30).tolist()
            for i in range(len(dates)):
                kline_data.append({
                    "date": str(dates[i]),
                    "open": round(float(open_.iloc[-30+i]), 2) if i < len(open_) else None,
                    "close": round(float(close.iloc[-30+i]), 2) if i < len(close) else None,
                    "low": round(float(low.iloc[-30+i]), 2) if i < len(low) else None,
                    "high": round(float(high.iloc[-30+i]), 2) if i < len(high) else None,
                })
        except Exception:
            kline_data = []
        # 涨跌停价（A股主板±10%）
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else price
        limit_up = round(prev_close * 1.1, 2)
        limit_down = round(prev_close * 0.9, 2)
        # 状态
        if price >= ma20:
            dist = (price - ma5) / ma5 * 100 if (pd.notna(ma5) and ma5 > 0) else 0
            if dist <= 5:
                state = "可买"; advice = "趋势向上，可按参考区间买入1手"
            else:
                state = "等回踩"; advice = f"短线涨得急，等回踩到MA5(约{ma5:.2f}元)附近再买更稳"
        else:
            state = "观望"; advice = "现价在20日线下方，先观察，别急着追"
        # 建议买入区间：现价与MA5的较低者 ~ 现价（别高于现价追）
        buy_low = round(min(price, ma5), 2) if pd.notna(ma5) else round(price, 2)
        buy_high = round(price, 2)
        stop = round(price * 0.95, 2)
        take = round(price * 1.10, 2)
        # 风险提示
        risks = []
        up_from_low = (price - low20) / low20 * 100 if (pd.notna(low20) and low20 > 0) else 0
        if up_from_low > 30:
            risks.append(f"较近20日低点已涨{up_from_low:.0f}%，追高风险较大")
        above_ma20 = (price / ma20 - 1) * 100 if ma20 > 0 else 0
        if above_ma20 > 12:
            risks.append(f"现价已高出20日均线约{above_ma20:.0f}%，短线偏热")
        if stop and low20 and stop < low20:
            risks.append(f"止损价{stop}已低于近20日低点{low20:.2f}，注意破位风险")
        risk_note = "；".join(risks)
        # 买入前确认清单
        confirm = (f"买前确认：①资金够买1手 ②券商挂限价单，填在{buy_low}~{buy_high}元区间 "
                   f"③同时设好止损单{stop}元 ④每次只买1手、不满仓")
        return {
            "state": state, "advice": advice,
            "buy_ref": round(price, 2), "stop_loss": stop, "take_profit": take,
            "ma5": round(ma5, 2) if pd.notna(ma5) else None,
            "ma20": round(ma20, 2), "low20": round(low20, 2),
            "buy_low": buy_low, "buy_high": buy_high,
            "risk_note": risk_note, "confirm": confirm,
            "kline": kline_data,
            "limit_up": limit_up, "limit_down": limit_down,
        }
    except Exception:
        return fallback

print("正在拉取全市场行情（多数据源自动切换）...")
df, src = fetch_all()
print(f"已拿到全市场 {len(df)} 只股票（数据源:{src}，可用资金:¥{BUDGET:.2f}）")

# 提取全A股股票列表（用于前端本地搜索）
all_stocks = []
for _, row in df.iterrows():
    code = str(row.get("code", ""))
    name = str(row.get("name", ""))
    if code and name:
        all_stocks.append({"code": code, "name": name})
print(f"已提取 {len(all_stocks)} 只股票用于前端搜索")

# ============ 5. "能不能买"的过滤（资金约束优先） ============
def 板块_可买(code):
    code = str(code)
    if code.startswith("sh6"): return True
    if code.startswith(("sz000","sz001","sz002","sz003")): return True
    return False

mask = (
    df["code"].apply(板块_可买)
    & (~df.get("name", pd.Series(index=df.index)).fillna("").astype(str).str.contains("ST", na=False))
    & (df["price"] >= MIN_PRICE)
    & (df["price"] <= MAX_PRICE)
    & (df["lb"].fillna(0) > 0)
)
pool = df[mask].copy()
print(f"过滤后，当前资金买得起的沪深主板候选 {len(pool)} 只")

# ============ 6. 打分（缺数据的项自动不参与） ============
def 打分(r):
    s, why = 0, []
    if pd.notna(r["chg"]) and pd.notna(r["lb"]):
        if r["chg"] > 1.0 and r["lb"] > 1.2: s += 2; why.append("今日放量上涨")
        elif r["chg"] > 0: s += 1; why.append("今日上涨")
    if pd.notna(r["chg10"]) and r["chg10"] > 0: s += 1; why.append("近10日走强")
    if pd.notna(r["chg20"]) and r["chg20"] > 0: s += 1; why.append("近20日走强")
    if pd.notna(r["mflow"]) and r["mflow"] > 0: s += 1; why.append("主力资金流入")
    if pd.notna(r["hsl"]) and 1 <= r["hsl"] <= 10: s += 1; why.append("换手活跃")
    if pd.notna(r["pe"]) and 0 < r["pe"] < 60: s += 1; why.append("估值适中")
    return s, "、".join(why)

rows = pool.to_dict("records")
scored = []
for r in rows:
    s, why = 打分(r)
    if s >= 3:
        scored.append((s, r, why))
scored.sort(reverse=True, key=lambda x: x[0])
top = scored[:TOP_N]
print(f"达到信号门槛(≥3分)的有 {len(scored)} 只，取前 {TOP_N} 只")

# ============ 6.5 涨停预测（专门筛选当日涨停潜力股） ============
def 涨停预测分(r):
    """计算涨停潜力分数"""
    s, reasons = 0, []
    # 当天涨幅3%-9%（还没涨停，但已经有涨幅）
    if pd.notna(r["chg"]):
        if 3 <= r["chg"] <= 9:
            s += 3; reasons.append(f"今日已涨{r['chg']:.1f}%，有冲涨停动力")
        elif 1 <= r["chg"] < 3:
            s += 1; reasons.append(f"今日小涨{r['chg']:.1f}%，蓄势中")
    # 量比放大（>1.5说明资金涌入）
    if pd.notna(r["lb"]) and r["lb"] > 1.5:
        s += 2; reasons.append(f"量比{r['lb']:.1f}，资金明显涌入")
    # 换手率活跃（2%-10%）
    if pd.notna(r["hsl"]) and 2 <= r["hsl"] <= 10:
        s += 1; reasons.append(f"换手{r['hsl']:.1f}%，交投活跃")
    # 主力资金流入
    if pd.notna(r["mflow"]) and r["mflow"] > 0:
        s += 1; reasons.append("主力资金净流入")
    # 近期走势强势
    if pd.notna(r["chg5"]) and r["chg5"] > 0:
        s += 1; reasons.append(f"近5日涨{r['chg5']:.1f}%，趋势向上")
    if pd.notna(r["chg10"]) and r["chg10"] > 0:
        s += 1; reasons.append(f"近10日涨{r['chg10']:.1f}%，中期走强")
    # 价格在合理区间（5-30元，更容易拉涨停）
    if pd.notna(r["price"]) and 5 <= r["price"] <= 30:
        s += 1; reasons.append(f"股价{r['price']:.1f}元，盘子适中易拉升")
    return s, reasons

limit_up_candidates = []
for r in rows:
    s, reasons = 涨停预测分(r)
    if s >= 5:  # 涨停潜力分≥5分
        limit_up_candidates.append((s, r, reasons))
limit_up_candidates.sort(reverse=True, key=lambda x: x[0])
limit_up_top = limit_up_candidates[:5]  # 取前5只
print(f"涨停预测：找到 {len(limit_up_candidates)} 只潜力股，取前 {len(limit_up_top)} 只")

# ============ 7. 组装结果（含买卖点） ============
print("正在逐只拉历史K线算买卖点（约半分钟）...")
out = []
for s, r, why in top:
    price = r["price"]
    hands = int(BUDGET // (price * 100))
    trade = calc_trade(r["code"], price)
    out.append({
        "code": str(r["code"]), "name": str(r.get("name", "")),
        "price": round(price, 2),
        "chg": round(r["chg"], 2) if pd.notna(r["chg"]) else None,
        "chg5": round(r["chg5"], 2) if pd.notna(r["chg5"]) else None,
        "chg10": round(r["chg10"], 2) if pd.notna(r["chg10"]) else None,
        "chg20": round(r["chg20"], 2) if pd.notna(r["chg20"]) else None,
        "lb": round(r["lb"], 2) if pd.notna(r["lb"]) else None,
        "hsl": round(r["hsl"], 2) if pd.notna(r["hsl"]) else None,
        "pe": round(r["pe"], 2) if pd.notna(r["pe"]) else None,
        "score": s, "why": why,
        "hands": hands, "cost": int(hands * price * 100),
        "trade": trade,
    })

# ============ 7.5 组装涨停预测结果 ============
limit_up_out = []
for s, r, reasons in limit_up_top:
    price = r["price"]
    limit_up_out.append({
        "code": str(r["code"]), "name": str(r.get("name", "")),
        "price": round(price, 2),
        "chg": round(r["chg"], 2) if pd.notna(r["chg"]) else None,
        "lb": round(r["lb"], 2) if pd.notna(r["lb"]) else None,
        "hsl": round(r["hsl"], 2) if pd.notna(r["hsl"]) else None,
        "score": s, "reasons": reasons,
    })

now = datetime.now().strftime("%Y-%m-%d %H:%M")

# 保存数据备份 data.json
with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"updated": now, "source": src, "budget": BUDGET,
               "count": len(out), "candidates": out,
               "limit_up_picks": limit_up_out}, f, ensure_ascii=False, indent=2)

# ============ 8. 生成手机友好页面 index.html ============
def esc(x):
    """把所有写入页面的文字转义，防止注入/乱码"""
    return html.escape(str(x), quote=True)

def fmt_pct(v):
    return "--" if v is None else f"{v:+.2f}%"
def color(v):
    if v is None or v == 0: return "#666"
    return "#d32f2f" if v > 0 else "#2e7d32"   # A股习惯：红涨绿跌

STATE_STYLE = {"可买": ("#e8f5e9", "#2e7d32"), "等回踩": ("#fff3e0", "#e65100"),
               "观望": ("#eeeeee", "#616161"), "未知": ("#eeeeee", "#616161")}

cards = ""
for r in out:
    t = r["trade"]
    bg, fg = STATE_STYLE.get(t["state"], STATE_STYLE["未知"])
    c_chg = color(r["chg"])
    chg5 = f"5日 {fmt_pct(r['chg5'])}" if r["chg5"] is not None else "5日 --"
    chg10 = f"10日 {fmt_pct(r['chg10'])}" if r["chg10"] is not None else "10日 --"
    chg20 = f"20日 {fmt_pct(r['chg20'])}" if r["chg20"] is not None else "20日 --"
    stop = f"¥{t['stop_loss']:.2f}" if t.get("stop_loss") else "--"
    take = f"¥{t['take_profit']:.2f}" if t.get("take_profit") else "--"
    risk_html = f'<div class="t-risk">⚠ {esc(t["risk_note"])}</div>' if t.get("risk_note") else ""
    cards += f"""
    <div class="card">
      <div class="card-top">
        <div><div class="name">{esc(r['name'])}</div><div class="code">{esc(r['code'])}</div></div>
        <div><span class="score">{r['score']}分</span>
             <span class="state" style="background:{bg};color:{fg}">{esc(t['state'])}</span></div>
      </div>
      <div class="price-line">
        <span class="price" data-code="{esc(r['code'])}">¥{r['price']:.2f}</span>
        <span class="chg" data-code="{esc(r['code'])}" style="color:{c_chg}">{fmt_pct(r['chg'])}</span>
      </div>
      <div class="limit-row">
        <span class="limit-up">涨停 ¥{t.get('limit_up', '--')}</span>
        <span class="limit-down">跌停 ¥{t.get('limit_down', '--')}</span>
      </div>
      <div class="tags">
        <span class="tag" style="color:{color(r['chg5'])}">{chg5}</span>
        <span class="tag" style="color:{color(r['chg10'])}">{chg10}</span>
        <span class="tag" style="color:{color(r['chg20'])}">{chg20}</span>
      </div>
      <div class="meta">量比 {r['lb'] if r['lb'] is not None else '--'} · 换手 {r['hsl'] if r['hsl'] is not None else '--'}% · 市盈率 {r['pe'] if r['pe'] is not None else '--'}</div>
      <div class="trade" style="background:{bg}">
        <div class="t-advice">{esc(t['advice'])}</div>
        <div class="t-row">买入参考 <b>¥{r['price']:.2f}</b> · 止损 <b>{stop}</b> · 止盈 <b>{take}</b></div>
        <div class="t-range">建议买入区间 <b>¥{t['buy_low']:.2f} ~ ¥{t['buy_high']:.2f}</b>（区间内挂单更稳，别高于现价追）</div>
        {risk_html}
        <div class="t-confirm">{esc(t['confirm'])}</div>
      </div>
      <div class="why">{esc(r['why'])}</div>
      <div class="hands">你的 ¥{BUDGET:.0f} 可买 <b>{r['hands']}手</b>（约{r['cost']}元，一手=100股）</div>
      <div>
        <button class="trade-btn btn-buy" onclick="recordTrade('buy','{esc(r['code'])}','{esc(r['name'])}',{r['price']})">记录买入</button>
        <button class="trade-btn btn-sell" onclick="recordTrade('sell','{esc(r['code'])}','{esc(r['name'])}',{r['price']})">记录卖出</button>
        <button class="trade-btn btn-chart" onclick="toggleChart('chart_{esc(r['code'])}')">K线图</button>
      </div>
      <div id="chart_{esc(r['code'])}" class="chart-container" style="display:none;">
        <div class="chart-title">近30日K线</div>
        <canvas id="canvas_{esc(r['code'])}" width="600" height="200"></canvas>
        <script type="application/json" id="data_{esc(r['code'])}">{json.dumps(t.get('kline', []), ensure_ascii=False)}</script>
      </div>
    </div>"""

wallet_rows = ""
for item in WALLET_LEDGER[-5:][::-1]:
    note = esc(item.get("note", "")) or "—"
    wallet_rows += f'<div class="w-row"><span class="w-date">{esc(item.get("date",""))}</span>'
    wallet_rows += f'<span class="w-amt">+¥{item["amount"]:.2f}</span><span class="w-note">{note}</span></div>'
wallet_html = f"""
<div class="card wallet">
  <div class="card-top"><div class="name">资金账户</div>
    <div class="w-total">当前可用 <b>¥{BUDGET:.2f}</b> <button onclick="editBudget()" style="margin-left:8px;font-size:12px;padding:3px 10px;background:#1a237e;color:#fff;border:none;border-radius:4px;cursor:pointer;">编辑</button></div></div>
  <div class="w-rows">{wallet_rows}</div>
  <div class="w-hint">点"编辑"可直接修改可用资金，数据保存在本地。</div>
  <div class="trades">
    <h3>📋 我的交易记录</h3>
    <div id="tradeList"><div style="font-size:12px;color:#999;">还没有交易记录，点下面的按钮开始记录</div></div>
  </div>
</div>"""

html_doc = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1a237e">
<link rel="manifest" href="manifest.json">
<link rel="icon" href="icons/icon-192.png" sizes="192x192">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<title>今日候选清单</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:"Microsoft YaHei", system-ui, sans-serif; background:#f0f2f5;
         max-width:640px; margin:0 auto; padding:14px; }}
  h1 {{ font-size:20px; color:#1a237e; margin-bottom:4px; }}
  .sub {{ font-size:12px; color:#777; margin-bottom:12px; }}
  .tip {{ background:#fff8e1; border-left:4px solid #f9a825; border-radius:6px;
         padding:10px 12px; font-size:13px; color:#5d4a00; margin-bottom:14px; }}
  .stat {{ display:flex; gap:8px; margin-bottom:14px; }}
  .stat div {{ flex:1; background:#fff; border-radius:8px; padding:10px; text-align:center;
              box-shadow:0 1px 3px rgba(0,0,0,.06); }}
  .stat b {{ display:block; font-size:20px; color:#1a237e; }}
  .stat span {{ font-size:11px; color:#888; }}
  .card {{ background:#fff; border-radius:12px; padding:14px; margin-bottom:12px;
          box-shadow:0 1px 4px rgba(0,0,0,.07); }}
  .card-top {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .name {{ font-size:17px; font-weight:bold; }}
  .code {{ font-size:11px; color:#999; }}
  .score {{ background:#c62828; color:#fff; border-radius:14px; padding:3px 10px;
           font-weight:bold; font-size:14px; }}
  .state {{ margin-left:6px; border-radius:14px; padding:3px 10px; font-weight:bold; font-size:13px; }}
  .price-line {{ margin:10px 0 6px; display:flex; align-items:baseline; gap:10px; }}
  .price {{ font-size:26px; font-weight:bold; }}
  .chg {{ font-size:16px; font-weight:bold; }}
  .tags {{ display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap; }}
  .tag {{ font-size:12px; background:#f5f5f5; border-radius:10px; padding:3px 8px; }}
  .meta {{ font-size:12px; color:#666; margin-bottom:8px; }}
  .trade {{ border-radius:8px; padding:8px 10px; margin-bottom:8px; }}
  .t-advice {{ font-size:13px; font-weight:bold; margin-bottom:4px; }}
  .t-row {{ font-size:13px; margin-bottom:4px; }}
  .t-range {{ font-size:13px; margin-bottom:4px; }}
  .t-risk {{ font-size:13px; color:#c62828; background:#ffebee; border-radius:6px;
            padding:5px 8px; margin:6px 0; }}
  .t-confirm {{ font-size:12px; color:#555; background:rgba(255,255,255,.6); border-radius:6px;
               padding:5px 8px; }}
  .why {{ font-size:13px; color:#333; line-height:1.5; margin-bottom:8px; }}
  .hands {{ font-size:13px; color:#1a237e; background:#e8eaf6; border-radius:8px; padding:7px 10px; }}
  .wallet {{ background:#fbfdff; border:1px solid #dbe4f7; }}
  .w-total b {{ font-size:18px; color:#1a237e; }}
  .w-row {{ display:flex; gap:8px; font-size:13px; padding:3px 0; color:#444; }}
  .w-date {{ color:#888; width:120px; }}
  .w-amt {{ font-weight:bold; color:#2e7d32; }}
  .w-note {{ color:#666; flex:1; }}
  .w-hint {{ font-size:12px; color:#888; margin-top:6px; }}
  .trade-btn {{ display:inline-block; margin:6px 6px 0 0; padding:7px 16px; border-radius:8px;
               border:none; font-size:13px; font-weight:bold; cursor:pointer; }}
  .btn-buy {{ background:#c62828; color:#fff; }}
  .btn-sell {{ background:#2e7d32; color:#fff; }}
  .trades {{ margin-top:10px; border-top:1px solid #eee; padding-top:10px; }}
  .trades h3 {{ font-size:14px; color:#1a237e; margin-bottom:6px; }}
  .trade-item {{ font-size:12px; padding:5px 0; border-bottom:1px dashed #eee; color:#444; }}
  .pnl-pos {{ color:#c62828; font-weight:bold; }}
  .pnl-neg {{ color:#2e7d32; font-weight:bold; }}
  .limit-row {{ display:flex; gap:12px; font-size:12px; margin:4px 0 8px; }}
  .limit-up {{ color:#c62828; background:#ffebee; padding:2px 8px; border-radius:4px; }}
  .limit-down {{ color:#2e7d32; background:#e8f5e9; padding:2px 8px; border-radius:4px; }}
  .btn-chart {{ background:#1a237e; color:#fff; }}
  .chart-container {{ margin-top:10px; border:1px solid #eee; border-radius:8px; padding:8px; background:#fafafa; }}
  .chart-title {{ font-size:12px; color:#666; margin-bottom:4px; }}
  .chart-container canvas {{ width:100%; height:200px; }}
  .search-box {{ margin:10px 0; display:flex; gap:8px; }}
  .search-box input {{ flex:1; padding:10px 14px; border:1px solid #ddd; border-radius:8px; font-size:14px; box-sizing:border-box; }}
  .search-box input:focus {{ outline:none; border-color:#1a237e; }}
  .search-box button {{ padding:10px 20px; background:#1a237e; color:#fff; border:none; border-radius:8px; font-size:14px; cursor:pointer; }}
  .search-box button:active {{ background:#283593; }}
  .foot {{ font-size:11px; color:#999; text-align:center; margin-top:16px; line-height:1.6; }}
</style></head><body>
<h1>今日候选清单</h1>
<div class="sub">数据更新于 {now} · 当前时间：<span id="currentTime"></span> · 数据源：{esc(src)} · 当前可用资金 ¥{BUDGET:.2f}</div>

<!-- 大盘指数 -->
<div style="margin:10px 0;padding:10px;background:#f5f5f5;border-radius:8px;display:flex;justify-content:space-around;text-align:center;">
  <div>
    <div style="font-size:12px;color:#666;">上证指数</div>
    <div id="shIndex" style="font-size:16px;font-weight:bold;">--</div>
  </div>
  <div>
    <div style="font-size:12px;color:#666;">深证成指</div>
    <div id="szIndex" style="font-size:16px;font-weight:bold;">--</div>
  </div>
  <div>
    <div style="font-size:12px;color:#666;">创业板指</div>
    <div id="cyIndex" style="font-size:16px;font-weight:bold;">--</div>
  </div>
</div>

<!-- 新手引导（3步） -->
<div class="tip" style="background:#e3f2fd;border-left:4px solid #1976d2;">
  <b>📱 新手3步上手：</b><br>
  ① 看下面推荐的股票，"✅可买"的可以考虑买入<br>
  ② 点"记录买入"，输入实际成交价格<br>
  ③ 系统自动帮你盯止盈止损，到点提醒你<br>
  <span style="color:#d32f2f;font-size:12px;">⚠️ 新手提醒：先小钱练手，别重仓！</span>
</div>

<!-- 今日涨停预计 -->
<div style="margin:14px 0;padding:14px;background:linear-gradient(135deg,#ff6b6b,#ee5a24);border-radius:12px;color:#fff;">
  <div style="font-size:16px;font-weight:bold;margin-bottom:10px;">🔥 今日涨停预计（短线潜力股）</div>
  <div style="font-size:12px;opacity:0.9;margin-bottom:10px;">以下是根据资金面、技术面筛选的今日涨停潜力股，仅供参考，不构成投资建议</div>
  {''.join(f'''
  <div style="background:rgba(255,255,255,0.15);border-radius:8px;padding:10px;margin-bottom:8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <div><b>{esc(r['name'])}</b> <span style="font-size:11px;opacity:0.8;">{esc(r['code'])}</span></div>
      <div style="text-align:right;">
        <div style="font-size:18px;font-weight:bold;">¥{r['price']:.2f}</div>
        <div style="font-size:12px;">{fmt_pct(r['chg'])}</div>
      </div>
    </div>
    <div style="font-size:11px;margin-top:6px;opacity:0.95;">
      <b>推荐理由：</b><br>
      {''.join('· ' + esc(reason) + '<br>' for reason in r['reasons'])}
    </div>
    <div style="margin-top:6px;font-size:11px;opacity:0.8;">
      量比 {r['lb'] if r['lb'] else '--'} · 换手 {r['hsl'] if r['hsl'] else '--'}% · 涨停潜力分 {r['score']}分
    </div>
  </div>
  ''' for r in limit_up_out)}
  <div style="font-size:11px;opacity:0.8;text-align:center;margin-top:6px;">⚠️ 涨停预测仅供参考，实际走势受多种因素影响，注意风险</div>
</div>

<div class="search-box">
  <input type="text" id="searchInput" placeholder="输入股票代码或名称..." onkeydown="if(event.key==='Enter')searchStocks()">
  <button onclick="searchStocks()">🔍 搜索</button>
</div>
<div class="stat">
  <div><b>{len(out)}</b><span>今日候选</span></div>
  <div><b>{len(pool)}</b><span>买得起的候选</span></div>
  <div><b>{sum(1 for x in out if x['trade']['state']=='可买')}</b><span>"可买"数量</span></div>
</div>
{wallet_html}
<div id="stockCards">
{cards}
</div>

<!-- 新手常见问题 -->
<div style="margin:20px 0;padding:14px;background:#fff3e0;border-radius:8px;">
  <div style="font-weight:bold;margin-bottom:8px;">❓ 新手常见问题</div>
  <div style="font-size:13px;line-height:1.8;">
    <b>Q：怎么添加到手机桌面？</b><br>
    A：手机浏览器打开本页 → 菜单 → "添加到主屏幕"，就像App一样用。<br><br>
    <b>Q：交易记录存在哪？</b><br>
    A：存在你手机本地（浏览器缓存），不会上传到服务器。<br><br>
    <b>Q：怎么清空记录重新开始？</b><br>
    A：点下面的"清空所有记录"按钮。<br><br>
    <button onclick="clearAllData()" style="margin-top:8px;padding:8px 16px;background:#f44336;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;">🗑️ 清空所有记录</button>
  </div>
</div>

<div class="foot">状态依据：现价 vs 20日均线、离5日均线远近；买入区间=现价与MA5之间。<br>
⚠️ 本工具仅为数据筛选参考，不构成投资建议。股市有风险，入市需谨慎。</div>
<script>
if ('serviceWorker' in navigator) {{ navigator.serviceWorker.register('./service-worker.js'); }}

// 清空所有数据
function clearAllData() {{
  if (!confirm('确定要清空所有交易记录和资金设置吗？此操作不可恢复！')) return;
  localStorage.removeItem('myTrades');
  localStorage.removeItem('myBudget');
  alert('已清空所有记录！');
  location.reload();
}}

// 实时更新当前时间
function updateCurrentTime() {{
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const seconds = String(now.getSeconds()).padStart(2, '0');
  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
  const weekday = weekdays[now.getDay()];
  const timeStr = `${{year}}-${{month}}-${{day}} ${{weekday}} ${{hours}}:${{minutes}}:${{seconds}}`;
  document.getElementById('currentTime').textContent = timeStr;
}}
updateCurrentTime();
setInterval(updateCurrentTime, 1000);

// 获取大盘指数（JSONP方式）
function fetchMarketIndex() {{
  const script = document.createElement('script');
  script.src = 'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006';
  script.onload = () => {{
    try {{
      // 上证指数
      if (typeof v_sh000001 !== 'undefined') {{
        const parts = v_sh000001.split('~');
        const price = parseFloat(parts[3]);
        const chg = parseFloat(parts[32]);
        if (price) {{
          document.getElementById('shIndex').textContent = price.toFixed(2);
          document.getElementById('shIndex').style.color = chg >= 0 ? '#d32f2f' : '#2e7d32';
        }}
      }}
      // 深证成指
      if (typeof v_sz399001 !== 'undefined') {{
        const parts = v_sz399001.split('~');
        const price = parseFloat(parts[3]);
        const chg = parseFloat(parts[32]);
        if (price) {{
          document.getElementById('szIndex').textContent = price.toFixed(2);
          document.getElementById('szIndex').style.color = chg >= 0 ? '#d32f2f' : '#2e7d32';
        }}
      }}
      // 创业板指
      if (typeof v_sz399006 !== 'undefined') {{
        const parts = v_sz399006.split('~');
        const price = parseFloat(parts[3]);
        const chg = parseFloat(parts[32]);
        if (price) {{
          document.getElementById('cyIndex').textContent = price.toFixed(2);
          document.getElementById('cyIndex').style.color = chg >= 0 ? '#d32f2f' : '#2e7d32';
        }}
      }}
    }} catch(e) {{
      console.log('大盘指数解析失败', e);
    }}
    document.body.removeChild(script);
  }};
  script.onerror = () => {{
    document.body.removeChild(script);
  }};
  document.body.appendChild(script);
}}
fetchMarketIndex();
setInterval(fetchMarketIndex, 10000); // 每10秒刷新一次

// JSONP辅助函数（绕过CORS跨域限制）
function jsonp(url, callbackName) {{
  return new Promise((resolve, reject) => {{
    const script = document.createElement('script');
    // 创建全局回调函数
    window[callbackName] = (data) => {{
      resolve(data);
      // 清理
      delete window[callbackName];
      document.body.removeChild(script);
    }};
    script.src = url;
    script.onerror = () => {{
      reject(new Error('JSONP请求失败'));
      document.body.removeChild(script);
    }};
    document.body.appendChild(script);
  }});
}}

// 搜索股票功能（从当前页面股票列表过滤）
function searchStocks() {{
  const keyword = document.getElementById('searchInput').value.trim().toLowerCase();
  
  // 从当前页面的股票卡片搜索
  const cards = document.querySelectorAll('#stockCards .card');
  let matchCount = 0;
  cards.forEach(card => {{
    const name = card.querySelector('.name')?.textContent.toLowerCase() || '';
    const code = card.querySelector('.code')?.textContent.toLowerCase() || '';
    if (!keyword || name.includes(keyword) || code.includes(keyword)) {{
      card.style.display = '';
      matchCount++;
    }} else {{
      card.style.display = 'none';
    }}
  }});
  
  // 隐藏搜索结果下拉框
  const searchResult = document.getElementById('searchResult');
  if (searchResult) searchResult.style.display = 'none';
  
  // 提示搜索结果数量
  if (keyword) {{
    alert('搜索到 ' + matchCount + ' 只匹配的股票');
  }}
}}

function showSearchResult(results) {{
  let div = document.getElementById('searchResult');
  const searchBox = document.querySelector('.search-box');
  if (!div) {{
    div = document.createElement('div');
    div.id = 'searchResult';
    // 下拉框样式：紧贴搜索框下方，绝对定位
    div.style.cssText = 'position:absolute;left:0;right:0;top:100%;margin-top:4px;border:1px solid #ddd;border-radius:8px;background:#fff;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1);z-index:1000;max-height:300px;overflow-y:auto;';
    // 让搜索框相对定位
    searchBox.style.position = 'relative';
    searchBox.appendChild(div);
  }}
  if (!results.length) {{
    div.style.display = 'none';
    return;
  }}
  div.style.display = 'block';
  let html = '';
  results.forEach((r, idx) => {{
    html += '<div onclick="showStockDetail(\'' + r.code + '\',\'' + r.name + '\')" style="padding:10px 14px;border-bottom:1px solid #f0f0f0;cursor:pointer;display:flex;justify-content:space-between;align-items:center;" onmouseover="this.style.background=\'#e3f2fd\'" onmouseout="this.style.background=\'\'">';
    html += '<span><b style="color:#1a237e;">' + r.name + '</b></span>';
    html += '<span style="color:#666;font-size:12px;background:#f5f5f5;padding:2px 8px;border-radius:4px;">' + r.code + '</span>';
    html += '</div>';
  }});
  div.innerHTML = html;
}}

// 点击页面其他地方时关闭搜索结果
document.addEventListener('click', function(e) {{
  const searchBox = document.querySelector('.search-box');
  const searchResult = document.getElementById('searchResult');
  if (searchResult && !searchBox.contains(e.target)) {{
    searchResult.style.display = 'none';
  }}
}});

// 显示股票详细行情
async function showStockDetail(code, name) {{
  try {{
    const resp = await fetch('https://qt.gtimg.cn/q=' + code);
    const text = await resp.text();
    const parts = text.split('~');
    if (parts.length < 35) return;
    const price = parseFloat(parts[3]);
    const chg = parseFloat(parts[32]);
    const open = parseFloat(parts[5]);
    const high = parseFloat(parts[33]);
    const low = parseFloat(parts[34]);
    const prevClose = parseFloat(parts[4]);
    const limitUp = (prevClose * 1.1).toFixed(2);
    const limitDown = (prevClose * 0.9).toFixed(2);
    
    // 弹出详情
    const chgColor = chg >= 0 ? '#c62828' : '#2e7d32';
    const html = 
      '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:999;display:flex;align-items:center;justify-content:center;">' +
      '<div style="background:#fff;border-radius:12px;padding:20px;width:90%;max-width:400px;max-height:80vh;overflow-y:auto;">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">' +
      '<div><h2 style="margin:0;font-size:18px;">' + name + '</h2>' +
      '<div style="color:#666;font-size:12px;">' + code + '</div></div>' +
      '<button onclick="closeStockDetail()" style="background:#eee;border:none;border-radius:50%;width:32px;height:32px;cursor:pointer;font-size:16px;">×</button>' +
      '</div>' +
      '<div style="text-align:center;margin:20px 0;">' +
      '<div style="font-size:36px;font-weight:bold;color:' + chgColor + ';">¥' + price.toFixed(2) + '</div>' +
      '<div style="color:' + chgColor + ';font-size:16px;">' + (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%</div>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:13px;">' +
      '<div>今开：¥' + open.toFixed(2) + '</div>' +
      '<div>昨收：¥' + prevClose.toFixed(2) + '</div>' +
      '<div>最高：¥' + high.toFixed(2) + '</div>' +
      '<div>最低：¥' + low.toFixed(2) + '</div>' +
      '<div style="color:#c62828;">涨停：¥' + limitUp + '</div>' +
      '<div style="color:#2e7d32;">跌停：¥' + limitDown + '</div>' +
      '</div>' +
      '<div style="margin-top:20px;display:flex;gap:10px;">' +
      '<button onclick="recordTrade(\'buy\',\'' + code + '\',\'' + name + '\',' + price + ')" style="flex:1;padding:12px;background:#c62828;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;">记录买入</button>' +
      '<button onclick="recordTrade(\'sell\',\'' + code + '\',\'' + name + '\',' + price + ')" style="flex:1;padding:12px;background:#2e7d32;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;">记录卖出</button>' +
      '</div>' +
      '</div></div>';
    
    let div = document.getElementById('stockDetailModal');
    if (!div) {{
      div = document.createElement('div');
      div.id = 'stockDetailModal';
      document.body.appendChild(div);
    }}
    div.innerHTML = html;
    div.style.display = 'block';
  }} catch(e) {{
    alert('获取行情失败，请重试');
  }}
}}

function closeStockDetail() {{
  const div = document.getElementById('stockDetailModal');
  if (div) div.style.display = 'none';
}}

// 交易记录功能（存在手机本地）
function getTrades() {{
  try {{ return JSON.parse(localStorage.getItem('myTrades') || '[]'); }}
  catch(e) {{ return []; }}
}}
function saveTrades(t) {{
  localStorage.setItem('myTrades', JSON.stringify(t));
  renderTrades();
}}
// 计算交易费用
function calcFee(amount, type) {{
  const commission = Math.max(amount * 0.00025, 5); // 佣金万2.5，最低5元
  const transfer = amount * 0.00002; // 过户费万0.2
  let stamp = 0;
  if (type === 'sell') stamp = amount * 0.001; // 印花税千1，卖出收
  return commission + transfer + stamp;
}}

function recordTrade(type, code, name, price) {{
  const priceInput = prompt('请输入实际成交价格（元）：', price);
  if (!priceInput || isNaN(priceInput) || priceInput <= 0) return;
  const qtyInput = prompt('请输入数量（股），1手=100股：', '100');
  if (!qtyInput || isNaN(qtyInput) || qtyInput <= 0) return;
  const actualPrice = parseFloat(priceInput);
  const qty = parseInt(qtyInput);
  const amount = actualPrice * qty;
  const fee = calcFee(amount, type);
  const trades = getTrades();
  trades.push({{
    type: type, code: code, name: name,
    price: actualPrice, qty: qty,
    amount: amount, fee: fee,
    time: new Date().toLocaleString('zh-CN')
  }});
  saveTrades(trades);
  alert((type === 'buy' ? '买入' : '卖出') + '记录成功：\n' +
    name + ' ' + qty + '股 @ ¥' + actualPrice.toFixed(2) + '\n' +
    '成交金额：¥' + amount.toFixed(2) + '\n' +
    '交易费用：¥' + fee.toFixed(2) + '\n' +
    '实际支出：¥' + (amount + fee).toFixed(2));
}}
function renderTrades() {{
  const trades = getTrades();
  const list = document.getElementById('tradeList');
  if (!trades.length) {{
    list.innerHTML = '<div style="font-size:12px;color:#999;">还没有交易记录，点下面的按钮开始记录</div>';
    return;
  }}
  // 计算持仓和盈亏
  const positions = {{}};
  trades.forEach(t => {{
    if (!positions[t.code]) positions[t.code] = {{ name: t.name, buyQty: 0, buyCost: 0, sellQty: 0, sellRevenue: 0 }};
    if (t.type === 'buy') {{ positions[t.code].buyQty += t.qty; positions[t.code].buyCost += t.price * t.qty; }}
    else {{ positions[t.code].sellQty += t.qty; positions[t.code].sellRevenue += t.price * t.qty; }}
  }});
  let html = '';
  let totalPnl = 0;
  Object.values(positions).forEach(p => {{
    const holdQty = p.buyQty - p.sellQty;
    const avgCost = p.buyQty > 0 ? (p.buyCost / p.buyQty) : 0;
    const realizedPnl = p.sellRevenue - (p.sellQty * avgCost);
    totalPnl += realizedPnl;
    const pnlClass = realizedPnl >= 0 ? 'pnl-pos' : 'pnl-neg';
    const pnlSign = realizedPnl >= 0 ? '+' : '';
    html += '<div class="trade-item">';
    html += '<b>' + p.name + '</b>：持仓 ' + holdQty + '股，成本 ¥' + avgCost.toFixed(2);
    if (holdQty > 0) {{
      const takeProfit = avgCost * 1.15;
      const stopLoss = avgCost * 0.85;
      html += '<div style="margin-top:4px;font-size:12px;color:#666;">';
      html += '止盈(+15%)：<span style="color:#c62828;font-weight:bold;">¥' + takeProfit.toFixed(2) + '</span>';
      html += ' · 止损(-15%)：<span style="color:#2e7d32;font-weight:bold;">¥' + stopLoss.toFixed(2) + '</span>';
      html += '</div>';
    }}
    if (p.sellQty > 0) html += '，已实现盈亏 <span class="' + pnlClass + '">' + pnlSign + '¥' + realizedPnl.toFixed(2) + '</span>';
    html += '</div>';
  }});
  // 总盈亏
  const totalClass = totalPnl >= 0 ? 'pnl-pos' : 'pnl-neg';
  const totalSign = totalPnl >= 0 ? '+' : '';
  html += '<div style="margin-top:6px;padding:6px;background:#f5f5f5;border-radius:6px;font-size:13px;">';
  html += '总已实现盈亏：<span class="' + totalClass + '"><b>' + totalSign + '¥' + totalPnl.toFixed(2) + '</b></span>';
  html += '</div>';
  // 最近5条明细
  html += '<div style="margin-top:6px;font-size:11px;color:#888;">最近记录：</div>';
  trades.slice(-5).reverse().forEach(t => {{
    html += '<div class="trade-item">' + t.time + ' ' + (t.type === 'buy' ? '买入' : '卖出') + ' ' + t.name + ' ' + t.qty + '股 @ ¥' + t.price.toFixed(2) + '</div>';
  }});
  list.innerHTML = html;
}}
renderTrades();

// 可用资金（可自由修改）
function getBudget() {{
  const saved = localStorage.getItem('myBudget');
  return saved ? parseFloat(saved) : {BUDGET};
}}
function setBudget(v) {{
  localStorage.setItem('myBudget', v);
  renderBudget();
}}
function renderBudget() {{
  const b = getBudget();
  document.querySelectorAll('.w-total b').forEach(el => el.textContent = '¥' + b.toFixed(2));
}}
function editBudget() {{
  const v = prompt('请输入可用资金（元）：', getBudget());
  if (!v || isNaN(v) || v <= 0) return;
  setBudget(parseFloat(v));
  alert('资金已更新：¥' + parseFloat(v).toFixed(2));
}}
renderBudget();

// 实时行情刷新（JSONP方式，绕过CORS）
const stockCodes = [{','.join(f"'{r['code']}'" for r in out)}];

function refreshRealtime() {{
  // 用JSONP方式加载腾讯行情API
  const codes = stockCodes.join(',');
  const script = document.createElement('script');
  script.src = 'https://qt.gtimg.cn/q=' + codes;
  script.onload = () => {{
    try {{
      // 解析所有股票的实时数据
      stockCodes.forEach(code => {{
        const varName = 'v_' + code;
        if (typeof window[varName] === 'undefined') return;
        const data = window[varName];
        if (!data || typeof data !== 'string') return;
        const parts = data.split('~');
        if (parts.length < 35) return;
        
        const price = parseFloat(parts[3]);
        const prevClose = parseFloat(parts[4]);
        const chg = parseFloat(parts[32]);
        
        if (!price || isNaN(price)) return;
        
        // 更新价格显示
        const priceEls = document.querySelectorAll('.price');
        priceEls.forEach(el => {{
          if (el.dataset.code === code) {{
            el.textContent = '¥' + price.toFixed(2);
          }}
        }});
        // 更新涨跌幅
        const chgEls = document.querySelectorAll('.chg');
        chgEls.forEach(el => {{
          if (el.dataset.code === code) {{
            el.textContent = (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
            el.style.color = chg >= 0 ? '#d32f2f' : '#2e7d32';
          }}
        }});
      }});
      // 更新盈亏
      renderFloatingPnl();
    }} catch(e) {{
      console.log('实时数据解析失败', e);
    }}
    document.body.removeChild(script);
  }};
  script.onerror = () => {{
    console.log('实时数据请求失败');
    document.body.removeChild(script);
  }};
  document.body.appendChild(script);
}}

// 浮动盈亏计算
function renderFloatingPnl() {{
  const trades = getTrades();
  if (!trades.length) return;
  const positions = {{}};
  trades.forEach(t => {{
    if (!positions[t.code]) positions[t.code] = {{ name: t.name, buyQty: 0, buyCost: 0, sellQty: 0, sellRevenue: 0 }};
    if (t.type === 'buy') {{ positions[t.code].buyQty += t.qty; positions[t.code].buyCost += t.price * t.qty; }}
    else {{ positions[t.code].sellQty += t.qty; positions[t.code].sellRevenue += t.price * t.qty; }}
  }});
  // 找当前浮动盈亏显示区域
  const list = document.getElementById('tradeList');
  if (!list) return;
  // 在已实现盈亏后面加上浮动盈亏
  const floatingDiv = document.getElementById('floatingPnl');
  if (floatingDiv) floatingDiv.remove();
  let totalFloating = 0;
  let html = '';
  Object.values(positions).forEach(p => {{
    const holdQty = p.buyQty - p.sellQty;
    if (holdQty <= 0) return;
    const avgCost = p.buyCost / p.buyQty;
    // 找当前价格
    const priceEl = document.querySelector(`.price[data-code="${{p.code}}"]`);
    const curPrice = priceEl ? parseFloat(priceEl.textContent.replace('¥', '')) : avgCost;
    const floatingPnl = (curPrice - avgCost) * holdQty;
    totalFloating += floatingPnl;
    const cls = floatingPnl >= 0 ? 'pnl-pos' : 'pnl-neg';
    const sign = floatingPnl >= 0 ? '+' : '';
    html += '<div class="trade-item">' + p.name + ' 浮动盈亏：<span class="' + cls + '">' + sign + '¥' + floatingPnl.toFixed(2) + '</span>';
    // 止盈止损提醒
    const takeProfit = avgCost * 1.15;
    const stopLoss = avgCost * 0.85;
    if (curPrice >= takeProfit) {{
      html += ' <span style="background:#ffeb3b;color:#000;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;">⚠ 已达止盈</span>';
    }} else if (curPrice <= stopLoss) {{
      html += ' <span style="background:#ff5722;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;">⚠ 已达止损</span>';
    }}
    html += '</div>';
  }});
  if (html) {{
    const div = document.createElement('div');
    div.id = 'floatingPnl';
    const totalCls = totalFloating >= 0 ? 'pnl-pos' : 'pnl-neg';
    const totalSign = totalFloating >= 0 ? '+' : '';
    div.innerHTML = '<div style="margin-top:6px;padding:6px;background:#e8eaf6;border-radius:6px;font-size:13px;">' +
      '总浮动盈亏：<span class="' + totalCls + '"><b>' + totalSign + '¥' + totalFloating.toFixed(2) + '</b></span></div>' +
      html;
    list.appendChild(div);
  }}
}}

// 每5秒刷新一次（秒级实时更新）
setInterval(refreshRealtime, 5000);
// 页面加载后先刷新一次
setTimeout(refreshRealtime, 1000);

// K线图功能
function toggleChart(chartId) {{
  const chart = document.getElementById(chartId);
  if (chart.style.display === 'none') {{
    chart.style.display = 'block';
    const code = chartId.replace('chart_', '');
    drawKLine(code);
  }} else {{
    chart.style.display = 'none';
  }}
}}

function drawKLine(code) {{
  const canvas = document.getElementById('canvas_' + code);
  const dataEl = document.getElementById('data_' + code);
  if (!canvas || !dataEl) return;
  let data;
  try {{ data = JSON.parse(dataEl.textContent); }} catch(e) {{ return; }}
  if (!data || data.length === 0) return;

  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  // 找最高最低价
  let maxPrice = 0, minPrice = 9999;
  data.forEach(d => {{
    if (d.high && d.high > maxPrice) maxPrice = d.high;
    if (d.low && d.low < minPrice) minPrice = d.low;
  }});
  const range = maxPrice - minPrice || 1;
  const padding = 10;
  const chartH = h - padding * 2;
  const chartW = w - padding * 2;
  const barWidth = chartW / data.length * 0.6;

  // 画K线
  data.forEach((d, i) => {{
    const x = padding + (chartW / data.length) * i + (chartW / data.length - barWidth) / 2;
    const yOpen = padding + chartH * (1 - (d.open - minPrice) / range);
    const yClose = padding + chartH * (1 - (d.close - minPrice) / range);
    const yHigh = padding + chartH * (1 - (d.high - minPrice) / range);
    const yLow = padding + chartH * (1 - (d.low - minPrice) / range);

    // 红涨绿跌
    const color = d.close >= d.open ? '#d32f2f' : '#2e7d32';
    ctx.fillStyle = color;
    ctx.strokeStyle = color;

    // 上下影线
    ctx.beginPath();
    ctx.moveTo(x + barWidth / 2, yHigh);
    ctx.lineTo(x + barWidth / 2, yLow);
    ctx.stroke();

    // 实体
    const yTop = Math.min(yOpen, yClose);
    const barH = Math.max(Math.abs(yClose - yOpen), 1);
    ctx.fillRect(x, yTop, barWidth, barH);
  }});

  // 画价格标签
  ctx.fillStyle = '#666';
  ctx.font = '10px sans-serif';
  ctx.fillText(maxPrice.toFixed(2), 5, padding + 8);
  ctx.fillText(minPrice.toFixed(2), 5, h - padding);
}}
</script>
</body></html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_doc)

print("\n完成！生成：index.html（手机页）+ data.json（数据备份）")
print(f"更新于 {now}，数据源 {src}，候选 {len(out)} 只，可用资金 ¥{BUDGET:.2f}")
