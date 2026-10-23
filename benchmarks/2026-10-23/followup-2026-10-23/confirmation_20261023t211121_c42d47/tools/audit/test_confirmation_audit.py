#!/usr/bin/env python3
"""Synthetic-only fixed-point aggregate tests; no real study data or runtime.

audit_phase, conformance and prior-study validation are explicitly stubbed: their
own qualification/provenance logic is outside these aggregation tests. Every
fixture is marked synthetic and removed with its TemporaryDirectory.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from audit import aggregate
from capacity_controller import CONFIRMATION_MODE
from search_policy import DEFAULT_PROTOCOL


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


class ConfirmationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='confirmation-audit-synthetic-')
        self.base = Path(self.temp.name)
        self.serial = 0
        self.patches = [mock.patch.object(subprocess, name,
                         side_effect=AssertionError('external execution forbidden'))
                        for name in ['run', 'Popen']]
        self.patches += [mock.patch.object(aggregate, 'validate_confirmation', return_value=None),
                         mock.patch.object(aggregate, 'conformance', return_value=True),
                         mock.patch.object(aggregate, 'audit_phase', side_effect=self.fake_phase)]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.temp.cleanup()

    @staticmethod
    def fake_phase(directory, case_dir, plan, case, initial, global_valid=True):
        # Intentionally do not weaken the stub when wrapper checks fail: the
        # aggregate must itself refuse a false confirmation for bad actions.
        return json.loads((directory / 'SYNTHETIC-assessment.json').read_text())

    def fixture(self, stages=None, users=None, classification=None, eligible=None):
        self.serial += 1
        root = self.base / str(self.serial)
        root.mkdir()
        protocol = copy.deepcopy(DEFAULT_PROTOCOL)
        protocol.update(load_cpus=8, load_memory_bytes=8 * 1024**3,
                        gomaxprocs_per_shard=2, client_cpu_scope_policy='dedicated_client_cgroup_v1',
                        growth_factor=1.1)
        cases = [{'fixture_only': True, 'name': name, 'confirm_users': count,
                  'expected_binary_sha256': sha(('SYNTHETIC app: ' + name).encode())}
                 for name, count in [('goose32-prototypeB', 140000), ('rust7', 130000)]]
        old = root / 'SYNTHETIC-seed-receipts'
        seed_hash = sha(b'SYNTHETIC seed')
        (old / 'setup').mkdir(parents=True)
        (old / 'seed-full.log').write_text('SYNTHETIC UNIT FIXTURE\nOK: conduit_seed matches the reference seed\n')
        (old / 'setup/upstream-sha256.txt').write_text(seed_hash + '  /work/seed/make-seed.sh\n')
        configuration = {'fixture_only': True, 'cases': cases, 'old_host_evidence': str(old),
                         'load_cpus': 8, 'load_memory_bytes': 8 * 1024**3,
                         'gomaxprocs_per_shard': 2, 'client_env': {'GOMAXPROCS': '2'},
                         'client_cpu_scope_policy': 'dedicated_client_cgroup_v1', 'growth_factor': 1.1,
                         'expected_native_sha256': 'f' * 64}
        plan = {'fixture_only': True, 'schema': 'multicore-local-confirmation-v1',
                'scope': 'SYNTHETIC UNIT FIXTURE ONLY; no benchmark executed',
                'study_mode': CONFIRMATION_MODE, 'capacity_search_disabled': True,
                'configuration': configuration, 'protocol': protocol}
        write(root / 'plan.json', plan)
        (root / 'plan.sha256').write_text(sha((root / 'plan.json').read_bytes()) + '\n')
        write(root / 'target-initial.json', {'fixture_only': True,
              'pg_settings': [{'name': k, 'setting': v, 'unit': None, 'source': 'synthetic'} for k, v in
                [('server_version_num', '180000'), ('max_connections', '100'), ('fsync', 'on'),
                 ('synchronous_commit', 'on'), ('full_page_writes', 'on')]],
              'official_source_sha256': {'seed/make-seed.sh': seed_hash}})
        for kind, memory in [('target', 16 * 1024**3), ('load', 8 * 1024**3)]:
            inspection = {'fixture_only': True, 'Id': 'synthetic-' + kind,
                          'Config': {'Env': ['GOMAXPROCS=2']},
                          'HostConfig': {'NanoCpus': 8 * 10**9, 'Memory': memory,
                            'MemorySwap': memory, 'CpusetCpus': '', 'CpusetMems': '',
                            'NetworkMode': 'container:synthetic-target' if kind == 'load' else 'bridge'}}
            write(root / (kind + '-inspect.json'), inspection)
            write(root / (kind + '-final-inspect.json'), inspection)
        (root / 'native-sha256.txt').write_text('f' * 64 + '  SYNTHETIC-not-executed\n')
        (root / 'tools').mkdir()
        (root / 'tools/SYNTHETIC-tool.txt').write_text('not executable; synthetic tool hash fixture\n')
        write(root / 'tool-sha256.json', {'SYNTHETIC-tool.txt': sha((root / 'tools/SYNTHETIC-tool.txt').read_bytes())})
        write(root / 'final-resource-check.json', {'fixture_only': True, 'valid': True})
        events = []
        for case_index, case in enumerate(cases):
            events.append({'event': 'case_start', 'case': case['name']})
            directory = root / 'cases' / case['name']
            source = directory / 'frozen/source'
            source.mkdir(parents=True)
            (source / 'SYNTHETIC-source.txt').write_text('not implementation code; synthetic source fixture\n')
            source_hashes = {'SYNTHETIC-source.txt': sha((source / 'SYNTHETIC-source.txt').read_bytes())}
            (directory / 'frozen/app').write_text('SYNTHETIC app: ' + case['name'])
            write(directory / 'frozen/metadata.json', {'fixture_only': True, 'case': case,
                  'binary_sha256': case['expected_binary_sha256'], 'source_sha256': source_hashes,
                  'source_manifest_sha256': sha(json.dumps(source_hashes, sort_keys=True).encode())})
            write(directory / 'app.json', {'fixture_only': True, 'pgid': 10 + case_index})
            write(directory / 'stopped.json', {'fixture_only': True, 'stopped_pgid': 10 + case_index})
            database = 'mc_pair_SYNTHETIC_' + str(case_index)
            write(directory / 'database.json', {'fixture_only': True, 'database': database})
            write(directory / 'dropped.json', {'database': database, 'dropped': True})
            selected_stages = (stages if stages is not None else ['warmup', 'probe', 'hold']) if case_index == 0 else ['warmup', 'probe', 'hold']
            for index, stage in enumerate(selected_stages):
                count = 10000 if stage == 'warmup' else case['confirm_users']
                if case_index == 0 and users is not None:
                    count = users[index]
                name = f'{index + 1:02}-{stage}-{count}'
                phase = directory / 'phases' / name
                write(phase / 'phase.json', {'fixture_only': True, 'stage': stage, 'users': count})
                outcome = classification.get(index, 'PASS') if case_index == 0 and classification else 'PASS'
                qualification = eligible.get(index, True) if case_index == 0 and eligible else True
                write(phase / 'SYNTHETIC-assessment.json', {'fixture_only': True, 'id': name,
                      'stage': stage, 'users': count, 'classification': outcome, 'eligible': qualification,
                      'overall': {'p95_ms': 5, 'p99_ms': 10, 'errors': 0},
                      'zero_measured_errors': True, 'observed_timeline_errors': 7,
                      'cpu_ms_per_successful_request_sampled_estimate': 1,
                      'native_qualified': False, 'local_qualified': True,
                      'native_verdict': {'pass': True, 'lg_limited': True,
                                        'lg_reasons': ['SYNTHETIC preserved native flag']},
                      'native_whole_vm_CPU_flag_count': 2, 'native_whole_vm_CPU_flagged_shards': [0, 1],
                      'local_whole_vm_CPU_scope_exception': True})
                (phase / 'SYNTHETIC-error.log').write_text('SYNTHETIC retained error evidence\n')
                events.append({'event': 'phase_start', 'case': case['name'], 'id': name})
        events.append({'event': 'controller_finished', 'error': None})
        (root / 'events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in events))
        return root

    def run_audit(self, root):
        before = {str(p.relative_to(root)): sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
        result = aggregate.audit_run(root)
        after = {str(p.relative_to(root)): sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
        self.assertEqual(before, after, 'read-only aggregation must preserve all failed/error fixture bytes')
        self.assertIs(result['capacity_maximum_established'], False)
        self.assertIs(result['official_rank_proven'], False)
        self.assertIs(result['all_competitors_beaten'], False)
        for row in result['rows']:
            self.assertIsNone(row['capacity_users'])
            self.assertIs(row['capacity_maximum_established'], False)
        return result

    def test_exact_three_actions_confirm_points_with_native_flags_without_maximum(self):
        result = self.run_audit(self.fixture())
        self.assertIs(result['both_selected_points_confirmed'], True)
        self.assertEqual([row['confirmed_users'] for row in result['rows']], [140000, 130000])
        for row in result['rows']:
            self.assertEqual(row['status'], 'LOCAL_CONFIRMATION_PASSED')
            self.assertEqual(row['measured_seconds'], 300)
            self.assertIs(row['native_qualified'], False)
            self.assertIs(row['native_verdict']['lg_limited'], True)
            self.assertEqual(row['native_verdict']['lg_reasons'], ['SYNTHETIC preserved native flag'])
            self.assertEqual(row['observed_timeline_errors'], 7)
            self.assertEqual(row['native_whole_vm_CPU_flagged_shards'], [0, 1])

    def test_wrong_phase_count_order_users_or_fourth_phase_cannot_confirm_both(self):
        wrong = [dict(stages=[]), dict(stages=['warmup']), dict(stages=['warmup', 'probe']),
                 dict(stages=['warmup', 'hold', 'probe']), dict(stages=['probe', 'probe', 'hold']),
                 dict(stages=['warmup', 'probe', 'hold', 'hold']),
                 dict(users=[9999, 140000, 140000]), dict(users=[10000, 135000, 140000]),
                 dict(users=[10000, 140000, 135000])]
        for options in wrong:
            with self.subTest(options=options):
                result = self.run_audit(self.fixture(**options))
                self.assertIs(result['both_selected_points_confirmed'], False)
                self.assertIs(result['rows'][0]['confirmation_passed'], False)
                self.assertIsNone(result['rows'][0]['confirmed_users'])

    def test_failed_or_invalid_warmup_probe_or_hold_never_confirms(self):
        for index in range(3):
            for classification in ['FAIL_SLO', 'INVALID_CLOCK', 'GENERATOR_TIMING']:
                with self.subTest(index=index, classification=classification):
                    stages = ['warmup', 'probe', 'hold'][:index + 1]
                    result = self.run_audit(self.fixture(stages=stages, classification={index: classification},
                                                        eligible={index: False}))
                    self.assertIs(result['both_selected_points_confirmed'], False)
                    self.assertIs(result['rows'][0]['confirmation_passed'], False)
                    self.assertEqual(result['rows'][0]['status'], 'CONFIRMATION_STOP_' + classification)

    def test_phase_after_failure_is_retained_and_invalidates_confirmation(self):
        result = self.run_audit(self.fixture(classification={1: 'FAIL_SLO'}, eligible={1: False}))
        row = result['rows'][0]
        self.assertIs(result['both_selected_points_confirmed'], False)
        self.assertEqual(len(row['phases']), 3)
        self.assertTrue(any(not c['pass'] and c['check'].endswith('no_phase_after_failure_or_invalidity')
                            for c in row['checks']))

    def test_PASS_without_exact_true_eligibility_does_not_confirm(self):
        for value in [False, None, 1, 'true']:
            with self.subTest(value=value):
                result = self.run_audit(self.fixture(eligible={2: value}))
                self.assertIs(result['both_selected_points_confirmed'], False)
                self.assertIs(result['rows'][0]['confirmation_passed'], False)

    def test_case_start_wrong_order_duplicate_or_missing_cannot_confirm_both(self):
        replacements = [['rust7', 'goose32-prototypeB'],
                        ['goose32-prototypeB', 'goose32-prototypeB', 'rust7'],
                        ['goose32-prototypeB'], []]
        for case_starts in replacements:
            with self.subTest(case_starts=case_starts):
                root = self.fixture()
                original = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
                changed = [{'event': 'case_start', 'case': case} for case in case_starts]
                changed += [row for row in original if row['event'] != 'case_start']
                (root / 'events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in changed))
                result = self.run_audit(root)
                self.assertIs(result['both_selected_points_confirmed'], False)
                self.assertEqual(result['status'], 'INVALID_GLOBAL_EVIDENCE')

    def test_genuinely_unstarted_next_case_retains_partial_evidence_without_both_confirmed(self):
        root = self.fixture()
        shutil.rmtree(root / 'cases/rust7')  # only this TemporaryDirectory fixture
        events = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
        events = [row for row in events if row.get('case') != 'rust7']
        (root / 'events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in events))
        result = self.run_audit(root)
        self.assertEqual(result['status'], 'AUDITED_COMPLETED_CONFIRMATION')
        self.assertIs(result['both_selected_points_confirmed'], False)
        self.assertIs(result['rows'][0]['confirmation_passed'], True)
        self.assertEqual(result['rows'][1]['status'], 'NOT_STARTED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
