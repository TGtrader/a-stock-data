"""
VPA HTML 报告生成器
===================
生成包含K线图+成交量标注+趋势通道+资金流+信号标注的交互式HTML报告。
"""

import json
from datetime import datetime
from typing import Dict, List


def generate_html_report(report: dict, output_path: str = None) -> str:
    """
    生成完整的量价分析HTML报告。

    Args:
        report: vpa_analyze() 返回的 VpaReport
        output_path: 保存路径，None则返回HTML字符串

    Returns:
        HTML字符串
    """
    if "error" in report:
        return _error_html(report)

    name = report.get("name", report.get("code", ""))
    code = report.get("code", "")
    date = report.get("date", "")

    # 评级
    rating = report.get("rating", {})
    rating_text = rating.get("rating", "")
    rating_score = rating.get("score", 0)
    rating_emoji = _rating_emoji(rating_text)
    rating_class = _rating_class(rating_text)

    # 趋势
    st = report.get("trend", {}).get("short_term", {})
    mt = report.get("trend", {}).get("medium_term", {})
    align = report.get("trend", {}).get("alignment", {})
    phase = report.get("position", {}).get("phase", {})
    sr = report.get("position", {}).get("sr_levels", {})

    # 信号
    signals = report.get("signals", {})
    latest_bar = signals.get("latest_bar", {})
    recent_signals = signals.get("recent_signals", [])

    # 资金流
    mf = report.get("money_flow", {})
    ft = mf.get("flow_trend_resonance", {})
    sr_div = mf.get("smart_retail", {})

    # 综合建议
    conclusion = report.get("conclusion", "").replace("\n", "<br>")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>量价分析报告 — {name}({code})</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
