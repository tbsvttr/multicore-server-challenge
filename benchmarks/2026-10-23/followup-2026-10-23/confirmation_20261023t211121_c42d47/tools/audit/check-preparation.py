#!/usr/bin/env python3
"""Read-only static delta proof; no runtime resources or benchmark records."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('refusing to replace an existing preparation proof')
    here = Path(__file__).resolve().parents[1]
    old = here.with_name('capacity-v4')
    checks = []

    def check(name, value, **details):
        checks.append({'name': name, 'pass': bool(value), **details})

    def methods(path):
        tree = ast.parse(path.read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Controller')
        return {node.name: ast.dump(node, include_attributes=False)
                for node in cls.body if isinstance(node, ast.FunctionDef)}

    baseline, current = methods(old / 'capacity_controller.py'), methods(here / 'capacity_controller.py')
    for name in sorted(baseline):
        expected_same = name not in ['__init__', 'run_case']
        check('Controller.' + name + ':expected_delta', (baseline[name] == current[name]) == expected_same,
              unchanged_expected=expected_same)
    for name in ['search_policy.py', 'audit/evidence.py', 'audit/primitives.py', 'audit/test_cpu_ratio.py']:
        check(name + ':byte_identical_v4', sha(old / name) == sha(here / name), sha256=sha(here / name))
    for name in ['capacity_controller.py', 'audit/aggregate.py']:
        tree = ast.parse((here / name).read_text())
        check(name + ':no_adaptive_search_calls', not any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'next_action'
            for node in ast.walk(tree)))
    original = json.loads((here.parent / 'profiles/capacity-v4-sourceB-config.json').read_text())
    draft = json.loads((here / 'cases-DRAFT.json').read_text())
    check('case_order_B_then_R', [case['name'] for case in draft['cases']] == ['goose32-prototypeB', 'rust7'])
    for before, after in zip(reversed(original['cases']), draft['cases']):
        check(after['name'] + ':all_original_case_inputs_unchanged',
              {key: value for key, value in after.items() if key != 'confirm_users'} == before)
    for key, value in original.items():
        if key not in ['cases', 'scope', 'study_note', 'search_overrides']:
            check('original_config:' + key, draft.get(key) == value)
    check('B_placeholder_not_selected', draft['cases'][0]['confirm_users'] is None)
    check('R_selected130000', draft['cases'][1]['confirm_users'] == 130000)
    check('reference_pending', draft['first_study_audit'] is None and draft['first_study_audit_sha256'] is None)
    for path in here.rglob('*.py'):
        ast.parse(path.read_text())
    check('all_python_ast_parse', True)
    origin = json.loads((here / 'v4-origin-sha256.json').read_text())
    check('frozen_v4_sources_match_origin', all(sha(old / key) == value for key, value in origin.items()))
    check('no_immutable_confirmation_plan', not any('plan' in path.name for path in here.iterdir() if path.is_file()))
    result = {'status': 'STATIC_PREPARATION_ONLY', 'runtime_executed': False, 'final_plan_prepared': False,
              'first_study_B_result_assumed': False, 'checks': checks,
              'passed': sum(check['pass'] for check in checks), 'total': len(checks),
              'controller_sha256': sha(here / 'capacity_controller.py'),
              'aggregate_sha256': sha(here / 'audit/aggregate.py'), 'draft_sha256': sha(here / 'cases-DRAFT.json')}
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'total': result['total'], 'out': str(args.out)}))
    return 0 if result['passed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
