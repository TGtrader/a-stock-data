"""
V4 全量管线编排器 (双轨)
========================
常规轨: Round 2评分→Round 3估值→Round 4深度→HTML报告
盈喜轨: 业绩盈喜公司→独立Round 3+4+HTML报告
"""
import sys, os, subprocess, shutil, time

DATE = '20260729'

def run_script(name, timeout=1200):
    path = f'analysis/{name}'
    sep = '=' * 70
    print(f'\n{sep}')
    print(f'  Running: {path}')
    print(sep)
    t0 = time.time()
    result = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout,
                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.stderr:
        print(f'STDERR: {result.stderr[:500]}')
    elapsed = time.time() - t0
    print(f'  耗时: {elapsed:.0f}s (exit={result.returncode})')
    return result.returncode == 0

def generate_html(json_path, html_path):
    v3_json = 'data/deep_reports/all_reports_v3.json'
    bak = v3_json + '.bak'
    if os.path.exists(bak): os.remove(bak)
    if os.path.exists(v3_json): os.rename(v3_json, bak)
    shutil.copy(json_path, v3_json)
    ok = run_script('report_v3_html.py', timeout=300)
    v3_html = 'data/deep_reports/A股科技成长_V3_深度分析.html'
    if os.path.exists(v3_html):
        if os.path.exists(html_path): os.remove(html_path)
        os.rename(v3_html, html_path)
    if os.path.exists(v3_json): os.remove(v3_json)
    if os.path.exists(bak): os.rename(bak, v3_json)
    if os.path.exists(html_path):
        print(f'  [OK] {html_path} ({os.path.getsize(html_path)/1024:.0f} KB)')
    return ok

t_start = time.time()

# ═══════════════════════
# Step 1: Round 2 (输出常规+盈喜两份CSV)
# ═══════════════════════
print('\n' + '#' * 70)
print('#  Round 2: 增长质量+超预期+稳健性 (双轨输出)')
print('#' * 70)
ok = run_script('screen_v4_round2.py')

# ═══════════════════════
# Step 2: 盈喜轨 (独立 Round 3+4+HTML)
# ═══════════════════════
yingxi_input = 'data/screen_v4_round2_yingxi.csv'
yingxi_json = 'data/deep_reports/all_reports_v4_yingxi.json'
yingxi_html = 'data/deep_reports/A股科技成长_V4_盈喜_深度分析.html'

if os.path.exists(yingxi_input):
    print('\n' + '#' * 70)
    print('#  盈喜轨: 业绩盈喜公司独立管线')
    print('#' * 70)

    # Copy yingxi CSV to Round 3 default input location
    r3_default = 'data/screen_v4_round3.csv'
    r3_regular_backup = None
    if os.path.exists(r3_default):
        r3_regular_backup = r3_default + '.regular_bak'
        if os.path.exists(r3_regular_backup): os.remove(r3_regular_backup)
        os.rename(r3_default, r3_regular_backup)
    shutil.copy(yingxi_input, r3_default)

    # Run Round 3 + Round 4
    ok_y = run_script('screen_v4_round3.py', timeout=300)
    if ok_y:
        # Save yingxi Round 3 output before Round 4 overwrites
        yingxi_r3 = 'data/screen_v4_round3_yingxi.csv'
        if os.path.exists(r3_default):
            shutil.copy(r3_default, yingxi_r3)
        ok_y = run_script('screen_v4_round4.py', timeout=600)

    # Generate yingxi HTML
    if os.path.exists(yingxi_json):
        generate_html(yingxi_json, yingxi_html)

    # Restore regular Round 3 if needed
    if os.path.exists(r3_default): os.remove(r3_default)
    if r3_regular_backup and os.path.exists(r3_regular_backup):
        os.rename(r3_regular_backup, r3_default)

# ═══════════════════════
# Step 3: 常规轨 (Round 3+4+HTML)
# ═══════════════════════
r2_regular = 'data/screen_v4_round2.csv'
if os.path.exists(r2_regular):
    print('\n' + '#' * 70)
    print('#  常规轨: Round 3 → Round 4 → HTML')
    print('#' * 70)

    # Copy regular Round 2 to Round 3 input
    if os.path.exists(r3_default):
        r3_old_bak = r3_default + '.old_bak'
        if os.path.exists(r3_old_bak): os.remove(r3_old_bak)
        os.rename(r3_default, r3_old_bak)
    shutil.copy(r2_regular, r3_default)

    ok_r = run_script('screen_v4_round3.py', timeout=300)
    if ok_r:
        ok_r = run_script('screen_v4_round4.py', timeout=600)

    v4_json = 'data/deep_reports/all_reports_v4.json'
    v4_html = 'data/deep_reports/A股科技成长_V4_深度分析.html'
    if os.path.exists(v4_json):
        generate_html(v4_json, v4_html)

total = time.time() - t_start
print(f'\n{"="*70}')
print(f'  V4 双轨管线完成！总耗时: {total:.0f}s')
print(f'  常规轨: {v4_html if os.path.exists("data/deep_reports/A股科技成长_V4_深度分析.html") else "N/A"}')
print(f'  盈喜轨: {yingxi_html if os.path.exists(yingxi_html) else "N/A"}')
print(f'{"="*70}')
