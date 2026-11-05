"""只读分析两份封存原件；不改终态/来源，复算所有响应并生成论文表。"""
import csv,hashlib,json,sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
REPO=Path('/home/yiwei/work/Forge-AutoCompiler')
sys.path.insert(0,str(REPO/'scripts'))
import forge_base_experience_comparison as run
from forge_typed_evidence import audit
RAW=Path('/home/yiwei/.codex/outputs/forge-base-experience-comparison-v1')
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else REPO/'benchmarks/analyses/base-experience-2026-11-05'
OUT.mkdir(parents=True,exist_ok=False)
(OUT/'analyze.py').write_bytes(Path(__file__).read_bytes())
all_summary={}
for mode in run.MODES:
 raw=RAW/mode
 if not (raw/'seal.json').exists():
  all_summary[mode]=dict(status='not_sealed_or_not_started')
  continue
 seal=audit(raw)
 result=run.shared.load(raw/'result.json');analysis=run.analyze(raw);protocol=run.shared.load(raw/'protocol.json')
 selections=[];receipts=[];rows=[];counts=Counter();total_cost=Decimal(0)
 for row in result['rows']:
  folder=raw/f"slot-{row['slot']:02d}-{row['project']}-{row['method']}"
  detail=next(d for d in analysis['slots'] if d['slot']==row['slot'])
  inputs=outputs=0;cost=Decimal(0);models=Counter()
  for f in sorted((folder/'agent').glob('response-*.json'),key=lambda p:int(p.stem.split('-')[-1])):
   messages=[m for m in run.shared.load(f) if m['type']=='ai'];assert len(messages)==1
   message=messages[0];usage=message['usage_metadata'];model=message['response_metadata']['model_name']
   assert model in run.shared.MODELS and usage['input_tokens']+usage['output_tokens']==usage['total_tokens']
   part=(Decimal('0.30')*usage['input_tokens']+Decimal('1.20')*usage['output_tokens'])/1000000
   inputs+=usage['input_tokens'];outputs+=usage['output_tokens'];cost+=part;models[model]+=1
   receipts.append(dict(slot=row['slot'],response=f.relative_to(raw).as_posix(),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),model=model,input_tokens=usage['input_tokens'],output_tokens=usage['output_tokens'],estimated_cost_usd=str(part)))
  for request_path in sorted((folder/'agent').glob('request-*.json')):
   packet=run.shared.load(request_path)
   for message in packet.get('messages',[]):
    if message.get('type')=='human':
     try: context=json.loads(message['content'])
     except (TypeError,ValueError): continue
     if 'historical_build_experience' in context:
      selections.append(dict(slot=row['slot'],project=row['project'],request=request_path.name,experience=context['historical_build_experience']))
      break
  recorded=run.shared.usage(row)
  assert inputs==recorded['input_tokens'] and outputs==recorded['output_tokens'] and recorded['requests']==sum(models.values())
  assert abs(cost-recorded['cost'])<Decimal('0.000000000001')
  assert cost==sum(map(Decimal,detail['phase_cost_usd'].values()))
  total_cost+=cost;counts.update(dict(requests=sum(models.values()),input_tokens=inputs,output_tokens=outputs))
  layers=row.get('layers',{});timings=row.get('timings',{})
  rows.append(dict(slot=row['slot'],project=row['project'],repetition=row['repetition'],method=row['method'],status=row['status'],initial_plan_available=detail['initial_plan_available'],recipe_selected=detail['recipe_selected'],primary_completed=layers.get('primary_build_completed','unobserved'),author_tests=layers.get('author_tests','unobserved'),delivery=layers.get('delivery','unobserved'),clean_replay=layers.get('clean_replay','unobserved'),full_completed=layers.get('full_completed','unobserved'),source_unchanged=row.get('source_unchanged'),cleanup=row['cleanup']['succeeded'],requests=recorded['requests'],input_tokens=inputs,output_tokens=outputs,estimated_cost_usd=str(cost),wall_seconds=row['arm_total_wall_seconds'],initial_planning_seconds=timings.get('initial_planning_seconds',0),time_to_primary_seconds=timings.get('time_to_primary_from_arm_start_seconds'),initial_requests=detail['phase_requests']['initial'],recovery_requests=detail['phase_requests']['recovery'],initial_cost_usd=detail['phase_cost_usd']['initial'],recovery_cost_usd=detail['phase_cost_usd']['recovery'],source_reads=detail['source_reads'],repeated_source_reads=detail['repeated_source_reads'],experience_retrievals=len(detail['experience_retrievals']),experience_bytes=sum(e['bytes'] for e in detail['experience_retrievals']),format_rejections=detail['format_rejections'],error=row.get('error')))
 pairs=[]
 for repeat in (1,2):
  for project in run.parent.PROJECTS:
   methods={m:next((r for r in rows if r['project']==project and r['repetition']==repeat and r['method']==m),None) for m in run.parent.METHODS}
   pairs.append(dict(project=project,repetition=repeat,**methods))
 for method,summary in analysis['summary'].items():
  selected=[r for r in rows if r['method']==method]
  summary.update(input_tokens=sum(r['input_tokens'] for r in selected),output_tokens=sum(r['output_tokens'] for r in selected),initial_requests=sum(r['initial_requests'] for r in selected),initial_cost_usd=str(sum((Decimal(r['initial_cost_usd']) for r in selected),Decimal(0))),recovery_cost_usd=str(sum((Decimal(r['recovery_cost_usd']) for r in selected),Decimal(0))),experience_retrievals=sum(r['experience_retrievals'] for r in selected),experience_bytes=sum(r['experience_bytes'] for r in selected),primary_time_seconds=sum(r['time_to_primary_seconds'] or 0 for r in selected))
  summary['layer_counts']={layer:dict(Counter(str(r.get('layers',{}).get(layer,'unobserved')) for r in result['rows'] if r['method']==method)) for layer in ('primary_build_completed','author_tests','delivery','clean_replay','full_completed')}
 sub=OUT/mode;sub.mkdir()
 with (sub/'slots.csv').open('w') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 run.save(sub/'analysis.json',analysis);run.save(sub/'pairs.json',pairs);run.save(sub/'experience-contexts.json',selections)
 run.save(sub/'response-verification.json',dict(valid=True,identity=protocol['identity'],**counts,total_tokens=counts['input_tokens']+counts['output_tokens'],estimated_cost_usd=str(total_cost),unknown_usage_requests=sum(run.shared.usage(r)['unknown'] for r in result['rows']),responses=receipts))
 all_summary[mode]=dict(identity=protocol['identity'],completed=result['completed_slots'],unobserved=len(result['unobserved']),stop_reason=result['stop_reason'],inventory=seal['inventory_canonical_sha256'],summary=analysis['summary'],cost_usd=str(total_cost),**counts)
run.save(OUT/'summary.json',all_summary)
print(json.dumps(all_summary,ensure_ascii=False,indent=2))
