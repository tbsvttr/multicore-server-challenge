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
from search_policy import DEFAULT_PROTOCOL, growth_factor, load_cpus, load_memory_bytes, next_action, shards
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
    def simulate(probe_limit, hold_limit=None, invalid_at=None, protocol=DEFAULT_PROTOCOL):
        history = []
        for _ in range(1 + protocol['max_probes'] + protocol['max_holds'] + 1):
            action = next_action(history, protocol)
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
    p160 = copy.deepcopy(DEFAULT_PROTOCOL); p160['start_users'] = 160000
    warm160 = [{'id': 'warm', 'stage': 'warmup', 'users': 10000, 'classification': 'PASS'}]
    check('declared160k_probe_start_still_warms_at10k', next_action([], p160)['users'] == 10000
          and next_action(warm160, p160) == {'stage': 'probe', 'users': 160000})
    warm160.append({'id': 'high', 'stage': 'probe', 'users': 160000, 'classification': 'FAIL_SLO'})
    check('valid160k_failure_halves_to_fresh80k_probe', next_action(warm160, p160) == {'stage': 'probe', 'users': 80000})
    gradual = copy.deepcopy(DEFAULT_PROTOCOL); gradual['start_users'] = 80000; gradual['growth_factor'] = 1.1
    history, end = simulate(999999, protocol=gradual)
    check('gradual_expansion_uses_existing_nice_rounding_and_reaches_ceiling_finitely',
          [p['users'] for p in history if p['stage'] == 'probe'] == [80000, 88000, 97000, 110000, 120000, 130000, 140000, 150000, 160000]
          and end['reason'] == 'HOLD_PASSED' and end['users'] == 160000
          and len([p for p in history if p['stage'] == 'probe']) <= 16)
    history, end = simulate(122000, protocol=gradual)
    check('gradual_expansion_brackets_and_bisects_within5pct_then_300s_hold', end['reason'] == 'HOLD_PASSED'
          and 0 < end['users'] <= 122000
          and min(p['users'] for p in history if p['classification'] == 'FAIL_SLO' and p['users'] > end['users']) - end['users'] <= .05 * end['users'])
    tiny = copy.deepcopy(gradual); tiny['minimum_users'] = tiny['start_users'] = 1
    check('rounded_expansion_that_hits_lower_bound_still_increases', next_action([
          {'id': 'w', 'stage': 'warmup', 'users': 10000, 'classification': 'PASS'},
          {'id': 'p', 'stage': 'probe', 'users': 1, 'classification': 'PASS'}], tiny) == {'stage': 'probe', 'users': 2})
    history, end = simulate(122000, hold_limit=1, protocol=gradual)
    check('gradual_search_respects_finite_probe_and_failed_hold_budgets', end['reason'] == 'HOLD_BUDGET_EXHAUSTED'
          and sum(p['stage'] == 'probe' for p in history) <= 16 and sum(p['stage'] == 'hold' for p in history) == 4)
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
    cpu_eight_inspect = copy.deepcopy(load_inspect)
    cpu_eight_inspect['HostConfig']['NanoCpus'] = 8 * 10**9
    cpu_eight_inspect['HostConfig']['Memory'] = cpu_eight_inspect['HostConfig']['MemorySwap'] = 8 * GiB
    check('actual_inspector_accepts8CPU8GiB_and_rejects4CPU_claim', inspect_budget(cpu_eight_inspect, 8, 8 * GiB)
          and not inspect_budget(cpu_eight_inspect, 4, 8 * GiB))
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
        cpu_plan = copy.deepcopy(eight_plan)
        cpu_plan['configuration']['load_cpus'] = cpu_plan['protocol']['load_cpus'] = 8
        rows = [json.loads(line) for line in (source / 'load-monitor.jsonl').read_text().splitlines()]
        for row in rows:
            row['cpu.max'] = '800000 100000'; row['memory.max'] = str(8 * GiB)
        path = directory / 'load-monitor.jsonl'; path.unlink(); path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        cpu_audit = audit_phase(directory, source, cpu_plan, case, initial)
        check('phase_audit_accepts_observed8CPU8GiB_matching_plan', cpu_audit['classification'] == 'PASS'
              and cpu_audit['declared_load_cpus'] == 8 and cpu_audit['declared_load_memory_bytes'] == 8 * GiB)
        check('client_CPU_utilization_uses_declared8CPU_denominator', abs(cpu_audit['load_monitor']['cgroup_quota_utilization_pct']
              - audited_eight['load_monitor']['cgroup_quota_utilization_pct'] / 2) < 1e-12)
        check('phase_audit_rejects_observed8CPU_against4CPU_plan', audit_phase(directory, source, eight_plan, case, initial)['classification'] == 'INVALID_MONITOR')
        cpu_mismatch = copy.deepcopy(cpu_plan); cpu_mismatch['configuration']['load_cpus'] = 4
        check('config_protocol_CPU_mismatch_rejected', audit_phase(directory, source, cpu_mismatch, case, initial)['classification'] == 'INVALID_EVIDENCE')
        restore('load-monitor.jsonl')
        check('phase_audit_rejects_observed4CPU_against8CPU_plan', audit_phase(directory, source, cpu_plan, case, initial)['classification'] == 'INVALID_MONITOR')
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
        for cpus in [8, 6]:
            config = {'cases': [copy.deepcopy(case)], 'load_cpus': cpus, 'load_memory_bytes': 8 * GiB,
                      'search_overrides': {'start_users': 80000}}
            cfg_path, dst = directory / f'config-cpu{cpus}.json', directory / f'plan-cpu{cpus}.json'
            cfg_path.write_text(json.dumps(config))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    prepare(cfg_path, dst)
                receipt = json.loads(dst.read_text())
                check('prepare_explicit8CPU8GiB_receipt_and_fixed_server', receipt['schema'] == 'multicore-local-capacity-v3'
                      and receipt['configuration']['load_cpus'] == receipt['protocol']['load_cpus'] == 8
                      and receipt['configuration']['load_memory_bytes'] == receipt['protocol']['load_memory_bytes'] == 8 * GiB
                      and receipt['protocol']['target_cpus'] == 8 and receipt['protocol']['target_memory_bytes'] == 16 * GiB
                      and receipt['protocol']['load_cpu_limit_pct'] == 75 and receipt['source_config_sha256'] == sha(cfg_path))
                prepare_checks.append({'cpus': cpus, 'memory': 8 * GiB, 'source_config_sha256': sha(cfg_path), 'plan_sha256': sha(dst)})
            except ValueError:
                check('prepare_rejects_unsupported6CPU_before_writing_plan', cpus == 6 and not dst.exists())
        default_receipt = json.loads(default_plan.read_text())
        check('prepare_default4CPU_preserves_historical_budget', default_receipt['configuration']['load_cpus']
              == default_receipt['protocol']['load_cpus'] == 4)
        for policy in ['dedicated_client_cgroup_v1', 'waive_all_invalidity']:
            scope_config = {'cases': [copy.deepcopy(case)], 'load_cpus': 8, 'load_memory_bytes': 8 * GiB,
                            'client_cpu_scope_policy': policy}
            cfg_path, dst = directory / ('config-' + policy + '.json'), directory / ('plan-' + policy + '.json')
            cfg_path.write_text(json.dumps(scope_config))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    prepare(cfg_path, dst)
                receipt = json.loads(dst.read_text())
                check('prepare_freezes_explicit_local_CPU_scope_in_source_config_receipt',
                      receipt['configuration']['client_cpu_scope_policy'] == receipt['protocol']['client_cpu_scope_policy'] == policy
                      and receipt['schema'] == 'multicore-local-capacity-v3' and receipt['source_config_sha256'] == sha(cfg_path))
                prepare_checks.append({'client_cpu_scope_policy': policy, 'source_config_sha256': sha(cfg_path), 'plan_sha256': sha(dst)})
            except ValueError:
                check('prepare_rejects_unknown_CPU_scope_before_writing_plan', policy == 'waive_all_invalidity' and not dst.exists())
        for factor in [1.1, 2, 1.2, True]:
            growth_config = {'cases': [copy.deepcopy(case)], 'growth_factor': factor, 'search_overrides': {'start_users': 80000}}
            cfg_path, dst = directory / f'config-growth{factor}.json', directory / f'plan-growth{factor}.json'
            cfg_path.write_text(json.dumps(growth_config))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    prepare(cfg_path, dst)
                receipt = json.loads(dst.read_text())
                check(f'prepare_freezes_growth{factor}_with_source_config_receipt',
                      receipt['configuration']['growth_factor'] == receipt['protocol']['growth_factor'] == factor
                      and receipt['schema'] == 'multicore-local-capacity-v3' and receipt['source_config_sha256'] == sha(cfg_path))
                prepare_checks.append({'growth_factor': factor, 'source_config_sha256': sha(cfg_path), 'plan_sha256': sha(dst)})
            except ValueError:
                check(f'prepare_rejects_unsupported_growth{factor}_before_writing_plan', factor in [1.2, True] and not dst.exists())
        check('default_growth_preserves_doubling_policy', default_receipt['configuration']['growth_factor']
              == default_receipt['protocol']['growth_factor'] == 2)
        inconsistent_growth = copy.deepcopy(plan); inconsistent_growth['configuration']['growth_factor'] = 1.1
        check('config_protocol_growth_mismatch_rejected', audit_phase(directory, source, inconsistent_growth, case, initial)['classification'] == 'INVALID_EVIDENCE')
        local_plan = copy.deepcopy(plan)
        local_plan['configuration']['client_cpu_scope_policy'] = local_plan['protocol']['client_cpu_scope_policy'] = 'dedicated_client_cgroup_v1'
        cpu_raws = [json.loads((source / f'box{i}.json').read_text()) for i in range(4)]
        cpu_merged = json.loads((source / 'merged.json').read_text())
        for i, raw in enumerate(cpu_raws):
            for row in raw['timeline']:
                row['cpu_pct'] = 90.0
            raw['box']['cpu_avg_measure_pct'] = raw['box']['cpu_max_measure_pct'] = 90.0
            cpu_merged['boxes'][i]['cpu_avg_measure_pct'] = cpu_merged['boxes'][i]['cpu_max_measure_pct'] = 90.0
            replace(f'box{i}.json', raw)
        cpu_merged['verdict']['lg_limited'] = True
        cpu_merged['verdict']['lg_reasons'] = [f'box {i} CPU 90% > 75%' for i in range(4)]
        replace('merged.json', cpu_merged)
        local = audit_phase(directory, source, local_plan, case, initial)
        check('whole_VM_CPU_only_exception_local_pass_preserves_native_LG_failure', local['classification'] == 'PASS'
              and local['local_qualified'] is True and local['native_qualified'] is False
              and local['native_verdict'] == cpu_merged['verdict'] and local['local_whole_vm_CPU_scope_exception'] is True)
        check('same_whole_VM_CPU_only_fixture_remains_invalid_under_default_native_policy',
              audit_phase(directory, source, plan, case, initial)['classification'] == 'INVALID_GENERATOR')
        monitor_rows = [json.loads(line) for line in (source / 'load-monitor.jsonl').read_text().splitlines()]
        factor = 80 / baseline['load_monitor']['cgroup_quota_utilization_pct']
        for row in monitor_rows:
            row['cpu']['usage_usec'] = round(row['cpu']['usage_usec'] * factor)
        path = directory / 'load-monitor.jsonl'; path.unlink(); path.write_text(''.join(json.dumps(r) + '\n' for r in monitor_rows))
        overloaded = audit_phase(directory, source, local_plan, case, initial)
        check('whole_VM_CPU_exception_does_not_waive_actual_client_cgroup80pct',
              overloaded['classification'] == 'INVALID_GENERATOR_CGROUP' and not overloaded['local_qualified'])
        restore('load-monitor.jsonl')
        false_reason = copy.deepcopy(cpu_merged); false_reason['verdict']['lg_reasons'].append('unknown infrastructure reason')
        replace('merged.json', false_reason)
        check('unknown_native_generator_reason_is_not_waived', not audit_phase(directory, source, local_plan, case, initial)['eligible'])
        false_reason['verdict']['lg_reasons'] = [f'box {i} CPU 99% > 75%' for i in range(4)]
        replace('merged.json', false_reason)
        check('false_native_CPU_reason_is_not_waived', not audit_phase(directory, source, local_plan, case, initial)['eligible'])
        replace('merged.json', cpu_merged)
        bad_raw = copy.deepcopy(cpu_raws[0]); bad_raw['box']['cpu_avg_measure_pct'] = 99.0
        replace('box0.json', bad_raw)
        check('CPU_summary_not_matching_timeline_is_not_waived', not audit_phase(directory, source, local_plan, case, initial)['eligible'])
        replace('box0.json', cpu_raws[0])
        bad_raw = copy.deepcopy(cpu_raws[0])
        next(row for row in bad_raw['timeline'] if row['t'] == bad_raw['meta']['ramp_s'])['tick_lag_ms'] = 600
        bad_raw['box']['fell_behind'] = True; bad_raw['box']['fell_behind_reasons'] = ['sampler tick 600 ms late']
        mixed = copy.deepcopy(cpu_merged); mixed['boxes'][0]['fell_behind'] = True
        mixed['boxes'][0]['fell_behind_reasons'] = ['sampler tick 600 ms late']
        mixed['verdict']['lg_reasons'].insert(1, 'box 0 fell behind: sampler tick 600 ms late')
        replace('box0.json', bad_raw); replace('merged.json', mixed)
        check('whole_VM_CPU_plus_actual_sampler_stall_remains_invalid',
              audit_phase(directory, source, local_plan, case, initial)['classification'] == 'INVALID_GENERATOR')
        bad_raw['box']['fell_behind'] = False; bad_raw['box'].pop('fell_behind_reasons')
        replace('box0.json', bad_raw); replace('merged.json', cpu_merged)
        check('hidden_timeline_stall_is_independently_rejected', not audit_phase(directory, source, local_plan, case, initial)['eligible'])
        replace('box0.json', cpu_raws[0])
        bad_hist = copy.deepcopy(cpu_merged); bad_hist['overall']['hist'] = cpu_raws[0]['endpoints']['tags']['hist'] if 'tags' in cpu_raws[0]['endpoints'] else ''
        # A changed aggregate quantile cannot be authorized by the CPU-scope exception.
        bad_hist['overall']['p95_ms'] *= 2
        replace('merged.json', bad_hist)
        check('histogram_quantile_tampering_remains_invalid_under_local_policy', not audit_phase(directory, source, local_plan, case, initial)['eligible'])
        for i in range(4):
            restore(f'box{i}.json')
        restore('merged.json')
        unsupported = copy.deepcopy(local_plan); unsupported['protocol']['client_cpu_scope_policy'] = 'ignore_everything'
        check('unsupported_or_mismatched_CPU_scope_policy_is_rejected',
              audit_phase(directory, source, unsupported, case, initial)['classification'] == 'INVALID_EVIDENCE')
        historical = Path(__file__).resolve().parents[2] / 'capacity_20261023t095453_5574c0'
        historical_plan = json.loads((historical / 'plan.json').read_text())
        historical_plan['configuration']['growth_factor'] = historical_plan['protocol']['growth_factor'] = 2
        historical_plan['configuration']['client_cpu_scope_policy'] = historical_plan['protocol']['client_cpu_scope_policy'] = 'dedicated_client_cgroup_v1'
        old_stall = audit_phase(historical / 'cases/rust7/phases/03-probe-160000', historical / 'cases/rust7', historical_plan,
                               historical_plan['configuration']['cases'][0], json.loads((historical / 'target-initial.json').read_text()))
        check('genuine_saved160k_stall_remains_invalid_with_new_local_policy', old_stall['classification'] == 'INVALID_GENERATOR'
              and not old_stall['eligible'] and not old_stall['native_qualified'] and not old_stall['local_whole_vm_CPU_scope_exception'])
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