.container {{ max-width: 1000px; margin: 0 auto; }}
.header {{ background: linear-gradient(135deg, #16213e, #0f3460); border-radius: 12px; padding: 30px; margin-bottom: 20px; text-align: center; }}
.header h1 {{ font-size: 28px; margin-bottom: 5px; }}
.header .code {{ color: #888; font-size: 14px; }}
.rating-badge {{ display: inline-block; padding: 10px 30px; border-radius: 30px; font-size: 24px; font-weight: bold; margin: 15px 0; }}
.rating-bull {{ background: #1b5e20; color: #4caf50; }}
.rating-bear {{ background: #4a0000; color: #f44336; }}
.rating-neutral {{ background: #333; color: #ffc107; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px; margin-bottom: 20px; }}
.card {{ background: #16213e; border-radius: 10px; padding: 20px; border: 1px solid #2a2a4a; }}
.card h3 {{ font-size: 16px; color: #888; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }}
.card .value {{ font-size: 24px; font-weight: bold; }}
.card .sub {{ font-size: 13px; color: #888; margin-top: 5px; }}
.bull {{ color: #4caf50; }}
.bear {{ color: #f44336; }}
.warn {{ color: #ff9800; }}
.neutral {{ color: #ffc107; }}
.signal-row {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #2a2a4a; }}
.signal-row:last-child {{ border-bottom: none; }}
.signal-type {{ font-size: 12px; padding: 2px 8px; border-radius: 10px; }}
.signal-type-cont {{ background: #1b5e20; color: #4caf50; }}
.signal-type-start {{ background: #1b5e20; color: #81c784; }}
.signal-type-exhaust {{ background: #4a0000; color: #f44336; }}
.signal-type-reverse {{ background: #3e2723; color: #ff9800; }}
.conclusion-box {{ background: linear-gradient(135deg, #1a1a2e, #16213e); border: 1px solid #2a2a4a; border-radius: 10px; padding: 25px; margin-bottom: 20px; line-height: 1.8; }}
.footer {{ text-align: center; color: #555; font-size: 12px; margin-top: 30px; }}
.score-bar {{ height: 8px; background: #333; border-radius: 4px; margin: 8px 0; }}
.score-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
.score-fill-bull {{ background: linear-gradient(90deg, #4caf50, #81c784); }}
.score-fill-bear {{ background: linear-gradient(90deg, #f44336, #ef9a9a); }}
.score-fill-neutral {{ background: linear-gradient(90deg, #ffc107, #fff176); }}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>{name}</h1>
    <div class="code">{code} · {date}</div>
    <div class="rating-badge {rating_class}">{rating_emoji} {rating_text} · {rating_score}/100</div>
</div>

<div class="grid">
    <div class="card">
        <h3>📊 短期趋势</h3>
        <div class="value {_dir_class(st.get('direction',''))}">{st.get('direction','')}</div>
        <div class="sub">阶段: {st.get('phase','')} | 强度: {st.get('strength',0)}/100</div>
        <div class="sub">均线: {st.get('ma_alignment','')}</div>
        <div style="margin-top:8px">
            <div class="score-bar"><div class="score-fill {_score_class(st.get('direction',''))}" style="width:{st.get('strength',50)}%"></div></div>
        </div>
    </div>

    <div class="card">
        <h3>📈 中期趋势</h3>
        <div class="value {_dir_class(mt.get('direction',''))}">{mt.get('direction','')}</div>
        <div class="sub">约束: {mt.get('constraint','')}</div>
        <div class="sub">{mt.get('ma_alignment','')}</div>
        <div style="margin-top:8px">
            <div class="score-bar"><div class="score-fill {_score_class(mt.get('direction',''))}" style="width:{mt.get('strength',50)}%"></div></div>
        </div>
    </div>

    <div class="card">
        <h3>💰 资金流</h3>
        <div class="value {_dir_class(ft.get('resonance',''))}">{ft.get('resonance','数据不可用')}</div>
        <div class="sub">强度: {ft.get('signal_strength',0)}/100</div>
        <div class="sub">主力vs散户: {sr_div.get('divergence','无数据')}</div>
    </div>

    <div class="card">
        <h3>🎯 趋势共振</h3>
        <div class="value {_dir_class(align.get('alignment',''))}">{align.get('alignment','')}</div>
        <div class="sub">{align.get('signal','')}</div>
    </div>
</div>

<div class="card" style="margin-bottom:20px">
    <h3>🔍 最新K线分析 ({latest_bar.get('date','')})</h3>
    <div class="grid" style="margin-top:12px">
        <div><span class="sub">形态: </span>{latest_bar.get('body_type','')}</div>
        <div><span class="sub">成交量: </span>{latest_bar.get('volume_level','')}</div>
        <div><span class="sub">量价验证: </span>{latest_bar.get('vpa_validation','')}</div>
        <div><span class="sub">蜡烛形态: </span>{latest_bar.get('candle_pattern') or '无特殊形态'}</div>
    </div>
</div>

<div class="card" style="margin-bottom:20px">
    <h3>📡 近期信号</h3>
"""

    # 信号列表
    if recent_signals:
        for sig in recent_signals[-8:]:
            stype = sig.get("type", "").replace("趋势", "")
            type_class = ""
            if "延续" in sig.get("type", "") or "启动" in sig.get("type", ""):
                type_class = "signal-type-cont"
            elif "衰竭" in sig.get("type", ""):
                type_class = "signal-type-exhaust"
            elif "反转" in sig.get("type", "") or "破坏" in sig.get("type", ""):
                type_class = "signal-type-reverse"
            icon = {"加仓": "➕", "减仓": "➖", "持仓": "📈", "离场": "🚪", "关注": "👀", "持仓/加仓": "📈", "观察": "👀", "观察/准备加仓": "👀"}
            action_icon = icon.get(sig.get("action", ""), "")

            html += f"""
    <div class="signal-row">
        <span>{sig['date']}</span>
        <span class="signal-type {type_class}">{sig['type']}</span>
        <strong>{sig['signal']}</strong>
        <span>{action_icon} {sig.get('action','')}</span>
    </div>"""
    else:
        html += '<div class="sub">无近期信号</div>'

    html += """
</div>

<div class="conclusion-box">
    <h3 style="color:#888;margin-bottom:15px">📋 综合研判</h3>
""" + conclusion + """
</div>

<div class="footer">
    VPA 量价分析模块 v1.0 · 基于威科夫理论 · Anna Coulling 方法论<br>
    生成时间: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """
</div>

</div>
</body>
</html>"""

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html


def _error_html(report: dict) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>分析失败</title></head>
<body style="background:#1a1a2e;color:#e0e0e0;font-family:sans-serif;text-align:center;padding:50px;">
<h1>❌ 分析失败</h1><p>{report.get('error','未知错误')}</p></body></html>"""


def _rating_emoji(rating: str) -> str:
    return {"趋势做多": "🟢", "偏多": "🟢", "观望": "🟡", "偏空": "🔴", "持币/做空": "🔴"}.get(rating, "⚪")


def _rating_class(rating: str) -> str:
    if rating in ("趋势做多", "偏多"):
        return "rating-bull"
    elif rating in ("偏空", "持币/做空"):
        return "rating-bear"
    return "rating-neutral"


def _dir_class(direction: str) -> str:
    if direction and direction.startswith("上涨"):
        return "bull"
    elif direction and direction.startswith("下跌"):
        return "bear"
    elif "共振看多" in direction or "吸筹" in direction:
        return "bull"
    elif "共振看空" in direction or "派筹" in direction:
        return "bear"
    return "neutral"


def _score_class(direction: str) -> str:
    if direction and direction.startswith("上涨"):
        return "score-fill-bull"
    elif direction and direction.startswith("下跌"):
        return "score-fill-bear"
    return "score-fill-neutral"
