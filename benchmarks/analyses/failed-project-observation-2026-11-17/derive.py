"""从本轮封存结果生成三项目表，独立保存后审，不修改原件。"""
import difflib
import hashlib
import json
import subprocess
import tarfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = Path('/home/yiwei/.codex/outputs/forge-failed-project-observation-flash-2026-11-17-v1')
OUT = Path(__file__).resolve().parent
result = json.loads((RAW / 'result.json').read_text())
analysis = json.loads((RAW / 'analysis.json').read_text())
protocol = json.loads((RAW / 'protocol.json').read_text())
rows, reviews, refs = [], [], set()
for row in result['rows']:
    folder = RAW / f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
    events = [json.loads(l) for l in (folder / 'agent/events.jsonl').read_text().splitlines()]
    ins = outs = requests = 0
    for response in (folder / 'agent').glob('response-*.json'):
        for message in json.loads(response.read_text()):
            assert message['response_metadata']['model_name'] == 'deepseek-flash'
            usage = message['response_metadata']['token_usage']
            ins += usage['prompt_tokens']
            outs += usage['completion_tokens']
            requests += 1
    meter = row['agent_usage']
    assert (ins, outs, requests) == (meter['input_tokens'], meter['output_tokens'], meter['model_requests'])
    cost = (Decimal(ins) * Decimal('.30') + Decimal(outs) * Decimal('1.20')) / 1_000_000
    assert cost == Decimal(str(meter['estimated_cost_usd_completed_responses']))
    assert meter['unknown_usage_requests'] == 0 and row['cleanup']['succeeded']
    errors = [e for e in events if e['event'] == 'tool.completed' and e.get('result', {}).get('status') == 'error']
    rows.append(dict(project=row['project'], status=row['status'], layers=row.get('layers', {}), requests=requests, input_tokens=ins, output_tokens=outs, cost_usd=str(cost), wall_seconds=row['arm_total_wall_seconds'], proposal_rejections=[e for e in events if e['event'] == 'simple.proposal_rejected'], tool_errors=errors, error=row.get('error'), cleanup=row['cleanup']))
    session_file = next(folder.glob('.compile-sessions/simple-system/*/session.json'))
    session = json.loads(session_file.read_text())
    for container in [session, *session.get('replay_attempts', [])]:
        refs.update(container[k] for k in ('container_id', 'container_name') if container.get(k))
    workspace = session_file.parent / 'workspace/repo'
    originals = [c for c in row.get('source_protection', {}).get('changes', []) if c.get('before') is not None]
    project = next(p for p in protocol['projects'] if p['name'] == row['project'])
    with tarfile.open(project['source_archive']) as archive:
        members = {m.name.removeprefix('./').removeprefix('repo/'): m for m in archive.getmembers()}
        for change in originals:
            path = change['path']
            member = members.get(path)
            old = archive.extractfile(member).read() if member and member.isfile() else b''
            current = workspace / path
            new = current.read_bytes() if current.is_file() and not current.is_symlink() else b''
            diff = ''.join(difflib.unified_diff(old.decode(errors='replace').splitlines(True), new.decode(errors='replace').splitlines(True), fromfile='original/' + path, tofile='observed/' + path))
            assessment = 'needs_manual_review'
            if row['project'] == 'libtasn1' and path == 'fuzz/corpus2array.c':
                assert new.replace(b'#include <config.h>\n', b'', 1) == old
                assessment = '辅助生成程序仅增加config.h包含，属构建适配；未更改核心逻辑或测试含义'
            reviews.append(dict(project=row['project'], path=path, kind=change['kind'], assessment=assessment, original_sha256=hashlib.sha256(old).hexdigest(), observed_sha256=hashlib.sha256(new).hexdigest(), diff=diff))
for ref in sorted(refs):
    check = subprocess.run(['docker', 'container', 'inspect', ref], capture_output=True, text=True)
    assert check.returncode != 0 and ('No such container' in check.stderr or 'No such object' in check.stderr)
seal = json.loads((RAW / 'seal.json').read_text())
verification = dict(identity=protocol['identity'], observed=len(rows), planned=3, input_tokens=sum(r['input_tokens'] for r in rows), output_tokens=sum(r['output_tokens'] for r in rows), requests=sum(r['requests'] for r in rows), cost_usd=str(sum((Decimal(r['cost_usd']) for r in rows), Decimal(0))), unknown_usage_requests=0, cleanup_passed=len(rows), absent_container_references=len(refs), inventory_sha256=seal['inventory_canonical_sha256'], original_input_changes=len(reviews))
for name, data in [('analysis.json', analysis), ('verification.json', verification), ('slots.json', rows), ('source-review.json', reviews)]:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(verification, ensure_ascii=False))
