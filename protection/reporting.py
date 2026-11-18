"""Lossless execution rows and per-metric statistics (never weighted scores)."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics
from protection.errors import EvaluationError, InvalidScenarioError
from protection.models import RunRecord, atomic_json, canonical_json, from_data, strict_json_loads, to_data


def read_records(path):
    """Reject incomplete/invalid rows, including an incomplete final JSON line."""
    records = []
    for number, line in enumerate(Path(path).read_text(encoding='utf8').splitlines(),1):
        if not line.strip():
            raise InvalidScenarioError(f'empty JSONL row {number}')
        try:
            records.append(from_data(RunRecord,strict_json_loads(line)))
        except Exception as exc:
            raise InvalidScenarioError(f'invalid JSONL row {number}: {exc}') from exc
    return records


def _row(record, bank):
    row = to_data(record)
    exact = record.condition.method in ('exhaustive','branch_bound')
    ev = (record.best_evaluation if exact else record.submitted_evaluation) if record.status=='completed' else None
    for field in ('connected_pairs','connected_ratio','delivered_mbps','delivery_ratio','delivery_units','cost'):
        row[field] = None if ev is None else getattr(ev,field)
    row['gap_connected_pairs'] = row['gap_delivery_units'] = None
    if ev is not None and record.case_id in bank:
        bundle = bank[record.case_id]
        if (bundle.case_id != record.case_id or bundle.scenario.scenario_id != record.condition.scenario_id
                or bundle.budget != record.condition.budget
                or bundle.budget_percent != record.condition.budget_percent
                or bundle.scenario.evaluation_policy.version != record.policy_version):
            raise EvaluationError('record/reference condition mismatch', reason='reference_mismatch')
        if bundle.optimal_reference is not None:
            reference = bundle.optimal_reference.evaluation
            first = reference.connected_pairs - ev.connected_pairs
            second = reference.delivery_units - ev.delivery_units if first == 0 else None
            if first < 0 or (first == 0 and second < 0):
                raise EvaluationError('score better than reference', reason='reference_mismatch')
            row['gap_connected_pairs'], row['gap_delivery_units'] = first, second
    return row


def _summaries(records, rows):
    groups = defaultdict(list)
    for record,row in zip(records,rows):
        key = (record.case_id,record.condition.method,record.submission_sha256,
               canonical_json(record.environment),record.policy_version,
               canonical_json(record.condition),record.run_kind)
        groups[key].append(row)
    summaries = []
    for key,values in groups.items():
        successful = [r for r in values if r['status']=='completed']
        result = dict(zip(('case_id','method_id','submission_sha256','environment','policy_version',
                           'condition','run_kind'),key))
        result.update(total_count=len(values), success_count=len(successful),
                      status_counts=dict(Counter(r['status'] for r in values)),
                      search_seconds=[r['search_seconds'] for r in values],
                      interpretation='Per-metric statistics; not a single protection plan score')
        for metric in ('connected_ratio','delivery_ratio'):
            scores = [r[metric] for r in successful]
            for suffix,function in (('median',statistics.median),('min',min),('max',max)):
                result[metric+'_'+suffix] = function(scores) if scores else None
        summaries.append(result)
    return summaries


def _csv(path, rows):
    fieldnames = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',newline='',encoding='utf8') as handle:
        writer=csv.DictWriter(handle,fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: canonical_json(value) if isinstance(value,(dict,list,tuple)) else value
                             for key,value in row.items()})


def write_report(records, bank, output_dir):
    """bank maps exact case_id to already-validated ScenarioBundle objects."""
    records=list(records)
    rows=[_row(r,bank) for r in records]
    summaries=_summaries(records,rows)
    report={'runs':rows,'summaries':summaries}
    output=Path(output_dir)
    output.mkdir(parents=True,exist_ok=True)
    atomic_json(output/'report.json',report,overwrite=True)
    _csv(output/'runs.csv',rows)
    _csv(output/'summary.csv',summaries)
    return report
