"""시나리오 생성, 참조 계산, 제출 채점과 보고서를 연결하는 로컬 CLI다."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys


def parser():
    p=argparse.ArgumentParser(prog='protection',description='Network protection research CLI v1')
    commands=p.add_subparsers(dest='command',required=True)
    for name in ('generate','grade','scale-probe'):
        q=commands.add_parser(name);q.add_argument('--manifest',required=True)
    q=commands.add_parser('exact')
    q.add_argument('--input',required=True);q.add_argument('--budget-percent',required=True,type=int,choices=(20,40))
    q.add_argument('--method',required=True,choices=('exhaustive','branch_bound'))
    q.add_argument('--run-kind',required=True,choices=('smoke','main','scale_probe'))
    q.add_argument('--manifest');q.add_argument('--limit-seconds',type=float);q.add_argument('--output',required=True)
    q=commands.add_parser('bundle')
    q.add_argument('--input',required=True);q.add_argument('--exact-record',required=True);q.add_argument('--output',required=True)
    q=commands.add_parser('validate')
    q.add_argument('--bundle',required=True);q.add_argument('--require-reference',action='store_true')
    q=commands.add_parser('input')
    q.add_argument('--bundle',required=True)
    q=commands.add_parser('report')
    q.add_argument('--records',required=True);q.add_argument('--bank-manifest',required=True);q.add_argument('--output-dir',required=True)
    return p


def load_manifest(path,kind):
    from protection.models import ExperimentManifest,strict_json_loads,require
    manifest=ExperimentManifest.parse(strict_json_loads(Path(path).read_text()),path)
    d=manifest.to_dict()
    require(d['kind']==kind,f'{kind} manifest required')

    return manifest


def load_bank(manifest):
    from protection.models import load_bundle,require
    bank={}
    for entry in manifest.to_dict()['bank']:
        b=load_bundle(entry['path'],require_reference=manifest.to_dict()['run_kind']=='main')
        require(b.case_id==entry['case_id'],'bank case_id does not match saved bundle')
        bank[b.case_id]=b
    return bank


def execute(args):
    from protection.models import (atomic_json,canonical_json,load_scenario,save_scenario,
        RunRecord,from_data,strict_json_loads,bundle_from_record,save_bundle,load_bundle,require)
    from protection.runner import collect_environment
    if args.command=='generate':
        manifest=load_manifest(args.manifest,'preparation');d=manifest.to_dict()
        from protection.generation import generate_scenario
        output=Path(d['output_dir'])
        targets=[(n,seed,output/'inputs'/f'n{n}-seed{seed}.json')
                 for n in d['sizes'] for seed in d['seeds_by_size'][str(n)]]
        require(not any(path.exists() for _,_,path in targets),'input already exists; refusing overwrite')
        require(not (output/'environment.json').exists(),'environment already exists; refusing overwrite')
        for n,seed,path in targets:
            save_scenario(generate_scenario(n,seed),path)
        atomic_json(output/'environment.json',collect_environment())
        print(canonical_json({'inputs':[str(p) for _,_,p in targets],'artifact_kind':'scenario_input'}))
    elif args.command=='exact':
        manifest=None
        if args.run_kind=='smoke':
            require(args.manifest is None,'--manifest is reserved for authorized main/scale_probe exact runs')
        else:
            require(args.manifest is not None,'main/scale_probe requires --manifest')
            require(args.limit_seconds is None,'limit override is allowed only for smoke')
            manifest=load_manifest(args.manifest,'preparation')
            require(manifest.to_dict()['run_kind']==args.run_kind,'run_kind does not match manifest')
        require(not Path(args.output).exists(),'output already exists; refusing overwrite')
        from protection.exact import search
        record=search(load_scenario(args.input),args.budget_percent,method=args.method,
                      limit_seconds=args.limit_seconds,run_kind=args.run_kind,manifest=manifest)
        atomic_json(args.output,record)
        print(canonical_json({'status':record.status,'output':args.output}))
        return 0 if record.status=='completed' else 1
    elif args.command=='scale-probe':
        from protection.operations import run_scale_probe
        summary=run_scale_probe(load_manifest(args.manifest,'preparation'))
        print(canonical_json(summary))
        return 0 if summary['complete'] else 1
    elif args.command=='bundle':
        record=from_data(RunRecord,strict_json_loads(Path(args.exact_record).read_text()))
        b=bundle_from_record(load_scenario(args.input),record)
        save_bundle(b,args.output)
        print(canonical_json({'case_id':b.case_id,'output':args.output}))
    elif args.command=='validate':
        b=load_bundle(args.bundle,require_reference=args.require_reference)
        print(canonical_json({'valid':True,'case_id':b.case_id,'has_reference':b.optimal_reference is not None}))
    elif args.command=='input':
        from protection.program import scenario_input
        sys.stdout.buffer.write(scenario_input(load_bundle(args.bundle)))
    elif args.command=='grade':
        manifest=load_manifest(args.manifest,'grading')
        load_bank(manifest)  # 제출 프로그램을 실행하기 전에 모든 사례 파일을 검증한다.
        from protection.runner import grade_manifest
        output=Path(manifest.to_dict()['output_dir'])
        require(not any((output/name).exists() for name in ('runs.jsonl','batch.json','environment.json')),
                'grading output already exists; choose a fresh output_dir')
        records=grade_manifest(manifest)
        output.mkdir(parents=True,exist_ok=True)
        with (output/'runs.jsonl').open('x',encoding='utf-8') as handle:
            for record in records:
                handle.write(canonical_json(record)+'\n')
                handle.flush()
        atomic_json(output/'environment.json',collect_environment())
        atomic_json(output/'batch.json',{'schema_version':1,'run_kind':manifest.to_dict()['run_kind'],
            'record_count':len(records),'statuses':[r.status for r in records],
            'manifest':manifest.to_dict()})
        print(canonical_json({'statuses':[r.status for r in records],'output_dir':str(output)}))
        return 0 if records and all(r.status=='completed' for r in records) else 1
    elif args.command=='report':
        manifest=load_manifest(args.bank_manifest,'grading');bank=load_bank(manifest)
        from protection.reporting import read_records,write_report
        records=read_records(args.records)
        require(bool(records),'empty records')
        require(all(r.case_id in bank for r in records),'record case_id absent from bank')
        write_report(records,bank,args.output_dir)
        print(canonical_json({'output_dir':args.output_dir,'record_count':len(records)}))
    return 0


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        # Must precede even indirect NumPy/SciPy imports. Help exits above.
        from protection.runner import initialize_single_thread
        initialize_single_thread()
        return execute(args)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,ImportError) as exc:
        print(json.dumps({'error':type(exc).__name__,'message':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
