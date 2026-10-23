#!/usr/bin/env python3
"""Focused policy boundaries and tampering checks on an actual saved native run."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import ast
import re
import contextlib
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from search_policy import DEFAULT_PROTOCOL, load_memory_bytes, next_action, shards
from audit.evidence import audit_phase
from audit.primitives import GiB, inspect_budget, sha
from capacity_controller import database_name, prepare


def main():
    checks = []
    def check(name, condition):
        assert condition, name
        checks.append({'check': name, 'pass': True})

    helper_source = Path('/private/tmp/multicore-research-20261022/lab-target-control-v2.py').read_text()
    helper_tree = ast.parse(helper_source)
    function = next(node for node in helper_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'dbid')
    namespace = {'re': re}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<frozen-lifecycle-dbid>', 'exec'), namespace)
    for index in [1, 3, 999]:
        name = database_name('capacity_20261023t123456_abcdef', index)
        check(f'database{index}:accepted_by_unmodified_lifecycle_guard', namespace['dbid'](name) == name)
    controller_tree = ast.parse(Path(__file__).resolve().parents[1].joinpath('capacity_controller.py').read_text())
    complete_events = [node for node in ast.walk(controller_tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Attribute) and node.func.attr == 'event'
                       and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'phase_complete']
    check('one_phase_complete_event_callsite', len(complete_events) == 1)

    for users in [10, 10000, 20000, 20001, 80000, 100001, 120000, 160000]:
        allocation = shards(users)
        check(f'{users}:disjoint_complete_shards', sum(s['users'] for s in allocation) == users
              and max(s['users'] for s in allocation) <= 20000 and len(allocation) <= 8
              and [s['id_offset'] for s in allocation] == [sum(a['users'] for a in allocation[:i]) for i in range(len(allocation))])
    def simulate(probe_limit, hold_limit=None, invalid_at=None):
        history = []
        for _ in range(1 + DEFAULT_PROTOCOL['max_probes'] + DEFAULT_PROTOCOL['max_holds'] + 1):
            action = next_action(history)
            if action['stage'] == 'stop':
                return history, action
            stage, users = action['stage'], action['users']
            limit = hold_limit if stage == 'hold' and hold_limit is not None else probe_limit
            classification = 'INVALID_GENERATOR' if invalid_at == users and stage == 'probe' else 'PASS' if users <= limit else 'FAIL_SLO'
            history.append({'id': str(len(history)), 'stage': stage, 'users': users, 'classification': classification})
        raise AssertionError('search did not terminate within its finite budget')
    history, end = simulate(65000)
    check('capacity_search_brackets_then_holds', end['reason'] == 'HOLD_PASSED' and end['users'] == 65000
          and all(p['users'] <= 160000 for p in history))
    history, end = simulate(999999)
    check('ceiling_pass_is_a_hold_at_ceiling_without_invented_failure', end.get('users') == 160000
          and not any(p['classification'] == 'FAIL_SLO' for p in history))
    history, end = simulate(1000)
    check('initial_failure_halves_until_low_pass', end['reason'] == 'HOLD_PASSED' and end['users'] <= 1000)
    history, end = simulate(65000, hold_limit=1)
    check('four_failed_holds_stop_finitely', end['reason'] == 'HOLD_BUDGET_EXHAUSTED'
          and sum(p['stage'] == 'hold' for p in history) == 4)
    history, end = simulate(65000, invalid_at=80000)
    check('generator_invalid_stops_without_failure_bracket_or_hold', end['reason'] == 'INVALID_GENERATOR'
          and not any(p['stage'] == 'hold' for p in history) and history[-1]['classification'] != 'FAIL_SLO')
    clock = [{'id': 'clock', 'stage': 'warmup', 'users': 10000, 'classification': 'INVALID_CLOCK'}]
    check('clock_invalid_never_becomes_server_failure', next_action(clock)['reason'] == 'INVALID_CLOCK')
    p80 = copy.deepcopy(DEFAULT_PROTOCOL); p80['start_users'] = 80000
    first = next_action([], p80)
    second = next_action([{'id': 'warm', 'stage': 'warmup', 'users': 10000, 'classification': 'PASS'}], p80)
    check('declared80k_probe_start_preserves10k_warmup', first == {'stage': 'warmup', 'users': 10000}
          and second == {'stage': 'probe', 'users': 80000})
    rounded = [{'id': 'warm', 'stage': 'warmup', 'users': 10000, 'classification': 'PASS'},
               {'id': 'lo', 'stage': 'probe', 'users': 150000, 'classification': 'PASS'},
               {'id': 'hi', 'stage': 'probe', 'users': 160000, 'classification': 'FAIL_SLO'}]
    check('150k_pass160k_fail_probes_strict155k_midpoint', next_action(rounded)['users'] == 155000
          and next_action(rounded)['stage'] == 'probe')
    rounded.append({'id': 'mid', 'stage': 'probe', 'users': 155000, 'classification': 'PASS'})
    check('155k_pass160k_fail_then_holds_resolved_interval', next_action(rounded) == {
          'stage': 'hold', 'users': 155000, 'probe_upper_fail': 160000})
    exhausted = copy.deepcopy(DEFAULT_PROTOCOL); exhausted['max_probes'] = 2
    check('rounding_fallback_does_not_exceed_finite_probe_budget', next_action(rounded[:3], exhausted) == {
          'stage': 'hold', 'users': 150000, 'probe_budget_exhausted': True})

    old = Path('/private/tmp/multicore-research-20261022/paired-multi-load-v3/v3_multi_pair_20261022t200445_706372')
    source = old / '01-p1-rust7'
    old_plan = json.loads((old / 'plan.json').read_text())
    case = old_plan['configuration']['cases'][0]
    initial = json.loads((old / 'target-initial.json').read_text())
    plan = {'configuration': old_plan['configuration'], 'protocol': DEFAULT_PROTOCOL}
    prior = json.loads((source / 'assessment.json').read_text())
    raw0 = json.loads((source / 'box0.json').read_text())
    load_inspect = json.loads((old / 'load-inspect.json').read_text())
    target_inspect = json.loads((old / 'target-inspect.json').read_text())
    eight_inspect = copy.deepcopy(load_inspect)
    eight_inspect['HostConfig']['Memory'] = eight_inspect['HostConfig']['MemorySwap'] = 8 * GiB
    check('actual_inspector_accepts_declared8GiB_only', inspect_budget(eight_inspect, 4, 8 * GiB)
          and not inspect_budget(eight_inspect, 4, 4 * GiB))
    eight_inspect['HostConfig']['MemorySwap'] = 16 * GiB
    check('actual_inspector_rejects_swap_allowance_above8GiB', not inspect_budget(eight_inspect, 4, 8 * GiB))
    check('server_budget_stays8CPU16GiB', inspect_budget(target_inspect, 8, 16 * GiB)
          and not inspect_budget(target_inspect, 4, 8 * GiB))
    with tempfile.TemporaryDirectory(prefix='capacity-audit-', dir=Path(__file__).resolve().parent) as temporary:
        directory = Path(temporary)
        for name in ['before-load.json', 'after-load.json', 'target-monitor.jsonl', 'load-monitor.jsonl', 'merged.json', 'load-commands.json', *[f'box{i}.json' for i in range(4)]]:
            (directory / name).symlink_to(source / name)
        state = {'id': directory.name, 'case': case['name'], 'stage': 'probe', 'users': 80000,
                 'shards': shards(80000), 'database': prior['database'], 'session_id': source.name,
                 'run_id': raw0['meta']['run_id'], 'load_exits': [0] * 4, 'merge_exit': prior['merge_exit']}
        (directory / 'phase.json').write_text(json.dumps(state))
        baseline = audit_phase(directory, source, plan, case, initial)
        check('actual_saved_four_shard_run_independently_passes', baseline['classification'] == 'PASS')
        def replace(name, value):
            path = directory / name
            path.unlink()
            path.write_text(json.dumps(value))
        def restore(name):
            path = directory / name
            path.unlink()
            path.symlink_to(source / name)
        eight_plan = copy.deepcopy(plan)
        eight_plan['configuration']['load_memory_bytes'] = eight_plan['protocol']['load_memory_bytes'] = 8 * GiB
        rows = [json.loads(line) for line in (source / 'load-monitor.jsonl').read_text().splitlines()]
        for row in rows:
            row['memory.max'] = str(8 * GiB)
        path = directory / 'load-monitor.jsonl'; path.unlink(); path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        audited_eight = audit_phase(directory, source, eight_plan, case, initial)
        check('phase_audit_accepts_observed8GiB_with_matching_explicit_plan', audited_eight['classification'] == 'PASS'
              and audited_eight['declared_load_memory_bytes'] == 8 * GiB)
        check('phase_audit_rejects_observed8GiB_against4GiB_plan', audit_phase(directory, source, plan, case, initial)['classification'] == 'INVALID_MONITOR')
        restore('load-monitor.jsonl')
        check('phase_audit_rejects_declared8GiB_with_observed4GiB', audit_phase(directory, source, eight_plan, case, initial)['classification'] == 'INVALID_MONITOR')
        mismatched = copy.deepcopy(eight_plan); mismatched['configuration']['load_memory_bytes'] = 4 * GiB
        check('config_protocol_memory_mismatch_rejected', audit_phase(directory, source, mismatched, case, initial)['classification'] == 'INVALID_EVIDENCE')
        prepare_checks = []
        for memory in [4 * GiB, 8 * GiB, 6 * GiB]:
            config = {'cases': [copy.deepcopy(case)], 'load_memory_bytes': memory, 'search_overrides': {'start_users': 80000}}
            config_path, plan_path = directory / f'config-{memory}.json', directory / f'plan-{memory}.json'
            config_path.write_text(json.dumps(config))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    prepare(config_path, plan_path)
                receipt = json.loads(plan_path.read_text())
                accepted = (receipt['configuration']['load_memory_bytes'] == receipt['protocol']['load_memory_bytes'] == memory
                            and receipt['protocol']['target_memory_bytes'] == 16 * GiB and receipt['protocol']['load_cpus'] == 4
                            and receipt['protocol']['start_users'] == 80000 and receipt['protocol']['warmup_users'] == 10000
                            and receipt['source_config_sha256'] == sha(config_path))
                overwrite_rejected = False
                try:
                    prepare(config_path, plan_path)
                except FileExistsError:
                    overwrite_rejected = True
                check(f'prepare_explicit{memory // GiB}GiB_receipt_and_immutable_plan', accepted and overwrite_rejected)
                prepare_checks.append({'memory': memory, 'source_config_sha256': sha(config_path), 'plan_sha256': sha(plan_path)})
            except ValueError:
                check('prepare_rejects_unsupported6GiB_before_writing_plan', memory == 6 * GiB and not plan_path.exists())
        default_config = directory / 'config-default.json'; default_config.write_text(json.dumps({'cases': [copy.deepcopy(case)]}))
        default_plan = directory / 'plan-default.json'
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(default_config, default_plan)
        check('prepare_default4GiB_preserves_historical_budget', json.loads(default_plan.read_text())['protocol']['load_memory_bytes'] == 4 * GiB)
        bad = json.loads((source / 'before-load.json').read_text())
        bad['actual_app']['processes'][0]['proc_limits'] = bad['actual_app']['processes'][0]['proc_limits'].replace('200000', '1024')
        replace('before-load.json', bad)
        check('raw1024_limit_rejected_even_if_helper_valid_true', audit_phase(directory, source, plan, case, initial)['classification'] == 'INVALID_EVIDENCE')
        restore('before-load.json')
        bad = json.loads((source / 'merged.json').read_text()); bad['overall']['rps'] *= 5
        replace('merged.json', bad)
        check('false_merged_rps_rejected', audit_phase(directory, source, plan, case, initial)['classification'] == 'INVALID_EVIDENCE')
        restore('merged.json')
        bad = json.loads((source / 'box0.json').read_text()); bad['box']['fell_behind'] = True
        replace('box0.json', bad)
        merged = json.loads((source / 'merged.json').read_text()); merged['verdict']['lg_limited'] = True
        replace('merged.json', merged)
        check('native_generator_limit_never_yields_score', audit_phase(directory, source, plan, case, initial)['classification'] == 'INVALID_GENERATOR')
        restore('box0.json'); restore('merged.json')
        rows = [json.loads(line) for line in (source / 'target-monitor.jsonl').read_text().splitlines()]
        for row in rows[len(rows) // 2:]:
            row['wall_ns'] += 3600 * 10**9
        path = directory / 'target-monitor.jsonl'; path.unlink(); path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        check('wall_clock_jump_never_yields_server_failure', audit_phase(directory, source, plan, case, initial)['classification'] == 'INVALID_CLOCK')
    out = Path(__file__).with_name('test-proof.json')
    out.write_text(json.dumps({'pass': True, 'checks': checks, 'prepare_receipts': prepare_checks,
                              'docker_or_benchmark_execution': False}, indent=2) + '\n')
    print(json.dumps({'pass': True, 'checks': len(checks), 'proof': str(out)}))


if __name__ == '__main__':
    main()
