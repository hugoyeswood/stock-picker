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
                "risk_note": "", "confirm": "历史数据暂缺，买入前请人工确认趋势",
                "kline30": []}
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
        ma5  = close.tail(5).mean()
        ma20 = close.tail(20).mean()
        low20 = low.tail(20).min()
        if pd.isna(ma20):
            return fallback
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
        # 提取近30日K线（[date,open,close,high,low]）供前端画图
        kline30 = []
        try:
            for _, row in hist.tail(30).iterrows():
                kline30.append([str(row.get("date", ""))[:10],
                                round(float(row["open"]), 2), round(float(row["close"]), 2),
                                round(float(row["high"]), 2), round(float(row["low"]), 2)])
        except Exception:
            kline30 = []
        return {
            "state": state, "advice": advice,
            "buy_ref": round(price, 2), "stop_loss": stop, "take_profit": take,
            "ma5": round(ma5, 2) if pd.notna(ma5) else None,
            "ma20": round(ma20, 2), "low20": round(low20, 2),
            "buy_low": buy_low, "buy_high": buy_high,
            "risk_note": risk_note, "confirm": confirm,
            "kline30": kline30,
        }
    except Exception:
        return fallback

print("正在拉取全市场行情（多数据源自动切换）...")
df, src = fetch_all()
print(f"已拿到全市场 {len(df)} 只股票（数据源:{src}，可用资金:¥{BUDGET:.2f}）")

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

now = datetime.now().strftime("%Y-%m-%d %H:%M")

# 保存数据备份 data.json
with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"updated": now, "source": src, "budget": BUDGET,
               "count": len(out), "candidates": out}, f, ensure_ascii=False, indent=2)

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


# ============ 7.5 24小时预判（基于买卖点状态+价格位置） ============
def predict24(t):
    st = t.get("state")
    if st == "可买": return ("看多", "高", "#c62828", "#ffebee")
    elif st == "等回踩": return ("偏多震荡", "中", "#f57f17", "#fff8e1")
    else: return ("偏空震荡", "中", "#f57f17", "#fff8e1")

cards = ""
for r in out:
    t = r["trade"]
    bg, fg = STATE_STYLE.get(t["state"], STATE_STYLE["未知"])
    c_chg = color(r["chg"])
    # 24小时预判 + K线数据
    trend_label, trend_conf, trend_color, trend_bg = predict24(t)
    kline_json = ""
    try:
        k = t.get("kline30") or []
        if k: kline_json = json.dumps(k)
    except Exception:
        kline_json = ""
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
      <div class="trend-row" style="margin:8px 0;padding:8px 10px;border-radius:6px;background:{trend_bg};border-left:3px solid {trend_color};">
        <div style="font-size:13px;font-weight:600;color:{trend_color};">📊 24小时预判：{trend_label} <span style="font-size:11px;font-weight:400;color:#666;">（置信度：{trend_conf}）</span></div>
      </div>
      <button class="btn-chart" onclick="toggleChart('chart_{esc(r['code'])}')">📈 K线图</button>
      <div id="chart_{esc(r['code'])}" class="chart-container" style="display:none;">
        <div class="chart-title">近30日K线 · 红涨绿跌</div>
        <canvas id="canvas_{esc(r['code'])}" width="600" height="200"></canvas>
      </div>
      <div id="data_{esc(r['code'])}" style="display:none;">{kline_json}</div>
    </div>"""

wallet_rows = ""
for item in WALLET_LEDGER[-5:][::-1]:
    note = esc(item.get("note", "")) or "—"
    wallet_rows += f'<div class="w-row"><span class="w-date">{esc(item.get("date",""))}</span>'
    wallet_rows += f'<span class="w-amt">+¥{item["amount"]:.2f}</span><span class="w-note">{note}</span></div>'
wallet_html = f"""
<div class="card wallet">
  <div class="card-top"><div class="name">资金账户</div>
    <div class="w-total">当前可用 <b>¥{BUDGET:.2f}</b></div></div>
  <div class="w-rows">{wallet_rows}</div>
  <div class="w-hint">要转入资金？本地运行 <b>python add_fund.py</b>，然后重新部署即可。</div>
