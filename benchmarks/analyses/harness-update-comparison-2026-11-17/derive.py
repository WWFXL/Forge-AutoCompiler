"""从封存原件重建派生表与核对收据；不调用Provider、不修改原件。"""
import csv
import hashlib
import json
import subprocess
import tarfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = Path('/home/yiwei/.codex/outputs/forge-harness-update-comparison-flash-2026-11-17-v1')
OUT = ROOT / 'benchmarks/analyses/harness-update-comparison-2026-11-17'
OUT.mkdir(exist_ok=True, parents=True)
a = json.loads((RAW/'analysis.json').read_text())
r = json.loads((RAW/'result.json').read_text())
assert r['completed_slots'] == r['expected_slots'] == 36
assert r['stop_reason'] is None and r['unclosed_slot'] is None and r['billing_complete']
responses = Counter()
total_in = total_out = 0
refs = set()
source_changes = []
for row in r['rows']:
    folder = RAW / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
    ins = outs = requests = 0
    for f in (folder/'agent').glob('response-*.json'):
        data = json.loads(f.read_text())
        for m in data:
            meta = m['response_metadata']
            responses[meta['model_name']] += 1
            usage = meta['token_usage']
            ins += usage['prompt_tokens']; outs += usage['completion_tokens']; requests += 1
    u = row['agent_usage']
    assert (ins, outs, requests) == (u['input_tokens'], u['output_tokens'], u['model_requests'])
    cost = Decimal(ins)*Decimal('0.30')/1000000 + Decimal(outs)*Decimal('1.20')/1000000
    assert cost == Decimal(str(u['estimated_cost_usd_completed_responses']))
    total_in += ins; total_out += outs
    assert u['unknown_usage_requests'] == 0 and row['cleanup']['succeeded']
    for f in folder.glob('.compile-sessions/simple-system/*/session.json'):
        s = json.loads(f.read_text())
        refs.update(s[k] for k in ('container_id','container_name') if s.get(k))
        for replay in s.get('replay_attempts',[]):
            refs.update(replay[k] for k in ('container_id','container_name') if replay.get(k))
    changes = row.get('source_protection',{}).get('changes',[])
    original = [x['path'] for x in changes if x.get('before') is not None]
    source_changes.append(dict(slot=row['slot'], project=row['project'], method=row['method'], original_input_changes=original, added=sum(x['kind']=='added' for x in changes), source_review=row.get('source_review')))
assert responses == {'deepseek-flash': 245}
present=[]
for ref in sorted(refs):
    c=subprocess.run(['docker','container','inspect',ref],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    if c.returncode == 0: present.append(ref)
    else: assert 'No such container' in c.stderr or 'No such object' in c.stderr, c.stderr
assert not present
seal=json.loads((RAW/'seal.json').read_text())
verification=dict(identity=a['identity'],closed_slots=36,request_responses=dict(responses),input_tokens=total_in,output_tokens=total_out,total_tokens=total_in+total_out,estimated_cost_usd=str(Decimal(total_in)*Decimal('.30')/1000000+Decimal(total_out)*Decimal('1.20')/1000000),unknown_usage_requests=0,billing_recomputed=True,cleanup_passed=36,container_references_checked=len(refs),container_references_present=present,source_changes=source_changes,raw_inventory_canonical_sha256=seal['inventory_canonical_sha256'],raw_result_sha256=hashlib.sha256((RAW/'result.json').read_bytes()).hexdigest(),raw_analysis_sha256=hashlib.sha256((RAW/'analysis.json').read_bytes()).hexdigest())
# 对发生原输入变化的两槽核实作者po更新未改翻译条目。
fixture = json.loads((ROOT/'benchmarks/fixtures/harness-update-comparison-v1/tasks.json').read_text())
source = next(x['source_archive'] for x in fixture['projects'] if x['name']=='libconfuse')
po_checks = []
with tarfile.open(source) as archive:
    for slot in (35, 36):
        folder = next(RAW.glob(f'slot-{slot:02d}-*'))
        workspace = next(folder.glob('.compile-sessions/simple-system/*/workspace/repo'))
        for relative in ('po/de.po','po/fr.po','po/ka.po','po/sv.po'):
            original = archive.extractfile(relative).read().decode()
            current = (workspace/relative).read_text()
            def normalized(text):
                return '\n'.join(line for line in text.splitlines() if not line.startswith('#') and 'POT-Creation-Date:' not in line)
            passed = normalized(original) == normalized(current)
            assert passed
            po_checks.append(dict(slot=slot,path=relative,translation_content_unchanged=passed))
verification['po_translation_checks'] = po_checks
(OUT/'analysis.json').write_bytes((RAW/'analysis.json').read_bytes())
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
fields=['slot','project','method','main_build_completed','reproducible_delivery_completed','initial_requests','recovery_requests','requests','input_tokens','output_tokens','estimated_cost_usd','wall_seconds']
with (OUT/'slots.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for x in a['slots']:
        w.writerow(dict(slot=x['slot'],project=x['project'],method=x['method'],main_build_completed=x['layers']['main_build_task_completed'],reproducible_delivery_completed=x['layers']['reproducible_delivery_completed'],initial_requests=x['phases']['initial']['requests'],recovery_requests=x['phases']['recovery']['requests'],requests=x['usage']['requests'],input_tokens=x['usage']['input_tokens'],output_tokens=x['usage']['output_tokens'],estimated_cost_usd=x['usage']['cost'],wall_seconds=f"{x['wall_seconds']:.6f}"))
table=['| 项目 | 主构建 原/新 | 可复现交付 原/新 | 请求 原/新 | 费用美元 原/新 | 含重建耗时秒 原/新 |','|---|---|---|---|---|---|']
for project in dict.fromkeys(x['project'] for x in a['slots']):
    old,new=sorted([x for x in a['slots'] if x['project']==project],key=lambda x:x['method'])
    def pair(fn):return f'{fn(old)}/{fn(new)}'
    mark=lambda v:'通过' if v else '未完成'
    table.append('| '+project+' | '+pair(lambda x:mark(x['layers']['main_build_task_completed']))+' | '+pair(lambda x:mark(x['layers']['reproducible_delivery_completed']))+' | '+pair(lambda x:x['usage']['requests'])+' | '+pair(lambda x:f"{Decimal(x['usage']['cost']):.6f}")+' | '+pair(lambda x:f"{x['wall_seconds']:.2f}")+' |')
(OUT/'project-table.md').write_text('\n'.join(table)+'\n')
print(json.dumps({k:v for k,v in verification.items() if k!='source_changes'},ensure_ascii=False,indent=2))
