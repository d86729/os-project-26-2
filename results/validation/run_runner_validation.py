"""Serial tiny smoke evidence. All submissions below are validation doubles only."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from protection.runner import run_submission, collect_environment
from protection.models import Scenario, ScenarioBundle, Node, Edge, Demand, to_data


def main():
    output=Path('results/validation')
    tests=['tests/contract/test_member_contract.py','tests/integration/test_worker_timing.py',
        'tests/integration/test_worker_memory.py','tests/integration/test_submission_failures.py',
        'tests/integration/test_repeat_isolation.py','tests/unit/test_context_transport.py']
    command=[sys.executable,'-m','pytest',*tests,'-q','--junitxml=results/validation/runner-focused.xml']
    result=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (output/'runner-focused.txt').write_text(result.stdout)
    print(result.stdout,flush=True)
    s=Scenario(nodes=(Node(0,.1,.1),Node(1,.5,.1),Node(2,.9,.1)),
        edges=(Edge(0,0,1,10,4),Edge(1,1,2,10,6)),
        demands=(Demand(0,0,2,10),Demand(1,0,1,10),Demand(2,2,0,10)),seed=0)
    b=ScenarioBundle(s,40,4)
    records=[]
    examples=[('completed','class Submission:\n def solve(self,s,b,c):\n  c.evaluate([0])\n  return []',{}),
        ('timeout','import time\nclass Submission:\n def solve(self,s,b,c):\n  c.evaluate([])\n  time.sleep(3)',{'limit_seconds':.4}),
        ('memory_limit','import time\nclass Submission:\n def solve(self,s,b,c):\n  c.evaluate([])\n  x=bytearray(100_000_000)\n  time.sleep(3)',{'memory_limit_bytes':80_000_000}),
        ('memory_limit','class Submission:\n def solve(self,s,b,c): return []',{'_evaluation_allocation_bytes':100_000_000,'memory_limit_bytes':80_000_000})]
    with tempfile.TemporaryDirectory() as directory:
        file=Path(directory)/'submission.py'
        for expected,source,options in examples:
            file.write_text(source)
            r=run_submission(b,file,'Submission',**({'limit_seconds':2}|options))
            records.append({'expected_status':expected,'matches':r.status==expected,'record':to_data(r)})
            print(expected,r.status,r.search_seconds,r.algorithm_peak_rss_bytes,r.evaluation_peak_rss_bytes,flush=True)
    report=dict(kind='US3 single-worker direct-evaluation smoke verification',command=command,exit_code=result.returncode,
        environment=collect_environment(),pytest_summary=ET.parse(output/'runner-focused.xml').getroot()[0].attrib,
        test_records=records,all_passed=result.returncode==0 and all(x['matches'] for x in records),
        caveats=['Test-only short deadlines and low memory limits, not team performance.',
                 'Whole-worker RSS includes evaluator, LP and cache; no evaluation process.',
                 'Linux RSS sampling is observational, not a continuous hard limit.',
                 'Final score is outside algorithm deadline; no main/long experiment ran.'])
    (output/'runner.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    return 0 if report['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
