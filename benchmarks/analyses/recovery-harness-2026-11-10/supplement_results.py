from pathlib import Path
from collections import Counter
import hashlib,json
from datetime import datetime
root=Path('/home/yiwei/.codex/outputs/forge-recovery-harness-comparison-flash-v2')
out=Path('/home/yiwei/.codex/outputs/forge-recovery-harness-results-session-2026-11-10-v1')
def read(p):return json.loads(p.read_text())
result=read(root/'result.json');protocol=read(root/'protocol.json');analysis=read(root/'analysis.json')
rows=result['rows'];details=[];containers=set()
expected_harness={k:hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() for k,v in protocol['recovery_harnesses'].items()}
for row in rows:
 folder=root/f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
 attempts=row.get('replay_attempts',[])
 events=[json.loads(line) for line in (folder/'agent/events.jsonl').read_text().splitlines()] if (folder/'agent/events.jsonl').exists() else []
 tools=Counter(e['name'] for e in events if e['event']=='tool.started')
 for p in folder.glob('.compile-sessions/*/*/session.json'):
  session=read(p)
  containers.update(session.get(k) for k in ('container_id','container_name') if session.get(k))
  for a in session.get('replay_attempts',[]):containers.update(a.get(k) for k in ('container_id','container_name') if a.get(k))
 smoke_seconds=0.0
 for wf in folder.glob('.compile-sessions/*/*/logs/workflow.log'):
  for line in wf.read_text().splitlines():
   event=json.loads(line)
   if event.get('event')=='container.exec.completed' and str(event.get('command','')).startswith('/artifacts/'):
    if event.get('started_at') and event.get('completed_at'):
     smoke_seconds+=(datetime.fromisoformat(event['completed_at'])-datetime.fromisoformat(event['started_at'])).total_seconds()
 accepted=[]
 for p in sorted((folder/'agent').glob('simple-actions-*.json')):
  d=read(p);accepted.append({'file':p.relative_to(root).as_posix(),'reason':d['reason'],'steps':[{k:s.get(k) for k in ('step_id','role','command','workdir','requires')} for s in d['steps']]})
 details.append({'slot':row['slot'],'project':row['project'],'method':row['method'],'source_unchanged':row.get('source_unchanged'),'cleanup_succeeded':row.get('cleanup',{}).get('succeeded'),'actual_replay_attempts':len(attempts),'actual_replay_duration_seconds':sum(a.get('duration_seconds',0) or 0 for a in attempts),'original_default_smoke_seconds':smoke_seconds,'actual_replay_statuses':[a['status'] for a in attempts],'layers':row.get('layers',{}),'tools':dict(tools),'harness_selections':[e for e in events if e['event']=='harness.selected'],'harness_selection_matches':all(e['sha256']==expected_harness[row['method']] and e.get('applied') is True for e in events if e['event']=='harness.selected'),'accepted_revisions':accepted})
recovery_sets={method:{r['project'] for r in rows if r['method']==method and r['agent_usage']['model_requests']>0} for method in ('H0','R1')}
summary={'identity':protocol['identity'],'shared_recovery_projects':sorted(recovery_sets['H0'] & recovery_sets['R1']),'asymmetric_recovery_projects':sorted(recovery_sets['H0'] ^ recovery_sets['R1']),'source_analysis_identity_header':analysis['identity'],'source_analysis_identity_header_note':'继承base.analyze常量导致原analysis头仍为v1；protocol/result/manifest及本派生标为实际v2，不修改已封存原件。' if analysis['identity']!=protocol['identity'] else None,'completed_slots':len(rows),'unobserved':len(result['unobserved']),'completed_planning_tasks':len(result['common_initial_plans']),'same_initial_plan_pairs':analysis['pairs'],'by_build_system':analysis['by_build_system'],'details':details,'containers_to_check':sorted(containers),'source_seal':read(root/'seal.json'),'expected_recovery_harness_sha256':expected_harness,'harness_selections_all_match':all(r['harness_selection_matches'] for r in details),'source_result_sha256':hashlib.sha256((root/'result.json').read_bytes()).hexdigest(),'methods':{}}
for method in ('H0','R1'):
 group=[r for r in details if r['method']==method]
 summary['methods'][method]={'actual_replay_attempts':sum(r['actual_replay_attempts'] for r in group),'actual_replay_duration_seconds':sum(r['actual_replay_duration_seconds'] for r in group),'original_default_smoke_seconds':sum(r['original_default_smoke_seconds'] for r in group),'replay_statuses':dict(Counter(s for r in group for s in r['actual_replay_statuses'])),'replay_unobserved_slots':sum(not r['actual_replay_attempts'] for r in group),'source_labels':dict(Counter(str(r['source_unchanged']) for r in group)),'cleanup_labels':dict(Counter(str(r['cleanup_succeeded']) for r in group)),'recovery_tool_calls':dict(sum((Counter(r['tools']) for r in group),Counter()))}
with (out/'results-supplement.json').open('x') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in summary.items() if k not in ('details','containers_to_check','same_initial_plan_pairs')},ensure_ascii=False,indent=2))
