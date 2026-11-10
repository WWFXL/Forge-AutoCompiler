from pathlib import Path
from collections import Counter
from decimal import Decimal
import json,csv,sys
root=Path('/home/yiwei/.codex/outputs/forge-recovery-harness-comparison-flash-v2')
out=Path('/home/yiwei/.codex/outputs/forge-recovery-harness-results-session-2026-11-10-v1')
def read(p):return json.loads(p.read_text())
def cost(r):return Decimal(str(r['agent_usage']['estimated_cost_usd_completed_responses']))
result=read(root/'result.json')
rows=result['rows'];plans={r['project']:r for r in result['common_initial_plans']}
protocol=read(root/'protocol.json')
by_name={r['name']:r for r in protocol['projects']}
details=[];response_totals=Counter();all_ids=[]
for folder in list((root/'initial').iterdir())+list(root.glob('slot-*')):
 for response_path in (folder/'agent').glob('response-*.json'):
  messages=read(response_path)
  for message in messages if isinstance(messages,list) else [messages]:
   usage=message.get('usage_metadata')
   if not usage:continue
   response_totals['requests']+=1
   response_totals['input_tokens']+=usage['input_tokens']
   response_totals['output_tokens']+=usage['output_tokens']
   response_totals['unknown_model']+=message.get('response_metadata',{}).get('model_name') not in protocol['provider']['accepted_models']
   all_ids.append(message.get('id'))
for row in rows:
 folder=root/f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
 events_path=folder/'agent/events.jsonl'
 events=[json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
 counts=Counter();seen=set()
 for event in events:
  if event['event']=='agent.started':counts['recovery_invocations']+=bool(event.get('recovery'))
  if event['event']=='tool.started' and event.get('name') in ('read_source','list_source'):
   key=(event['name'],json.dumps(event.get('args',{}),sort_keys=True))
   counts[event['name']]+=1;counts['exact_repeat_reads']+=key in seen;seen.add(key)
 handoffs=[]
 for p in sorted(folder.glob('.compile-sessions/*/*/build-plan/handoff-*.json')):
  h=read(p);handoffs.append({'file':p.relative_to(root).as_posix(),'reason':h.get('reason'),'step_id':h.get('step_id')})
 details.append({'slot':row['slot'],'project':row['project'],'method':row['method'],'system':by_name[row['project']]['task']['build_system'],'status':row['status'],'layers':row.get('layers',{}),'requests':row['agent_usage']['model_requests'],'input_tokens':row['agent_usage']['input_tokens'],'output_tokens':row['agent_usage']['output_tokens'],'online_recovery_cost_usd':str(cost(row)),'execution_wall_seconds':row.get('arm_total_wall_seconds'),'timings':row.get('timings'),'events':dict(counts),'handoffs':handoffs,'error':row.get('error'),'state_routing':row.get('router_usage'),'initial_plan_sha256':row['initial_plan_sha256']})
methods={}
for method in ('H0','R1'):
 group=[r for r in rows if r['method']==method];diag=[r for r in details if r['method']==method]
 layers={key:{'passed':sum(r.get('layers',{}).get(key) is True for r in group),'failed':sum(r.get('layers',{}).get(key) is False for r in group),'unobserved':sum(r.get('layers',{}).get(key) is None for r in group)} for key in ('command_build_passed','primary_build_completed','final_verification_passed','main_build_task_completed','reproducible_delivery_completed')}
 planning=sum((cost(r) for r in plans.values()),Decimal(0));recovery=sum((cost(r) for r in group),Decimal(0))
 methods[method]={'planned':18,'observed':len(group),'layers':layers,'initial_requests':sum(r['agent_usage']['model_requests'] for r in plans.values()),'recovery_requests':sum(r['agent_usage']['model_requests'] for r in group),'recovery_projects':[r['project'] for r in diag if r['requests']>0],'initial_cost_usd':str(planning),'recovery_cost_usd':str(recovery),'deployment_cost_usd':str(planning+recovery),'execution_wall_seconds':sum(r['arm_total_wall_seconds'] for r in group),'common_planning_wall_seconds':sum(r['arm_total_wall_seconds'] for r in plans.values()),'deployment_wall_seconds':sum(r['arm_total_wall_seconds'] for r in group+list(plans.values())),'recovery_agent_seconds':sum(r.get('timings',{}).get('recovery_agent_seconds',0) for r in group),'events':dict(sum((Counter(d['events']) for d in diag),Counter()))}
expected_input=sum(r['agent_usage']['input_tokens'] for r in rows+list(plans.values()));expected_output=sum(r['agent_usage']['output_tokens'] for r in rows+list(plans.values()))
computed_cost=(Decimal(response_totals['input_tokens'])*Decimal('0.30')+Decimal(response_totals['output_tokens'])*Decimal('1.20'))/1_000_000
summary={'methods':methods,'details':details,'response_verification':dict(response_totals)|{'ledger_input_tokens':expected_input,'ledger_output_tokens':expected_output,'tokens_match':expected_input==response_totals['input_tokens'] and expected_output==response_totals['output_tokens'],'unique_response_ids':len(set(all_ids)),'recomputed_cost_usd':str(computed_cost),'ledger_known_cost_usd':result['known_actual_batch_cost_usd']},'stop_reason':result['stop_reason'],'billing_complete':result['billing_complete'],'unobserved':result['unobserved'],'parent_planning_imported_once':protocol['parent_scope']}
with (out/'results-derived.json').open('x') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
columns=('slot','project','system','method','status','requests','online_recovery_cost_usd','execution_wall_seconds','main_build_completed','reproducible_delivery_completed')
with (out/'results-by-slot.csv').open('x',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
 for row in details:writer.writerow({k:row[k] for k in columns if k in row}|{'main_build_completed':row['layers'].get('main_build_task_completed'),'reproducible_delivery_completed':row['layers'].get('reproducible_delivery_completed')})
print(json.dumps({'methods':methods,'response_verification':summary['response_verification'],'stop_reason':result['stop_reason']},ensure_ascii=False,indent=2))
