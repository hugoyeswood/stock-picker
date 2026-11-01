# -*- coding: utf-8 -*-
"""
銆愪綘鐨勮嚜鍔ㄩ€夎偂灏忓姪鎵嬨€戞墜鏈虹増 + 浜戠鐗?+ 涔板崠鐐?+ 璧勯噾璐︽埛  build_site.py
====================================================
姣忓ぉ鑷姩锛氭媺鍏ㄥ競鍦烘暟鎹?-> 绛涢€?-> 涓哄€欓€夌畻涔板崠鐐?-> 鐢熸垚鎵嬫満椤甸潰 index.html + 鏁版嵁 data.json

鍔熻兘锛?  1. 璧勯噾璐︽埛锛氫粠 wallet.json 璇诲彇"褰撳墠鍙敤璧勯噾"锛屾寜鏈€鏂拌祫閲戠瓫閫?涔板緱璧风殑鑲?锛?     鎯冲姞閽辩敤 add_fund.py锛堣祫閲戣浆鍏ョ鍙ｏ級銆?  2. 涔板崠鐐癸細姣忓彧鍊欓€夌粰鍑?璇ヤ拱/绛夊洖韪?瑙傛湜 + 涔板叆鍙傝€冧环/姝㈡崯/姝㈢泩 +
     寤鸿涔板叆鍖洪棿 + 杩介珮椋庨櫓鎻愮ず + 涔板叆鍓嶇‘璁ゆ竻鍗曘€?  3. 瀹夊叏锛氭墍鏈夊啓鍏ラ〉闈㈢殑鏂囧瓧閮戒細鍋氳浆涔夛紝闃叉缃戦〉娉ㄥ叆闂銆?     鏈伐鍏蜂笉淇濆瓨浠讳綍璐﹀彿瀵嗙爜锛屽彧璇诲叕寮€鍏嶈垂琛屾儏銆?
鏁版嵁婧愯嚜鍔ㄥ垏鎹細鑵捐 -> 涓滄柟璐㈠瘜 -> 鏂版氮銆?====================================================
"""
import akshare as ak
import pandas as pd
import json
import html
from datetime import datetime, timedelta

# ============ 1. 鍙皟鐨?閫夎偂鍙ｅ懗" ============
BUDGET_DEFAULT = 1000.0   # 娌℃湁璧勯噾璐︽埛鏂囦欢鏃剁敤鐨勯粯璁よ祫閲?TOP_N    = 20             # 姣忓ぉ鏈€澶氭帹鍑犲彧
MIN_PRICE = 0.5
MAX_PRICE = 10.0