</div>"""

EXTRA_CSS = '\n  .search-box { display:flex; gap:8px; margin-bottom:10px; position:relative; }\n  .search-box input { flex:1; padding:11px 12px; border:1px solid #d0d0d0; border-radius:8px; font-size:14px; outline:none; }\n  .search-box input:focus { border-color:#1a237e; }\n  .search-box button { padding:11px 16px; background:#1a237e; color:#fff; border:none; border-radius:8px; cursor:pointer; font-size:14px; }\n  #searchResult { display:none; position:absolute; left:0; right:0; top:100%; margin-top:4px; border:1px solid #ddd; border-radius:8px;\n                  background:#fff; box-shadow:0 4px 12px rgba(0,0,0,.15); z-index:1000; max-height:300px; overflow-y:auto; }\n  .budget-line { text-align:center; font-size:14px; color:#1a237e; background:#e8eaf6; border-radius:8px; padding:9px; margin-bottom:12px; }\n    .btn-chart { display:block; width:100%; margin:6px 0; padding:9px; background:#1a237e; color:#fff; border:none; border-radius:8px; font-size:13px; cursor:pointer; }\n  .chart-container { margin-top:8px; border:1px solid #eee; border-radius:8px; padding:8px; background:#fafafa; }\n  .chart-title { font-size:12px; color:#666; margin-bottom:4px; }\n  .chart-container canvas { width:100%; height:200px; }\n  .trend-row { font-size:13px; }\n'
SEARCH_HTML = '<div class="search-box">\n  <input type="text" id="searchInput" placeholder="输入股票代码/名称，全网搜索..." onkeydown="if(event.key===\'Enter\')searchStocks()">\n  <button onclick="searchStocks()">🔍 搜索</button>\n  <div id="searchResult"></div>\n</div>\n<div class="budget-line">可用资金 <b id="budgetDisplay" onclick="editBudget()" title="点击编辑">¥1000.00</b>（点我直接改，存本地）</div>\n'
APP_JS_EXTRA = "\n// ===== 实时价格刷新（O(n)优化版：缓存DOM映射，避免每只股票全页扫描） =====\nvar _priceMap = null;\nfunction getPriceMap(){\n  if(_priceMap) return _priceMap;\n  _priceMap = { p:{}, c:{} };\n  document.querySelectorAll('.price[data-code]').forEach(function(el){ _priceMap.p[el.getAttribute('data-code')] = el; });\n  document.querySelectorAll('.chg[data-code]').forEach(function(el){ _priceMap.c[el.getAttribute('data-code')] = el; });\n  return _priceMap;\n}\nfunction refreshRealtime(){\n  var codes = [];\n  document.querySelectorAll('.price[data-code]').forEach(function(el){ codes.push(el.getAttribute('data-code')); });\n  if(!codes.length) return;\n  var m = getPriceMap();\n  var s = document.createElement('script');\n  s.src = 'https://qt.gtimg.cn/q=' + codes.join(',');\n  s.onload = function(){\n    try{\n      codes.forEach(function(code){\n        var data = window['v_' + code];\n        if(!data || typeof data !== 'string') return;\n        var parts = data.split('~');\n        if(parts.length < 35) return;\n        var price = parseFloat(parts[3]), chg = parseFloat(parts[32]);\n        if(!price || isNaN(price)) return;\n        var pe = m.p[code], ce = m.c[code];\n        if(pe) pe.textContent = '¥' + price.toFixed(2);\n        if(ce){ ce.textContent = (chg>=0?'+':'') + chg.toFixed(2) + '%'; ce.style.color = chg>=0 ? '#d32f2f' : '#2e7d32'; }\n      });\n    }catch(e){ console.log('实时解析失败', e); }\n    if(s.parentNode) s.parentNode.removeChild(s);\n  };\n  s.onerror = function(){ if(s.parentNode) s.parentNode.removeChild(s); };\n  document.body.appendChild(s);\n}\nsetInterval(refreshRealtime, 10000); // 每10秒刷新（比5秒省一半请求）\nsetTimeout(refreshRealtime, 1500);   // 页面加载后先刷一次\n\n// ===== K线图（canvas高清适配 devicePixelRatio） =====\nfunction toggleChart(chartId){\n  var chart = document.getElementById(chartId);\n  if(!chart) return;\n  if(chart.style.display === 'none'){ chart.style.display = 'block'; drawKLine(chartId.replace('chart_','')); }\n  else chart.style.display = 'none';\n}\nfunction drawKLine(code){\n  var canvas = document.getElementById('canvas_' + code);\n  var dataEl = document.getElementById('data_' + code);\n  if(!canvas || !dataEl) return;\n  var data;\n  try{ data = JSON.parse(dataEl.textContent); }catch(e){ return; }\n  if(!data || !data.length) return;\n  var dpr = window.devicePixelRatio || 1;\n  var w = canvas.clientWidth || canvas.width;\n  var h = 200;\n  canvas.width = w * dpr; canvas.height = h * dpr;\n  canvas.style.width = w + 'px'; canvas.style.height = h + 'px';\n  var ctx = canvas.getContext('2d');\n  ctx.scale(dpr, dpr);\n  ctx.clearRect(0, 0, w, h);\n  var maxPrice = 0, minPrice = Infinity;\n  data.forEach(function(d){ if(d[3] > maxPrice) maxPrice = d[3]; if(d[4] < minPrice) minPrice = d[4]; });\n  var range = maxPrice - minPrice || 1;\n  var pad = 12, cw = w - pad*2, ch = h - pad*2;\n  var bw = cw / data.length * 0.6;\n  data.forEach(function(d, i){\n    var x = pad + (cw/data.length)*i + (cw/data.length - bw)/2;\n    var yo = pad + ch*(1-(d[1]-minPrice)/range);\n    var yc = pad + ch*(1-(d[2]-minPrice)/range);\n    var yh = pad + ch*(1-(d[3]-minPrice)/range);\n    var yl = pad + ch*(1-(d[4]-minPrice)/range);\n    var col = d[2] >= d[1] ? '#d32f2f' : '#2e7d32';\n    ctx.strokeStyle = col; ctx.fillStyle = col;\n    ctx.beginPath(); ctx.moveTo(x+bw/2, yh); ctx.lineTo(x+bw/2, yl); ctx.stroke();\n    var yTop = Math.min(yo, yc), bh = Math.max(Math.abs(yc-yo), 1);\n    ctx.fillRect(x, yTop, bw, bh);\n  });\n  ctx.fillStyle = '#666'; ctx.font = '10px sans-serif';\n  ctx.fillText(maxPrice.toFixed(2), 3, pad+8);\n  ctx.fillText(minPrice.toFixed(2), 3, h-2);\n}\n"

APP_JS = '\n// ===== 资金（可编辑，存本地） =====\nfunction getBudget(){ try{ return parseFloat(localStorage.getItem(\'myBudget\'))||1000; }catch(e){ return 1000; } }\nfunction setBudget(v){ localStorage.setItem(\'myBudget\', v); refreshBudgetDisplay(); }\nfunction refreshBudgetDisplay(){ var el=document.getElementById(\'budgetDisplay\'); if(el) el.textContent=\'¥\'+getBudget().toFixed(2); }\nfunction editBudget(){ var v=prompt(\'请输入可用资金（元）：\', getBudget()); if(!v||isNaN(v)||parseFloat(v)<=0) return; setBudget(parseFloat(v)); alert(\'资金已更新：¥\'+parseFloat(v).toFixed(2)); }\n\n// ===== 交易费用 =====\nfunction calcFee(amount,type){ var c=Math.max(amount*0.00025,5); var t=amount*0.00002; var s=0; if(type===\'sell\') s=amount*0.001; return c+t+s; }\n\n// ===== 交易记录（存本地） =====\nfunction getTrades(){ try{ return JSON.parse(localStorage.getItem(\'myTrades\')||\'[]\'); }catch(e){ return []; } }\nfunction saveTrades(t){ localStorage.setItem(\'myTrades\', JSON.stringify(t)); }\n\n// ===== 全网搜索（JSONP，腾讯smartbox） =====\nfunction searchStocks(){\n  var keyword=(document.getElementById(\'searchInput\').value||\'\').trim();\n  if(!keyword) return;\n  var div=document.getElementById(\'searchResult\');\n  var cb=\'searchCb_\'+Date.now();\n  window[cb]=function(results){\n    try{\n      if(!results||!results.length){ div.innerHTML=\'<div style="padding:14px;color:#999;font-size:13px;">未找到匹配股票</div>\'; div.style.display=\'block\'; return; }\n      var html=\'\';\n      results.forEach(function(r){\n        html+=\'<div onclick="closeSearch();showStockDetail(\\\'\'+r.code+\'\\\',\\\'\'+r.name+\'\\\')" style="padding:10px 14px;border-bottom:1px solid #f0f0f0;cursor:pointer;display:flex;justify-content:space-between;align-items:center;">\';\n        html+=\'<span><b style="color:#1a237e;">\'+r.name+\'</b></span><span style="color:#666;font-size:12px;background:#f5f5f5;padding:2px 8px;border-radius:4px;">\'+r.code+\'</span></div>\';\n      });\n      div.innerHTML=html; div.style.display=\'block\';\n    }finally{ delete window[cb]; var s=document.getElementById(cb); if(s&&s.parentNode) s.parentNode.removeChild(s); }\n  };\n  var s=document.createElement(\'script\'); s.id=cb;\n  s.src=\'https://smartbox.gtimg.cn/s3/?v=2&q=\'+encodeURIComponent(keyword)+\'&t=all\';\n  s.onload=function(){\n    try{\n      var raw=window.v_hint||\'\';\n      if(!raw){ div.innerHTML=\'<div style="padding:14px;color:#999;font-size:13px;">未找到匹配股票</div>\'; div.style.display=\'block\'; }\n      else{\n        var results=[];\n        raw.split(\'^\').forEach(function(item){ var p=item.split(\'~\'); if(p.length>=3&&p[4]&&p[4].indexOf(\'GP\')===0){ results.push({code:p[0]+p[1],name:p[2]}); } });\n        window[cb](results);\n      }\n    }catch(e){ console.log(\'搜索解析失败\',e); }\n    if(s.parentNode) s.parentNode.removeChild(s);\n  };\n  s.onerror=function(){ div.innerHTML=\'<div style="padding:14px;color:#999;font-size:13px;">搜索失败，请检查网络后重试</div>\'; div.style.display=\'block\'; if(s.parentNode) s.parentNode.removeChild(s); };\n  document.body.appendChild(s);\n}\nfunction closeSearch(){ var div=document.getElementById(\'searchResult\'); if(div) div.style.display=\'none\'; }\n\n// ===== 行情详情（JSONP，腾讯qt） =====\nfunction showStockDetail(code,name){\n  closeSearch();\n  var cb=\'detailCb_\'+Date.now();\n  window[cb]=function(){\n    try{\n      var data=window[\'v_\'+code];\n      if(!data||typeof data!==\'string\'){ alert(\'获取行情失败，请重试\'); return; }\n      var parts=data.split(\'~\');\n      if(parts.length<35) return;\n      var price=parseFloat(parts[3]),chg=parseFloat(parts[32]),open=parseFloat(parts[5]),high=parseFloat(parts[33]),low=parseFloat(parts[34]),prevClose=parseFloat(parts[4]);\n      var limitUp=(prevClose*1.1).toFixed(2),limitDown=(prevClose*0.9).toFixed(2);\n      var chgColor=chg>=0?\'#c62828\':\'#2e7d32\';\n      var budget=getBudget();\n      var maxQty=Math.floor(budget/price/100)*100;\n      var canBuy=maxQty>=100;\n      var html=\n        \'<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;">\'+\n        \'<div style="background:#fff;border-radius:12px;padding:20px;width:90%;max-width:400px;max-height:80vh;overflow-y:auto;">\'+\n        \'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">\'+\n        \'<div><h2 style="margin:0;font-size:18px;">\'+name+\'</h2><div style="color:#666;font-size:12px;">\'+code+\'</div></div>\'+\n        \'<button onclick="closeStockDetail()" style="background:#eee;border:none;border-radius:50%;width:32px;height:32px;cursor:pointer;font-size:16px;">×</button></div>\'+\n        \'<div style="text-align:center;margin:20px 0;">\'+\n        \'<div style="font-size:36px;font-weight:bold;color:\'+chgColor+\';">¥\'+price.toFixed(2)+\'</div>\'+\n        \'<div style="color:\'+chgColor+\';font-size:16px;">\'+(chg>=0?\'+\':\'\')+chg.toFixed(2)+\'%</div></div>\'+\n        \'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:13px;">\'+\n        \'<div>今开：¥\'+open.toFixed(2)+\'</div><div>昨收：¥\'+prevClose.toFixed(2)+\'</div>\'+\n        \'<div>最高：¥\'+high.toFixed(2)+\'</div><div>最低：¥\'+low.toFixed(2)+\'</div>\'+\n        \'<div style="color:#c62828;">涨停：¥\'+limitUp+\'</div><div style="color:#2e7d32;">跌停：¥\'+limitDown+\'</div></div>\'+\n        \'<div style="margin-top:16px;padding:10px;background:#e8eaf6;border-radius:8px;font-size:13px;text-align:center;">\'+\n        \'可用资金：<b>¥\'+budget.toFixed(2)+\'</b> · 当前价可买：<b>\'+(canBuy?maxQty+\'股\':\'资金不足\')+\'</b></div>\'+\n        \'<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;">\'+\n        \'<button onclick="buyWithBudget(\\\'\'+code+\'\\\',\\\'\'+name+\'\\\',\'+price+\')" style="flex:1;padding:12px;background:#c62828;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;\'+(canBuy?\'\':\'opacity:0.5;\')+\'">⚡一键模拟买入</button>\'+\n        \'<button onclick="recordTrade(\\\'buy\\\',\\\'\'+code+\'\\\',\\\'\'+name+\'\\\',\'+price+\')" style="flex:1;padding:12px;background:#ff7043;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;">记录买入</button></div>\'+\n        \'<div style="margin-top:8px;"><button onclick="recordTrade(\\\'sell\\\',\\\'\'+code+\'\\\',\\\'\'+name+\'\\\',\'+price+\')" style="width:100%;padding:12px;background:#2e7d32;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;">记录卖出</button></div>\'+\n        \'<div style="margin-top:12px;font-size:11px;color:#999;text-align:center;">⚠️ 模拟交易仅记录本地，不连接券商，不构成投资建议</div>\'+\n        \'</div></div>\';\n      var m=document.getElementById(\'stockDetailModal\');\n      if(!m){ m=document.createElement(\'div\'); m.id=\'stockDetailModal\'; document.body.appendChild(m); }\n      m.innerHTML=html; m.style.display=\'block\';\n    }catch(e){ console.log(\'详情解析失败\',e); alert(\'获取行情失败，请重试\'); }\n    finally{ delete window[cb]; var s=document.getElementById(cb); if(s&&s.parentNode) s.parentNode.removeChild(s); }\n  };\n  var s=document.createElement(\'script\'); s.id=cb; s.src=\'https://qt.gtimg.cn/q=\'+code;\n  s.onload=function(){ try{ window[cb](); }catch(e){} if(s.parentNode) s.parentNode.removeChild(s); };\n  s.onerror=function(){ try{ window[cb](); }catch(e){ alert(\'获取行情失败，请检查网络\'); } if(s.parentNode) s.parentNode.removeChild(s); };\n  document.body.appendChild(s);\n}\nfunction closeStockDetail(){ var m=document.getElementById(\'stockDetailModal\'); if(m) m.style.display=\'none\'; }\n\n// ===== 一键模拟买入 =====\nfunction buyWithBudget(code,name,price){\n  var budget=getBudget();\n  var maxQty=Math.floor(budget/price/100)*100;\n  if(maxQty<100){ alert(\'可用资金不足！\\n可用资金：¥\'+budget.toFixed(2)+\'\\n当前价：¥\'+price.toFixed(2)+\'\\n买1手(100股)需要：¥\'+(price*100).toFixed(2)); return; }\n  var amount=price*maxQty, fee=calcFee(amount,\'buy\'), total=amount+fee;\n  if(total>budget){ var q2=maxQty-100; if(q2<100){ alert(\'交易费用后资金不足，请调整\'); return; } maxQty=q2; amount=price*maxQty; fee=calcFee(amount,\'buy\'); total=amount+fee; }\n  var trades=getTrades();\n  trades.push({type:\'buy\',code:code,name:name,price:price,qty:maxQty,amount:amount,fee:fee,time:new Date().toLocaleString(\'zh-CN\'),auto:true});\n  saveTrades(trades);\n  setBudget(budget-total);\n  alert(\'⚡ 模拟买入成功！\\n\'+name+\' \'+maxQty+\'股 @ ¥\'+price.toFixed(2)+\'\\n成交金额：¥\'+amount.toFixed(2)+\'\\n交易费用：¥\'+fee.toFixed(2)+\'\\n实际支出：¥\'+total.toFixed(2)+\'\\n剩余资金：¥\'+(budget-total).toFixed(2));\n  closeStockDetail();\n}\n\n// ===== 手动记录交易 =====\nfunction recordTrade(type,code,name,price){\n  var pi=prompt(\'请输入实际成交价格（元）：\',price); if(!pi||isNaN(pi)||parseFloat(pi)<=0) return;\n  var qi=prompt(\'请输入数量（股），1手=100股：\',\'100\'); if(!qi||isNaN(qi)||parseInt(qi)<=0) return;\n  var p=parseFloat(pi), q=parseInt(qi), amt=p*q, fee=calcFee(amt,type);\n  var trades=getTrades(); trades.push({type:type,code:code,name:name,price:p,qty:q,amount:amt,fee:fee,time:new Date().toLocaleString(\'zh-CN\')}); saveTrades(trades);\n  alert((type===\'buy\'?\'买入\':\'卖出\')+\'记录成功：\\n\'+name+\' \'+q+\'股 @ ¥\'+p.toFixed(2)+\'\\n成交金额：¥\'+amt.toFixed(2)+\'\\n交易费用：¥\'+fee.toFixed(2)+\'\\n实际支出：¥\'+(amt+fee).toFixed(2));\n  closeStockDetail();\n}\n\nrefreshBudgetDisplay();\n'

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
  .foot {{ font-size:11px; color:#999; text-align:center; margin-top:16px; line-height:1.6; }}
{EXTRA_CSS}</style></head><body>
<h1>今日候选清单</h1>
<div class="sub">更新于 {now} · 数据源：{esc(src)} · 当前可用资金 ¥{BUDGET:.2f}</div>
<div class="tip"><b>怎么用：</b>看卡片【状态】——"可买"按【建议买入区间】挂限价单买1手；"等回踩"别追高；"观望"先别碰。<br>
买入后设好<b>止损</b>(跌到就走)和<b>止盈</b>(涨到落袋)。<b>提醒：</b>数据筛选，非投资建议；涨跌有风险，控制仓位。</div>
{SEARCH_HTML}
<div class="stat">
  <div><b>{len(out)}</b><span>今日候选</span></div>
  <div><b>{len(pool)}</b><span>买得起的候选</span></div>
  <div><b>{sum(1 for x in out if x['trade']['state']=='可买')}</b><span>"可买"数量</span></div>
</div>
{wallet_html}
{cards}
<div class="foot">状态依据：现价 vs 20日均线、离5日均线远近；买入区间=现价与MA5之间。<br>
资金账户：本地 python add_fund.py 转入资金后重新部署 · 添加到主屏幕即可像App一样用 · 每天收盘后自动更新</div>
<script>
{APP_JS}
{APP_JS_EXTRA}
if ('serviceWorker' in navigator) {{ navigator.serviceWorker.register('./service-worker.js'); }}
</script>
</body></html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_doc)

print("\n完成！生成：index.html（手机页）+ data.json（数据备份）")
print(f"更新于 {now}，数据源 {src}，候选 {len(out)} 只，可用资金 ¥{BUDGET:.2f}")
