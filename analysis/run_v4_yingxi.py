"""
V4 盈喜独立管线
===============
对已发布2026H1业绩盈喜(预增/略增/扭亏)的科技股，
独立运行 Round 3 估值筛选 + Round 4 深度分析 → HTML报告
"""
import sys, os, subprocess, shutil, time

DATE = '20260729'
INPUT_CSV = 'data/screen_v4_round2_yingxi.csv'

def run_cmd(cmd_args, timeout=600):
    sep = '=' * 70
    print(f'\n{sep}')
    print(f'  Running: {" ".join(cmd_args)}')
    print(sep)
    t0 = time.time()
    result = subprocess.run(cmd_args, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout,
                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    print(result.stdout[-1500:] if len(result.stdout) > 1500 else result.stdout)
    if result.stderr:
        print(f'STDERR: {result.stderr[:300]}')
    print(f'  耗时: {time.time()-t0:.0f}s (exit={result.returncode})')
    return result.returncode == 0

t_start = time.time()

# ── Round 3: 估值筛选(指定输入输出) ──
ok = run_cmd([
    sys.executable, '-c', f'''
import sys; sys.path.insert(0, '.')
import os; os.environ['PYTHONIOENCODING'] = 'utf-8'
import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd, numpy as np, time
from TG_trading_sys.data.cache import DataCache

INPUT = "{INPUT_CSV}"
OUTPUT = "data/screen_v4_round3_yingxi.csv"
DATE = "{DATE}"

df = pd.read_csv(INPUT)
print(f"[盈喜 Round 3] 估值筛选 — {{len(df)}} 只")

if len(df) == 0:
    print("无标的，终止")
    sys.exit(0)

TOP_N = min(50, len(df))
df = df.head(TOP_N)
print(f"  截取 Top {{TOP_N}} 只做估值分析")

cache = DataCache()
results = []

for i, (_, row) in enumerate(df.iterrows()):
    ts_code = str(row["ts_code"])
    code = str(ts_code.split(".")[0]).zfill(6)
    name = row["name"]
    price = row["close"]
    pe_ttm = row["pe_ttm"]
    pb = row["pb"]
    fc_type = row.get("fc_type", "")

    if (i + 1) % 15 == 0:
        print(f"    {{i+1}}/{{len(df)}}...")

    try:
        from TG_trading_sys.valuation.val_report import val_report
        val = val_report(code)
        final_value = val.get("final_value")
        mos = val.get("margin_of_safety_pct")
        mos_verdict = val.get("margin_of_safety_verdict", "")
        dcf_val = val.get("dcf", {{}}).get("per_share_value")
        peg_val = val.get("relative", {{}}).get("peg_value", {{}})
        pb_roe = val.get("relative", {{}}).get("pb_roe_value", {{}})
        research = val.get("relative", {{}}).get("research_consensus", {{}})
        n_reports = research.get("count", 0)
        consensus_target = research.get("avg_target")
    except Exception as e:
        val = {{}}; final_value = None; mos = None; mos_verdict = ""
        dcf_val = None; peg_val = {{}}; pb_roe = {{}}; research = {{}}
        n_reports = 0; consensus_target = None

    if mos is not None:
        if mos > 20: score_mos = 40
        elif mos > 10: score_mos = 30
        elif mos > 0: score_mos = 20
        elif mos > -10: score_mos = 10
        elif mos > -30: score_mos = 5
        else: score_mos = 0
    else:
        score_mos = 0

    peg_ratio = peg_val.get("peg")
    if peg_ratio is not None and peg_ratio > 0:
        if peg_ratio < 0.5: score_peg = 25
        elif peg_ratio < 1.0: score_peg = 20
        elif peg_ratio < 1.5: score_peg = 15
        elif peg_ratio < 2.0: score_peg = 10
        else: score_peg = 5
    else:
        score_peg = 0

    if n_reports >= 10: score_research = 10
    elif n_reports >= 5: score_research = 7
    elif n_reports >= 1: score_research = 4
    else: score_research = 0

    score_total = score_mos + score_peg + score_research

    # 盈喜溢价: 有盈喜的额外+5分
    if fc_type in ["预增", "略增", "扭亏"]:
        score_total += 5

    results.append({{
        "ts_code": ts_code, "code": code, "name": name,
        "industry": row["industry"], "price": price,
        "pe_ttm": pe_ttm, "pb": pb, "mcap_yi": row["total_mv"] / 10000,
        "rev_weighted": row.get("rev_weighted", 0), "np_weighted": row.get("np_weighted", 0),
        "gross_margin": row.get("gross_margin", None),
        "debt_to_assets": row.get("debt_to_assets", None),
        "fc_type": fc_type, "fc_p_min": row.get("fc_p_min"),
        "score_growth": row.get("score_growth", 0),
        "score_beat": row.get("score_beat", 0),
        "score_health": row.get("score_health", 0),
        "final_value": round(final_value, 2) if final_value else None,
        "mos_pct": mos, "mos_verdict": mos_verdict,
        "dcf_value": round(dcf_val, 2) if dcf_val else None,
        "peg_value": round(peg_val.get("fair_value"), 2) if peg_val.get("fair_value") else None,
        "pbroe_value": round(pb_roe.get("fair_value"), 2) if isinstance(pb_roe, dict) and pb_roe.get("fair_value") else None,
        "peg_ratio": round(peg_ratio, 2) if peg_ratio else None,
        "n_reports": n_reports, "consensus_target": consensus_target,
        "score_mos": score_mos, "score_peg": score_peg,
        "score_research": score_research, "score_total": score_total,
    }})

    time.sleep(0.15)

result_df = pd.DataFrame(results).sort_values("score_total", ascending=False)
final = result_df[result_df["score_total"] >= 10].head(25)
print(f"\\n盈喜估值筛选: {{len(final)}} 只 (≥10分)")
for _, r in final.iterrows():
    mos_s = f'{{r["mos_pct"]:+.1f}}%' if pd.notna(r["mos_pct"]) else "N/A"
    print(f'  {{r["code"]}} {{r["name"]:<10}} MOS={{mos_s}} PEG={{r.get("peg_ratio","-")}}')

final.to_csv(OUTPUT, index=False)
print(f"\\n保存: {{OUTPUT}} ({{len(final)}} 只)")
'''])

# ── Round 4: 深度分析 ──
ok = run_cmd([
    sys.executable, '-c', f'''
import sys; sys.path.insert(0, '.')
import subprocess
# Patch input file for Round 4
subprocess.run([sys.executable, "analysis/screen_v4_round4.py"],
    env={{**__import__("os").environ, "PYTHONIOENCODING": "utf-8",
          "V4_INPUT": "data/screen_v4_round3_yingxi.csv",
          "V4_OUTPUT_JSON": "data/deep_reports/all_reports_v4_yingxi.json"}},
    timeout=600)
'''], timeout=700)

# ── HTML Report ──
yingxi_json = 'data/deep_reports/all_reports_v4_yingxi.json'
yingxi_html = 'data/deep_reports/A股科技成长_V4_盈喜_深度分析.html'
v3_json = 'data/deep_reports/all_reports_v3.json'

if os.path.exists(yingxi_json):
    bak = v3_json + '.bak'
    if os.path.exists(bak): os.remove(bak)
    if os.path.exists(v3_json): os.rename(v3_json, bak)
    shutil.copy(yingxi_json, v3_json)

    run_cmd([sys.executable, 'analysis/report_v3_html.py'], timeout=300)

    v3_html = 'data/deep_reports/A股科技成长_V3_深度分析.html'
    if os.path.exists(v3_html):
        if os.path.exists(yingxi_html): os.remove(yingxi_html)
        os.rename(v3_html, yingxi_html)
    # Restore
    if os.path.exists(v3_json): os.remove(v3_json)
    if os.path.exists(bak): os.rename(bak, v3_json)

if os.path.exists(yingxi_html):
    print(f'\n[OK] 盈喜报告: {yingxi_html} ({os.path.getsize(yingxi_html)/1024:.0f} KB)')

total = time.time() - t_start
print(f'\n[OK] 盈喜管线完成！总耗时: {total:.0f}s')