# ============ 2. 璇诲彇璧勯噾璐︽埛 ============
def load_wallet():
    """浠?wallet.json 璇诲綋鍓嶅彲鐢ㄨ祫閲戯紱鏂囦欢涓嶅瓨鍦ㄦ垨鍑洪敊鏃剁敤榛樿鍊?""
    try:
        with open("wallet.json", encoding="utf-8") as f:
            w = json.load(f)
        return float(w.get("available", BUDGET_DEFAULT)), w.get("ledger", [])
    except Exception:
        return BUDGET_DEFAULT, []

WALLET_AMT, WALLET_LEDGER = load_wallet()
BUDGET = WALLET_AMT

# ============ 3. 澶氭暟鎹簮鑷姩鍒囨崲 ============
def normalize(df, source):
    if source == "鑵捐":
        ren = {"zxj":"price","zdf":"chg","zdf_d5":"chg5","zdf_d10":"chg10",
               "zdf_d20":"chg20","zdf_d60":"chg60","lb":"lb","hsl":"hsl",
               "pe_ttm":"pe","zljlr":"mflow","ltsz":"ltsz","stock_type":"stype"}
    elif source == "涓滆储":
        ren = {"鏈€鏂颁环":"price","娑ㄨ穼骞?:"chg","閲忔瘮":"lb","鎹㈡墜鐜?:"hsl",
               "甯傜泩鐜?鍔ㄦ€?:"pe","鎬诲競鍊?:"ltsz","鑲＄エ浠ｇ爜":"code","鑲＄エ绠€绉?:"name"}
    else:
        ren = {"鏈€鏂颁环":"price","娑ㄨ穼骞?:"chg"}
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
    for source, fn in [("鑵捐", ak.stock_zh_a_spot_tx),
                       ("涓滆储", ak.stock_zh_a_spot_em),
                       ("鏂版氮", ak.stock_zh_a_spot)]:
        try:
            df = fn()
            print(f"[鏁版嵁婧怾 鐢?{source}")
            return normalize(df, source), source
        except Exception as e:
            print(f"[鏁版嵁婧怾 {source} 澶辫触({str(e)[:50]})锛屾崲涓嬩竴涓?..")
    raise RuntimeError("鎵€鏈夋暟鎹簮閮藉け璐?)

# ============ 4. 绠椾拱鍗栫偣锛堟媺鍘嗗彶K绾匡級 ============
def calc_trade(code, price):
    """鎷夎繎250澶╁巻鍙诧紝绠楀潎绾?鏀拺锛岀粰鍑轰拱鍗栫偣銆傚け璐ヨ繑鍥炲甫鍏滃簳淇℃伅鐨勫瓧鍏?""
    fallback = {"state": "鏈煡", "advice": "鍘嗗彶鏁版嵁鏆傜己锛屽缓璁厛鐪嬭鑲绾垮啀鍐冲畾",
                "buy_ref": round(price, 2), "stop_loss": None, "take_profit": None,
                "ma5": None, "ma20": None, "low20": None,
                "buy_low": round(price, 2), "buy_high": round(price, 2),
                "risk_note": "", "confirm": "鍘嗗彶鏁版嵁鏆傜己锛屼拱鍏ュ墠璇蜂汉宸ョ‘璁よ秼鍔?}
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
        # 鏈€杩?0澶㎏绾挎暟鎹紙鐢ㄤ簬鐢诲浘锛?        kline_data = []
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
        # 娑ㄨ穼鍋滀环锛圓鑲′富鏉柯?0%锛?        prev_close = float(close.iloc[-2]) if len(close) >= 2 else price
        limit_up = round(prev_close * 1.1, 2)
        limit_down = round(prev_close * 0.9, 2)
        # 鐘舵€?        if price >= ma20:
            dist = (price - ma5) / ma5 * 100 if (pd.notna(ma5) and ma5 > 0) else 0
            if dist <= 5:
                state = "鍙拱"; advice = "瓒嬪娍鍚戜笂锛屽彲鎸夊弬鑰冨尯闂翠拱鍏?鎵?
            else:
                state = "绛夊洖韪?; advice = f"鐭嚎娑ㄥ緱鎬ワ紝绛夊洖韪╁埌MA5(绾ma5:.2f}鍏?闄勮繎鍐嶄拱鏇寸ǔ"
        else:
            state = "瑙傛湜"; advice = "鐜颁环鍦?0鏃ョ嚎涓嬫柟锛屽厛瑙傚療锛屽埆鎬ョ潃杩?
        # 寤鸿涔板叆鍖洪棿锛氱幇浠蜂笌MA5鐨勮緝浣庤€?~ 鐜颁环锛堝埆楂樹簬鐜颁环杩斤級
        buy_low = round(min(price, ma5), 2) if pd.notna(ma5) else round(price, 2)
        buy_high = round(price, 2)
        stop = round(price * 0.95, 2)
        take = round(price * 1.10, 2)
        # 椋庨櫓鎻愮ず
        risks = []
        up_from_low = (price - low20) / low20 * 100 if (pd.notna(low20) and low20 > 0) else 0
        if up_from_low > 30:
            risks.append(f"杈冭繎20鏃ヤ綆鐐瑰凡娑▄up_from_low:.0f}%锛岃拷楂橀闄╄緝澶?)
        above_ma20 = (price / ma20 - 1) * 100 if ma20 > 0 else 0
        if above_ma20 > 12:
            risks.append(f"鐜颁环宸查珮鍑?0鏃ュ潎绾跨害{above_ma20:.0f}%锛岀煭绾垮亸鐑?)
        if stop and low20 and stop < low20:
            risks.append(f"姝㈡崯浠穥stop}宸蹭綆浜庤繎20鏃ヤ綆鐐箋low20:.2f}锛屾敞鎰忕牬浣嶉闄?)
        risk_note = "锛?.join(risks)
        # 涔板叆鍓嶇‘璁ゆ竻鍗?        confirm = (f"涔板墠纭锛氣憼璧勯噾澶熶拱1鎵?鈶″埜鍟嗘寕闄愪环鍗曪紝濉湪{buy_low}~{buy_high}鍏冨尯闂?"
                   f"鈶㈠悓鏃惰濂芥鎹熷崟{stop}鍏?鈶ｆ瘡娆″彧涔?鎵嬨€佷笉婊′粨")
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

print("姝ｅ湪鎷夊彇鍏ㄥ競鍦鸿鎯咃紙澶氭暟鎹簮鑷姩鍒囨崲锛?..")
df, src = fetch_all()
print(f"宸叉嬁鍒板叏甯傚満 {len(df)} 鍙偂绁紙鏁版嵁婧?{src}锛屽彲鐢ㄨ祫閲?楼{BUDGET:.2f}锛?)

# 鎻愬彇鍏ˋ鑲¤偂绁ㄥ垪琛紙鐢ㄤ簬鍓嶇鏈湴鎼滅储锛?all_stocks = []
for _, row in df.iterrows():
    code = str(row.get("code", ""))
    name = str(row.get("name", ""))
    if code and name:
        all_stocks.append({"code": code, "name": name})
print(f"宸叉彁鍙?{len(all_stocks)} 鍙偂绁ㄧ敤浜庡墠绔悳绱?)

# ============ 5. "鑳戒笉鑳戒拱"鐨勮繃婊わ紙璧勯噾绾︽潫浼樺厛锛?============
def 鏉垮潡_鍙拱(code):
    code = str(code)
    if code.startswith("sh6"): return True
    if code.startswith(("sz000","sz001","sz002","sz003")): return True
    return False

mask = (
    df["code"].apply(鏉垮潡_鍙拱)
    & (~df.get("name", pd.Series(index=df.index)).fillna("").astype(str).str.contains("ST", na=False))
    & (df["price"] >= MIN_PRICE)
    & (df["price"] <= MAX_PRICE)
    & (df["lb"].fillna(0) > 0)
)
pool = df[mask].copy()
print(f"杩囨护鍚庯紝褰撳墠璧勯噾涔板緱璧风殑娌繁涓绘澘鍊欓€?{len(pool)} 鍙?)

# ============ 6. 鎵撳垎锛堢己鏁版嵁鐨勯」鑷姩涓嶅弬涓庯級 ============
def 鎵撳垎(r):
    s, why = 0, []
    if pd.notna(r["chg"]) and pd.notna(r["lb"]):
        if r["chg"] > 1.0 and r["lb"] > 1.2: s += 2; why.append("浠婃棩鏀鹃噺涓婃定")
        elif r["chg"] > 0: s += 1; why.append("浠婃棩涓婃定")
    if pd.notna(r["chg10"]) and r["chg10"] > 0: s += 1; why.append("杩?0鏃ヨ蛋寮?)
    if pd.notna(r["chg20"]) and r["chg20"] > 0: s += 1; why.append("杩?0鏃ヨ蛋寮?)
    if pd.notna(r["mflow"]) and r["mflow"] > 0: s += 1; why.append("涓诲姏璧勯噾娴佸叆")
    if pd.notna(r["hsl"]) and 1 <= r["hsl"] <= 10: s += 1; why.append("鎹㈡墜娲昏穬")
    if pd.notna(r["pe"]) and 0 < r["pe"] < 60: s += 1; why.append("浼板€奸€備腑")
    return s, "銆?.join(why)

rows = pool.to_dict("records")
scored = []
for r in rows:
    s, why = 鎵撳垎(r)
    if s >= 3:
        scored.append((s, r, why))
scored.sort(reverse=True, key=lambda x: x[0])
top = scored[:TOP_N]
print(f"杈惧埌淇″彿闂ㄦ(鈮?鍒?鐨勬湁 {len(scored)} 鍙紝鍙栧墠 {TOP_N} 鍙?)

# ============ 6.5 娑ㄥ仠棰勬祴锛堜笓闂ㄧ瓫閫夊綋鏃ユ定鍋滄綔鍔涜偂锛?============
def 娑ㄥ仠棰勬祴鍒?r):
    """璁＄畻娑ㄥ仠娼滃姏鍒嗘暟"""
    s, reasons = 0, []
    # 褰撳ぉ娑ㄥ箙3%-9%锛堣繕娌℃定鍋滐紝浣嗗凡缁忔湁娑ㄥ箙锛?    if pd.notna(r["chg"]):
        if 3 <= r["chg"] <= 9:
            s += 3; reasons.append(f"浠婃棩宸叉定{r['chg']:.1f}%锛屾湁鍐叉定鍋滃姩鍔?)
        elif 1 <= r["chg"] < 3:
            s += 1; reasons.append(f"浠婃棩灏忔定{r['chg']:.1f}%锛岃搫鍔夸腑")
    # 閲忔瘮鏀惧ぇ锛?1.5璇存槑璧勯噾娑屽叆锛?    if pd.notna(r["lb"]) and r["lb"] > 1.5:
        s += 2; reasons.append(f"閲忔瘮{r['lb']:.1f}锛岃祫閲戞槑鏄炬秾鍏?)
    # 鎹㈡墜鐜囨椿璺冿紙2%-10%锛?    if pd.notna(r["hsl"]) and 2 <= r["hsl"] <= 10:
        s += 1; reasons.append(f"鎹㈡墜{r['hsl']:.1f}%锛屼氦鎶曟椿璺?)
    # 涓诲姏璧勯噾娴佸叆
    if pd.notna(r["mflow"]) and r["mflow"] > 0:
        s += 1; reasons.append("涓诲姏璧勯噾鍑€娴佸叆")
    # 杩戞湡璧板娍寮哄娍
    if pd.notna(r["chg5"]) and r["chg5"] > 0:
        s += 1; reasons.append(f"杩?鏃ユ定{r['chg5']:.1f}%锛岃秼鍔垮悜涓?)
    if pd.notna(r["chg10"]) and r["chg10"] > 0:
        s += 1; reasons.append(f"杩?0鏃ユ定{r['chg10']:.1f}%锛屼腑鏈熻蛋寮?)
    # 浠锋牸鍦ㄥ悎鐞嗗尯闂达紙5-30鍏冿紝鏇村鏄撴媺娑ㄥ仠锛?    if pd.notna(r["price"]) and 5 <= r["price"] <= 30:
        s += 1; reasons.append(f"鑲′环{r['price']:.1f}鍏冿紝鐩樺瓙閫備腑鏄撴媺鍗?)
    return s, reasons

limit_up_candidates = []
for r in rows:
    s, reasons = 娑ㄥ仠棰勬祴鍒?r)
    if s >= 5:  # 娑ㄥ仠娼滃姏鍒嗏墺5鍒?        limit_up_candidates.append((s, r, reasons))
limit_up_candidates.sort(reverse=True, key=lambda x: x[0])
limit_up_top = limit_up_candidates[:5]  # 鍙栧墠5鍙?print(f"娑ㄥ仠棰勬祴锛氭壘鍒?{len(limit_up_candidates)} 鍙綔鍔涜偂锛屽彇鍓?{len(limit_up_top)} 鍙?)

# ============ 7. 缁勮缁撴灉锛堝惈涔板崠鐐癸級 ============
print("姝ｅ湪閫愬彧鎷夊巻鍙睰绾跨畻涔板崠鐐癸紙绾﹀崐鍒嗛挓锛?..")
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

# ============ 7.5 缁勮娑ㄥ仠棰勬祴缁撴灉 ============
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

# 淇濆瓨鏁版嵁澶囦唤 data.json
with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"updated": now, "source": src, "budget": BUDGET,
               "count": len(out), "candidates": out,
               "limit_up_picks": limit_up_out}, f, ensure_ascii=False, indent=2)

# ============ 8. 鐢熸垚鎵嬫満鍙嬪ソ椤甸潰 index.html ============
def esc(x):
    """鎶婃墍鏈夊啓鍏ラ〉闈㈢殑鏂囧瓧杞箟锛岄槻姝㈡敞鍏?涔辩爜"""
    return html.escape(str(x), quote=True)

def fmt_pct(v):
    return "--" if v is None else f"{v:+.2f}%"
def color(v):
    if v is None or v == 0: return "#666"
    return "#d32f2f" if v > 0 else "#2e7d32"   # A鑲′範鎯細绾㈡定缁胯穼

STATE_STYLE = {"鍙拱": ("#e8f5e9", "#2e7d32"), "绛夊洖韪?: ("#fff3e0", "#e65100"),
               "瑙傛湜": ("#eeeeee", "#616161"), "鏈煡": ("#eeeeee", "#616161")}

cards = ""
for r in out:
    t = r["trade"]
    bg, fg = STATE_STYLE.get(t["state"], STATE_STYLE["鏈煡"])
    c_chg = color(r["chg"])
    chg5 = f"5鏃?{fmt_pct(r['chg5'])}" if r["chg5"] is not None else "5鏃?--"
    chg10 = f"10鏃?{fmt_pct(r['chg10'])}" if r["chg10"] is not None else "10鏃?--"
    chg20 = f"20鏃?{fmt_pct(r['chg20'])}" if r["chg20"] is not None else "20鏃?--"
    stop = f"楼{t['stop_loss']:.2f}" if t.get("stop_loss") else "--"
    take = f"楼{t['take_profit']:.2f}" if t.get("take_profit") else "--"
    risk_html = f'<div class="t-risk">鈿?{esc(t["risk_note"])}</div>' if t.get("risk_note") else ""
    cards += f"""
    <div class="card">
      <div class="card-top">
        <div><div class="name">{esc(r['name'])}</div><div class="code">{esc(r['code'])}</div></div>
        <div><span class="score">{r['score']}鍒?/span>
             <span class="state" style="background:{bg};color:{fg}">{esc(t['state'])}</span></div>
      </div>
      <div class="price-line">
        <span class="price" data-code="{esc(r['code'])}">楼{r['price']:.2f}</span>
        <span class="chg" data-code="{esc(r['code'])}" style="color:{c_chg}">{fmt_pct(r['chg'])}</span>
      </div>
      <div class="limit-row">
        <span class="limit-up">娑ㄥ仠 楼{t.get('limit_up', '--')}</span>
        <span class="limit-down">璺屽仠 楼{t.get('limit_down', '--')}</span>
      </div>
      <div class="tags">
        <span class="tag" style="color:{color(r['chg5'])}">{chg5}</span>
        <span class="tag" style="color:{color(r['chg10'])}">{chg10}</span>
        <span class="tag" style="color:{color(r['chg20'])}">{chg20}</span>
      </div>
      <div class="meta">閲忔瘮 {r['lb'] if r['lb'] is not None else '--'} 路 鎹㈡墜 {r['hsl'] if r['hsl'] is not None else '--'}% 路 甯傜泩鐜?{r['pe'] if r['pe'] is not None else '--'}</div>
      <div class="trade" style="background:{bg}">
        <div class="t-advice">{esc(t['advice'])}</div>
        <div class="t-row">涔板叆鍙傝€?<b>楼{r['price']:.2f}</b> 路 姝㈡崯 <b>{stop}</b> 路 姝㈢泩 <b>{take}</b></div>
        <div class="t-range">寤鸿涔板叆鍖洪棿 <b>楼{t['buy_low']:.2f} ~ 楼{t['buy_high']:.2f}</b>锛堝尯闂村唴鎸傚崟鏇寸ǔ锛屽埆楂樹簬鐜颁环杩斤級</div>
        {risk_html}
        <div class="t-confirm">{esc(t['confirm'])}</div>
      </div>
      <div class="why">{esc(r['why'])}</div>
      <div class="hands">浣犵殑 楼{BUDGET:.0f} 鍙拱 <b>{r['hands']}鎵?/b>锛堢害{r['cost']}鍏冿紝涓€鎵?100鑲★級</div>
      <div>
        <button class="trade-btn btn-buy" onclick="recordTrade('buy','{esc(r['code'])}','{esc(r['name'])}',{r['price']})">璁板綍涔板叆</button>
        <button class="trade-btn btn-sell" onclick="recordTrade('sell','{esc(r['code'])}','{esc(r['name'])}',{r['price']})">璁板綍鍗栧嚭</button>
        <button class="trade-btn btn-chart" onclick="toggleChart('chart_{esc(r['code'])}')">K绾垮浘</button>
      </div>
      <div id="chart_{esc(r['code'])}" class="chart-container" style="display:none;">
        <div class="chart-title">杩?0鏃绾?/div>
        <canvas id="canvas_{esc(r['code'])}" width="600" height="200"></canvas>
        <script type="application/json" id="data_{esc(r['code'])}">{json.dumps(t.get('kline', []), ensure_ascii=False)}</script>
      </div>
    </div>"""

wallet_rows = ""
for item in WALLET_LEDGER[-5:][::-1]:
    note = esc(item.get("note", "")) or "鈥?
    wallet_rows += f'<div class="w-row"><span class="w-date">{esc(item.get("date",""))}</span>'
    wallet_rows += f'<span class="w-amt">+楼{item["amount"]:.2f}</span><span class="w-note">{note}</span></div>'
wallet_html = f"""
<div class="card wallet">
  <div class="card-top"><div class="name">璧勯噾璐︽埛</div>
    <div class="w-total">褰撳墠鍙敤 <b>楼{BUDGET:.2f}</b> <button onclick="editBudget()" style="margin-left:8px;font-size:12px;padding:3px 10px;background:#1a237e;color:#fff;border:none;border-radius:4px;cursor:pointer;">缂栬緫</button></div></div>
  <div class="w-rows">{wallet_rows}</div>
  <div class="w-hint">鐐?缂栬緫"鍙洿鎺ヤ慨鏀瑰彲鐢ㄨ祫閲戯紝鏁版嵁淇濆瓨鍦ㄦ湰鍦般€?/div>
  <div class="trades">
    <h3>馃搵 鎴戠殑浜ゆ槗璁板綍</h3>
    <div id="tradeList"><div style="font-size:12px;color:#999;">杩樻病鏈変氦鏄撹褰曪紝鐐逛笅闈㈢殑鎸夐挳寮€濮嬭褰?/div></div>
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
<title>浠婃棩鍊欓€夋竻鍗?/title>
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
  .search-box {{ margin:10px 0; position:relative; }}
  .search-box input {{ width:100%; padding:10px 14px; border:1px solid #ddd; border-radius:8px; font-size:14px; box-sizing:border-box; }}
  .search-box input:focus {{ outline:none; border-color:#1a237e; }}
  .search-dropdown {{ position:absolute; left:0; right:0; top:100%; margin-top:4px; border:1px solid #ddd; border-radius:8px; background:#fff; box-shadow:0 4px 12px rgba(0,0,0,0.1); z-index:1000; max-height:300px; overflow-y:auto; display:none; }}
  .search-dropdown-item {{ padding:10px 14px; border-bottom:1px solid #f0f0f0; cursor:pointer; display:flex; justify-content:space-between; align-items:center; }}
  .search-dropdown-item:hover {{ background:#e3f2fd; }}
  .foot {{ font-size:11px; color:#999; text-align:center; margin-top:16px; line-height:1.6; }}
</style></head><body>
<h1>浠婃棩鍊欓€夋竻鍗?/h1>
<div class="sub">鏁版嵁鏇存柊浜?{now} 路 褰撳墠鏃堕棿锛?span id="currentTime"></span> 路 鏁版嵁婧愶細{esc(src)} 路 褰撳墠鍙敤璧勯噾 楼{BUDGET:.2f}</div>

<!-- 澶х洏鎸囨暟 -->
<div style="margin:10px 0;padding:10px;background:#f5f5f5;border-radius:8px;display:flex;justify-content:space-around;text-align:center;">
  <div>
    <div style="font-size:12px;color:#666;">涓婅瘉鎸囨暟</div>
    <div id="shIndex" style="font-size:16px;font-weight:bold;">--</div>
  </div>
  <div>
    <div style="font-size:12px;color:#666;">娣辫瘉鎴愭寚</div>
    <div id="szIndex" style="font-size:16px;font-weight:bold;">--</div>
  </div>
  <div>
    <div style="font-size:12px;color:#666;">鍒涗笟鏉挎寚</div>
    <div id="cyIndex" style="font-size:16px;font-weight:bold;">--</div>
  </div>
</div>

<!-- 閱掔洰鐨勯闄╅鍒ゆ彁绀?-->
<div style="margin:14px 0;padding:14px;background:linear-gradient(135deg,#ff5252,#d32f2f);border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(211,47,47,0.3);">
  <div style="font-size:16px;font-weight:bold;margin-bottom:8px;">鈿狅笍 椋庨櫓棰勫垽鎻愮ず</div>
  <div style="font-size:13px;line-height:1.8;opacity:0.95;">
    <b>寤鸿锛?/b>
    鈶?鍗曞彧鑲＄エ浠撲綅涓嶈秴杩囨€昏祫閲?0%锛屽埆鎶婇浮铔嬫斁涓€涓瀛?br>
    鈶?涓ユ牸姝㈡崯锛屼簭鎹熻秴杩?0%鏋滄柇绂诲満<br>
    鈶?娑ㄥ緱澶鐨勮偂绁ㄥ埆杩介珮锛岀瓑鍥炶俯鍐嶈€冭檻<br>
    鈶?鏂版墜鍏堢敤1000鍏冪粌鎵嬶紝鐔熸倝浜嗗啀鍔犱粨<br>
    鈶?鏈珹PP浠呬綔鏁版嵁鍙傝€冿紝涓嶆瀯鎴愭姇璧勫缓璁?  </div>
</div>

<!-- 鏂版墜寮曞锛?姝ワ級 -->
<div class="tip" style="background:#e3f2fd;border-left:4px solid #1976d2;">
  <b>馃摫 鏂版墜3姝ヤ笂鎵嬶細</b><br>
  鈶?鐪嬩笅闈㈡帹鑽愮殑鑲＄エ锛?鉁呭彲涔?鐨勫彲浠ヨ€冭檻涔板叆<br>
  鈶?鐐?璁板綍涔板叆"锛岃緭鍏ュ疄闄呮垚浜や环鏍?br>
  鈶?绯荤粺鑷姩甯綘鐩鐩堟鎹燂紝鍒扮偣鎻愰啋浣?br>
  <span style="color:#d32f2f;font-size:12px;">鈿狅笍 鏂版墜鎻愰啋锛氬厛灏忛挶缁冩墜锛屽埆閲嶄粨锛?/span>
</div>

<!-- 浠婃棩娑ㄥ仠棰勮 -->
<div style="margin:14px 0;padding:14px;background:linear-gradient(135deg,#ff6b6b,#ee5a24);border-radius:12px;color:#fff;">
  <div style="font-size:16px;font-weight:bold;margin-bottom:10px;">馃敟 浠婃棩娑ㄥ仠棰勮锛堢煭绾挎綔鍔涜偂锛?/div>
  <div style="font-size:12px;opacity:0.9;margin-bottom:10px;">浠ヤ笅鏄牴鎹祫閲戦潰銆佹妧鏈潰绛涢€夌殑浠婃棩娑ㄥ仠娼滃姏鑲★紝浠呬緵鍙傝€冿紝涓嶆瀯鎴愭姇璧勫缓璁?/div>
  {''.join(f'''
  <div style="background:rgba(255,255,255,0.15);border-radius:8px;padding:10px;margin-bottom:8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <div><b>{esc(r['name'])}</b> <span style="font-size:11px;opacity:0.8;">{esc(r['code'])}</span></div>
      <div style="text-align:right;">
        <div style="font-size:18px;font-weight:bold;">楼{r['price']:.2f}</div>
        <div style="font-size:12px;">{fmt_pct(r['chg'])}</div>
      </div>
    </div>
    <div style="font-size:11px;margin-top:6px;opacity:0.95;">
      <b>鎺ㄨ崘鐞嗙敱锛?/b><br>
      {''.join('路 ' + esc(reason) + '<br>' for reason in r['reasons'])}
    </div>
    <div style="margin-top:6px;font-size:11px;opacity:0.8;">
      閲忔瘮 {r['lb'] if r['lb'] else '--'} 路 鎹㈡墜 {r['hsl'] if r['hsl'] else '--'}% 路 娑ㄥ仠娼滃姏鍒?{r['score']}鍒?    </div>
  </div>
  ''' for r in limit_up_out)}
  <div style="font-size:11px;opacity:0.8;text-align:center;margin-top:6px;">鈿狅笍 娑ㄥ仠棰勬祴浠呬緵鍙傝€冿紝瀹為檯璧板娍鍙楀绉嶅洜绱犲奖鍝嶏紝娉ㄦ剰椋庨櫓</div>
</div>

<div class="search-box" style="display:flex;gap:8px;">
  <input type="text" id="searchInput" placeholder="杈撳叆鑲＄エ浠ｇ爜鎴栧悕绉?.." style="flex:1;padding:10px 14px;border:1px solid #ddd;border-radius:8px;font-size:14px;">
  <button onclick="doSearch()" style="padding:10px 20px;background:#1a237e;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;">鎼滅储</button>
</div>
<div class="stat">
  <div><b>{len(out)}</b><span>浠婃棩鍊欓€?/span></div>
  <div><b>{len(pool)}</b><span>涔板緱璧风殑鍊欓€?/span></div>
  <div><b>{sum(1 for x in out if x['trade']['state']=='鍙拱')}</b><span>"鍙拱"鏁伴噺</span></div>
</div>
{wallet_html}
<div id="stockCards">
{cards}
</div>

<!-- 鏂版墜甯歌闂 -->
<div style="margin:20px 0;padding:14px;background:#fff3e0;border-radius:8px;">
  <div style="font-weight:bold;margin-bottom:8px;">鉂?鏂版墜甯歌闂</div>
  <div style="font-size:13px;line-height:1.8;">
    <b>Q锛氭€庝箞娣诲姞鍒版墜鏈烘闈紵</b><br>
    A锛氭墜鏈烘祻瑙堝櫒鎵撳紑鏈〉 鈫?鑿滃崟 鈫?"娣诲姞鍒颁富灞忓箷"锛屽氨鍍廇pp涓€鏍风敤銆?br><br>
    <b>Q锛氫氦鏄撹褰曞瓨鍦ㄥ摢锛?/b><br>
    A锛氬瓨鍦ㄤ綘鎵嬫満鏈湴锛堟祻瑙堝櫒缂撳瓨锛夛紝涓嶄細涓婁紶鍒版湇鍔″櫒銆?br><br>
    <b>Q锛氭€庝箞娓呯┖璁板綍閲嶆柊寮€濮嬶紵</b><br>
    A锛氱偣涓嬮潰鐨?娓呯┖鎵€鏈夎褰?鎸夐挳銆?br><br>
    <button onclick="clearAllData()" style="margin-top:8px;padding:8px 16px;background:#f44336;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;">馃棏锔?娓呯┖鎵€鏈夎褰?/button>
  </div>
</div>

<div class="foot">鐘舵€佷緷鎹細鐜颁环 vs 20鏃ュ潎绾裤€佺5鏃ュ潎绾胯繙杩戯紱涔板叆鍖洪棿=鐜颁环涓嶮A5涔嬮棿銆?br>
鈿狅笍 鏈伐鍏蜂粎涓烘暟鎹瓫閫夊弬鑰冿紝涓嶆瀯鎴愭姇璧勫缓璁€傝偂甯傛湁椋庨櫓锛屽叆甯傞渶璋ㄦ厧銆?/div>
<script>
// 瀹炴椂鏇存柊褰撳墠鏃堕棿
function updateCurrentTime() {{
  try {{
    var now = new Date();
    var year = now.getFullYear();
    var month = String(now.getMonth() + 1).padStart(2, '0');
    var day = String(now.getDate()).padStart(2, '0');
    var hours = String(now.getHours()).padStart(2, '0');
    var minutes = String(now.getMinutes()).padStart(2, '0');
    var seconds = String(now.getSeconds()).padStart(2, '0');
    var weekdays = ['鏄熸湡鏃?, '鏄熸湡涓€', '鏄熸湡浜?, '鏄熸湡涓?, '鏄熸湡鍥?, '鏄熸湡浜?, '鏄熸湡鍏?];
    var weekday = weekdays[now.getDay()];
    var timeStr = year + '-' + month + '-' + day + ' ' + weekday + ' ' + hours + ':' + minutes + ':' + seconds;
    var el = document.getElementById('currentTime');
    if (el) el.textContent = timeStr;
  }} catch(e) {{}}
}}
updateCurrentTime();
setInterval(updateCurrentTime, 1000);

// 鎼滅储鍔熻兘
function doSearch() {{
  try {{
    var keyword = document.getElementById('searchInput').value.trim().toLowerCase();
    var cards = document.querySelectorAll('#stockCards .card');
    var matchCount = 0;
    cards.forEach(function(card) {{
      var name = card.querySelector('.name')?.textContent.toLowerCase() || '';
      var code = card.querySelector('.code')?.textContent.toLowerCase() || '';
      if (!keyword || name.includes(keyword) || code.includes(keyword)) {{
        card.style.display = '';
        matchCount++;
      }} else {{
        card.style.display = 'none';
      }}
    }});
    if (keyword) alert('鎼滅储鍒?' + matchCount + ' 鍙尮閰嶇殑鑲＄エ');
  }} catch(e) {{
    alert('鎼滅储鍑洪敊: ' + e.message);
  }}
}}

// 缂栬緫璧勯噾鍔熻兘
function editBudget() {{
  try {{
    var v = prompt('璇疯緭鍏ュ彲鐢ㄨ祫閲戯紙鍏冿級锛?, 1000);
    if (!v || isNaN(v) || v <= 0) return;
    localStorage.setItem('myBudget', v);
    alert('璧勯噾宸叉洿鏂帮細楼' + parseFloat(v).toFixed(2));
    location.reload();
  }} catch(e) {{
    alert('缂栬緫鍑洪敊: ' + e.message);
  }}
}}

// 娓呯┖鎵€鏈夋暟鎹?function clearAllData() {{
  if (!confirm('纭畾瑕佹竻绌烘墍鏈変氦鏄撹褰曞拰璧勯噾璁剧疆鍚楋紵姝ゆ搷浣滀笉鍙仮澶嶏紒')) return;
  localStorage.removeItem('myTrades');
  localStorage.removeItem('myBudget');
  alert('宸叉竻绌烘墍鏈夎褰曪紒');
  location.reload();
}}
</script>
</body></html>"""
