#!/usr/bin/env python3
"""Synthetic confirmation orchestration tests: no app, Docker, SQL or load.

Every phase result and process/database identity below is an explicitly fake
unit fixture in TemporaryDirectory, never an observed benchmark result.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import capacity_controller as implementation
from search_policy import DEFAULT_PROTOCOL


BINARY_B = '9016ff93e924c0d94652490ac895d1fbc64153fd9d3ea4b8b52b66ae892c3424'
BINARY_RUST = '844afb23cb68586c7652e70b94357e73da6c7708c723b815e1209bd520fd3241'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def cases():
    # Hypothetical selected counts exercise the controller. No real B result is
    # consulted or implied; confirmation preparation stays blocked until chosen.
    return [{'name': 'goose32-prototypeB', 'confirm_users': 140000,
             'binary': '/synthetic/B/app', 'source_dir': '/synthetic/B/source',
             'expected_binary_sha256': BINARY_B, 'env': {}},
            {'name': 'rust7', 'confirm_users': 130000,
             'binary': '/synthetic/Rust/app', 'source_dir': '/synthetic/Rust/source',
             'expected_binary_sha256': BINARY_RUST, 'env': {}}]


class FakeController(implementation.Controller):
    """Use real run_case/run; replace only external-effect boundaries and phase."""
    def __init__(self, root, outcomes=None, fail_cleanup=None, phase_exception=None):
        # Deliberately bypass the production constructor, which creates/freeze
        # real study files. A separate test covers its placeholder guard.
        self.root = Path(root)
        self.croot = str(self.root)
        self.host_base = self.root
        self.name = 'confirmation_20990101t000000_synthetic'
        self.target, self.client = 'synthetic-target', 'synthetic-client'
        self.protocol = copy.deepcopy(DEFAULT_PROTOCOL)
        self.cfg = {'cases': cases(), 'port': 3000, 'jwt_secret': 'synthetic-secret',
                    'container_evidence': '/synthetic',
                    'old_host_evidence': '/synthetic/not-accessed',
                    'native_binary': '/synthetic/not-executed',
                    'expected_native_sha256': 'f' * 64}
        self.plan = {'configuration': self.cfg, 'protocol': self.protocol}
        self.case_records = []
        self.events = io.StringIO()
        self.stop_host = threading.Event()
        self.load_cpus, self.load_memory = 8, 8 * 1024**3
        self.load_created = False
        self.current_generators = []
        self.outcomes = outcomes or {}
        self.fail_cleanup = fail_cleanup or set()
        self.phase_exception = phase_exception
        self.trace, self.phase_calls, self.returned_results = [], [], []
        self.live_db = self.live_app = None
        self.database_serial = self.app_serial = 0
        self.running = {self.target}
        self.artifact_hashes = {}

    def event(self, kind, **fields):
        self.trace.append(('event', kind, copy.deepcopy(fields)))

    def idle(self, seconds):
        self.trace.append(('idle', seconds))

    def host_monitor(self):
        self.trace.append(('synthetic-host-monitor',))

    def kill_generators(self):
        self.trace.append(('synthetic-kill-generators',))

    def docker(self, *argv, save=None, **kwargs):
        self.trace.append(('docker-fake', argv))
        if argv[0] == 'run':
            self.running.add(self.client)
        elif argv[0] == 'stop':
            self.running.discard(argv[-1])
        if save is not None:
            save.write_text(self.cfg['expected_native_sha256'] + '  synthetic-client\n')
        return ''

    def inspect(self, name, path, cpus, memory):
        value = {'fixture_only': True, 'Id': name, 'Image': 'synthetic-image',
                 'State': {'Running': name in self.running},
                 'HostConfig': {'NanoCpus': cpus * 10**9, 'Memory': memory,
                                'MemorySwap': memory, 'CpusetCpus': '', 'CpusetMems': ''}}
        write(path, value)
        return value

    def control(self, action, destination, *args, **kwargs):
        destination = Path(destination)
        self.trace.append(('control', action, str(destination)))
        if action in self.fail_cleanup:
            raise RuntimeError('synthetic ' + action + ' failure')
        if action == 'freeze':
            assert self.live_db is None and self.live_app is None
            case = json.loads(Path(args[args.index('--case') + 1]).read_text())
            write(destination / 'metadata.json', {'fixture_only': True,
                  'binary_sha256': case['expected_binary_sha256']})
        elif action == 'clone':
            assert self.live_db is None and self.live_app is None
            self.database_serial += 1
            self.live_db = {'database': args[args.index('--database') + 1],
                            'clone_generation': self.database_serial, 'mutations': 0}
            write(destination, {'fixture_only': True, 'database': self.live_db['database'],
                                'template': 'conduit_seed',
                                'counts': {'users': 100000, 'articles': 500000}})
        elif action == 'start':
            assert self.live_db and self.live_app is None
            assert args[args.index('--database') + 1] == self.live_db['database']
            self.app_serial += 1
            self.live_app = {'fixture_only': True, 'database': self.live_db['database'],
                             'pgid': 1000 + self.app_serial, 'pid': 2000 + self.app_serial}
            write(destination, self.live_app)
        elif action == 'stop':
            assert self.live_app is not None
            write(destination, {'fixture_only': True, 'stopped_pgid': self.live_app['pgid']})
            self.live_app = None
        elif action == 'drop':
            assert self.live_db is not None and self.live_app is None
            assert args[args.index('--database') + 1] == self.live_db['database']
            write(destination, {'fixture_only': True, 'database': self.live_db['database'], 'dropped': True})
            self.live_db = None
        elif action == 'snapshot':
            write(destination, {'fixture_only': True, 'ip_local_port_range': '10000 65000',
                                'pg_settings': [{'name': k, 'setting': v} for k, v in
                                    [('server_version_num', '180000'), ('max_connections', '100'),
                                     ('fsync', 'on'), ('synchronous_commit', 'on'), ('full_page_writes', 'on')]]})
        elif action == 'probe-limits':
            write(destination, {'fixture_only': True})
        else:
            raise AssertionError('unexpected production side-effect boundary: ' + action)

    def phase(self, directory, cdir, case, action, number):
        assert self.live_db and self.live_app
        assert json.loads((directory / 'app.json').read_text()) == self.live_app
        assert json.loads((directory / 'database.json').read_text())['database'] == self.live_db['database']
        call = {'case': case['name'], **copy.deepcopy(action),
                'duration': copy.deepcopy(self.protocol[action['stage']]),
                'database': self.live_db['database'], 'clone_generation': self.live_db['clone_generation'],
                'pid': self.live_app['pid'], 'pgid': self.live_app['pgid'],
                'mutations_before': self.live_db['mutations']}
        self.phase_calls.append(call)
        self.live_db['mutations'] += 1
        choices = self.outcomes.get(case['name'], [])
        override = choices[number - 1] if number <= len(choices) else {}
        result = {'fixture_only': True, 'id': f'{number:02}-{action["stage"]}-{action["users"]}',
                  'case': case['name'], **action, 'classification': 'PASS', 'eligible': True,
                  'native_verdict': {'pass': True, 'lg_limited': True,
                                     'lg_reasons': ['SYNTHETIC retained whole-VM CPU flag']},
                  'native_qualified': False, 'local_qualified': True,
                  'observed_timeline_errors': 7, 'raw_error_sentinel': 'SYNTHETIC retained errors'}
        result.update(copy.deepcopy(override))
        phase_dir = directory / 'phases' / result['id']
        write(phase_dir / 'assessment.json', result)
        (phase_dir / 'error.log').write_text('SYNTHETIC UNIT FIXTURE retained error evidence\n')
        for path in phase_dir.iterdir():
            self.artifact_hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        if self.phase_exception == (case['name'], action['stage']):
            raise RuntimeError('synthetic phase failure')
        self.returned_results.append(copy.deepcopy(result))
        return result


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='confirmation-synthetic-')
        self.root = Path(self.scratch.name)
        # Any accidental escape from a fake boundary fails before an external
        # process can run. Production constructors are used only for rejection.
        self.no_run = mock.patch.object(implementation.subprocess, 'run', side_effect=AssertionError('external command forbidden'))
        self.no_popen = mock.patch.object(implementation.subprocess, 'Popen', side_effect=AssertionError('external process forbidden'))
        self.no_run.start(); self.no_popen.start()

    def tearDown(self):
        self.no_popen.stop(); self.no_run.stop(); self.scratch.cleanup()

    def lifecycle(self, controller, action):
        return [row for row in controller.trace if row[:2] == ('control', action)]

    def assert_artifacts_retained(self, controller):
        for path, sha in controller.artifact_hashes.items():
            self.assertTrue(path.exists())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)

    def test_actions_are_fixed_independent_and_boundary_validated(self):
        for users in [10, 10000, 130000, 160000]:
            with self.subTest(users=users):
                self.assertEqual(implementation.confirmation_actions({'confirm_users': users}),
                                 [{'stage': 'warmup', 'users': 10000},
                                  {'stage': 'probe', 'users': users}, {'stage': 'hold', 'users': users}])
        first = implementation.confirmation_actions({'confirm_users': 130000})
        first[1]['users'] = 1
        self.assertEqual(implementation.confirmation_actions({'confirm_users': 130000})[1]['users'], 130000)
        class IntSubclass(int):
            pass
        for users in [None, True, False, 0, -1, 9, 160001, '130000', 130000.0, IntSubclass(130000), [], {}]:
            with self.subTest(invalid=repr(users)):
                with self.assertRaises(ValueError):
                    implementation.confirmation_actions({'confirm_users': users})
        with self.assertRaises(ValueError):
            implementation.confirmation_actions({})

    def test_placeholder_cannot_prepare_or_create_a_runtime_directory(self):
        selected = cases(); selected[0]['confirm_users'] = None
        cfg = {'study_mode': implementation.CONFIRMATION_MODE, 'cases': selected,
               'host_evidence': str(self.root / 'must-not-create'),
               'load_cpus': 8, 'load_memory_bytes': 8 * 1024**3}
        source, plan = self.root / 'draft.json', self.root / 'plan.json'
        write(source, cfg)
        with self.assertRaises(ValueError):
            implementation.prepare(source, plan)
        self.assertFalse(plan.exists())
        self.assertFalse(plan.with_suffix('.json.sha256').exists())
        write(plan, {'schema': 'multicore-local-confirmation-v1',
                     'study_mode': implementation.CONFIRMATION_MODE, 'capacity_search_disabled': True,
                     'configuration': cfg, 'protocol': DEFAULT_PROTOCOL})
        plan.with_suffix('.json.sha256').write_text(hashlib.sha256(plan.read_bytes()).hexdigest() + '\n')
        with self.assertRaises(ValueError):
            implementation.Controller(plan)
        self.assertFalse(Path(cfg['host_evidence']).exists())

    def synthetic_reference(self):
        selected = cases()
        cfg = {'study_mode': implementation.CONFIRMATION_MODE, 'cases': selected,
               'load_cpus': 8, 'load_memory_bytes': 8 * 1024**3,
               'client_cpu_scope_policy': 'dedicated_client_cgroup_v1',
               'gomaxprocs_per_shard': 2, 'client_env': {'GOMAXPROCS': '2'},
               'growth_factor': 1.1, 'native_binary': '/synthetic/native',
               'expected_native_sha256': 'f' * 64, 'port': 3000}
        first_run = self.root / 'SYNTHETIC-FIRST-STUDY'
        first_configuration = copy.deepcopy(cfg)
        first_configuration.pop('study_mode')
        first_configuration['cases'].reverse()
        for case in first_configuration['cases']:
            case.pop('confirm_users')
        first_configuration['lifecycle_helper'] = '/private/tmp/multicore-research-20261022/lab-target-control-v2.py'
        first_configuration['monitor_helper'] = '/private/tmp/multicore-research-20261022/lab-monitor.py'
        write(first_run / 'plan.json', {'fixture_only': True, 'schema': 'multicore-local-capacity-v4',
                                       'configuration': first_configuration})
        prior = {'fixture_only': True, 'status': 'AUDITED_COMPLETED_LOCAL_SEARCH',
                 'study_complete': True,
                 'run': str(first_run),
                 'raw_input_sha256': {'plan.json': hashlib.sha256((first_run / 'plan.json').read_bytes()).hexdigest()},
                 'rows': [{'fixture_only': True, 'case': case['name'],
                           'binary_sha256': case['expected_binary_sha256'],
                           'capacity_users': case['confirm_users'], 'measured_seconds': 300,
                           'local_qualified': True, 'conformance_197_full_seed_proven': True}
                          for case in selected]}
        path = self.root / 'SYNTHETIC-UNIT-REFERENCE.json'
        write(path, prior)
        cfg.update(first_study_audit=str(path),
                   first_study_audit_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        return cfg, prior, path

    def test_reference_requires_completed_exact_binary_qualified300second_points(self):
        cfg, prior, path = self.synthetic_reference()
        self.assertIsNone(implementation.validate_confirmation(cfg))
        changes = [lambda p: p.update({'status': 'ACTIVE_NOT_READ'}),
                   lambda p: p.update({'study_complete': False}),
                   lambda p: p['rows'].pop(),
                   lambda p: p['rows'][0].update({'binary_sha256': '0' * 64}),
                   lambda p: p['rows'][0].update({'capacity_users': 150000}),
                   lambda p: p['rows'][0].update({'measured_seconds': 60}),
                   lambda p: p['rows'][0].update({'local_qualified': False}),
                   lambda p: p['rows'][0].update({'conformance_197_full_seed_proven': False})]
        for index, change in enumerate(changes):
            with self.subTest(invalid_reference=index):
                altered = copy.deepcopy(prior)
                change(altered); write(path, altered)
                cfg['first_study_audit_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):
                    implementation.validate_confirmation(cfg)

    def test_reference_hash_and_selected_order_cannot_be_silently_changed(self):
        cfg, _, path = self.synthetic_reference()
        path.write_text(path.read_text() + '\n')
        with self.assertRaises(ValueError):
            implementation.validate_confirmation(cfg)
        cfg, _, _ = self.synthetic_reference()
        for change in [lambda c: c.update({'study_mode': 'capacity-search'}),
                       lambda c: c.update({'load_cpus': 4}),
                       lambda c: c.update({'load_memory_bytes': 4 * 1024**3}),
                       lambda c: c['cases'].reverse(),
                       lambda c: c['cases'][0].update({'expected_binary_sha256': BINARY_RUST}),
                       lambda c: c['cases'][0].update({'confirm_users': 130000})]:
            altered = copy.deepcopy(cfg); change(altered)
            with self.assertRaises(ValueError):
                implementation.validate_confirmation(altered)

    def test_reference_binds_effective_source_environment_and_runtime_inputs(self):
        cfg, prior, reference = self.synthetic_reference()
        self.assertIsNone(implementation.validate_confirmation(cfg))
        changes = [lambda c: c['cases'][0]['env'].update({'WORKERS': '99'}),
                   lambda c: c['cases'][0].update({'binary': '/synthetic/changed-binary'}),
                   lambda c: c['cases'][0].update({'source_dir': '/synthetic/changed-source'}),
                   lambda c: c.update({'client_cpu_scope_policy': 'native_whole_vm_v1'}),
                   lambda c: c.update({'gomaxprocs_per_shard': 1}),
                   lambda c: c.update({'client_env': {'GOMAXPROCS': '4'}}),
                   lambda c: c.update({'native_binary': '/synthetic/changed-native'}),
                   lambda c: c.update({'expected_native_sha256': '0' * 64}),
                   lambda c: c.update({'port': 3999}),
                   lambda c: c.update({'growth_factor': 2}),
                   lambda c: c.update({'lifecycle_helper': '/synthetic/changed-helper'}),
                   lambda c: c.update({'search_overrides': {}})]
        for index, change in enumerate(changes):
            with self.subTest(changed_effective_input=index):
                altered = copy.deepcopy(cfg); change(altered)
                with self.assertRaises(ValueError):
                    implementation.validate_confirmation(altered)
        first_plan = Path(prior['run']) / 'plan.json'
        first_plan.write_text(first_plan.read_text() + '\n')
        with self.assertRaises(ValueError):
            implementation.validate_confirmation(cfg)
        # Even a rehashed reference cannot silently choose other runtime inputs.
        changed = json.loads(first_plan.read_text())
        changed['configuration']['cases'][0]['env']['READ_BATCH_SIZE'] = '99'
        write(first_plan, changed)
        prior['raw_input_sha256']['plan.json'] = hashlib.sha256(first_plan.read_bytes()).hexdigest()
        write(reference, prior)
        cfg['first_study_audit_sha256'] = hashlib.sha256(reference.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            implementation.validate_confirmation(cfg)

    def test_success_uses_one_continuous_session_and_exact300second_hold(self):
        controller = FakeController(self.root)
        controller.run_case(cases()[0])
        record = controller.case_records[0]
        self.assertEqual(record['status'], 'CONFIRMATION_PASSED')
        self.assertEqual(record['confirmation_users'], 140000)
        self.assertIs(record['capacity_maximum_established'], False)
        self.assertEqual([(p['stage'], p['users']) for p in controller.phase_calls],
                         [('warmup', 10000), ('probe', 140000), ('hold', 140000)])
        self.assertEqual([p['duration'] for p in controller.phase_calls],
                         [{'ramp_s': 60, 'measure_s': 120, 'tail_s': 15},
                          {'ramp_s': 60, 'measure_s': 60, 'tail_s': 15},
                          {'ramp_s': 60, 'measure_s': 300, 'tail_s': 15}])
        for action in ['freeze', 'clone', 'start', 'stop', 'drop']:
            self.assertEqual(len(self.lifecycle(controller, action)), 1)
        self.assertEqual(len({p['database'] for p in controller.phase_calls}), 1)
        self.assertEqual(len({p['pid'] for p in controller.phase_calls}), 1)
        self.assertEqual([p['mutations_before'] for p in controller.phase_calls], [0, 1, 2])
        self.assertEqual([x[1] for x in controller.trace if x[0] == 'idle'], [5, 65, 65])
        self.assertIsNone(controller.live_db); self.assertIsNone(controller.live_app)
        self.assert_artifacts_retained(controller)

    def test_each_stage_stops_on_SLO_or_invalid_without_retry_or_stepdown(self):
        for stage_index in range(3):
            for classification in ['FAIL_SLO', 'INVALID_CLOCK', 'GENERATOR_TIMING', 'APP_CRASH']:
                with self.subTest(stage=stage_index, classification=classification):
                    root = self.root / f'{stage_index}-{classification}'
                    outcomes = [{} for _ in range(stage_index)] + [{'classification': classification, 'eligible': False}]
                    controller = FakeController(root, {'goose32-prototypeB': outcomes})
                    controller.run_case(cases()[0])
                    record = controller.case_records[0]
                    self.assertEqual(record['status'], 'CONFIRMATION_STOP_' + classification)
                    self.assertEqual(len(controller.phase_calls), stage_index + 1)
                    self.assertEqual(len(record['phases']), stage_index + 1)
                    self.assertIs(record['stop_action']['no_retry_or_fallback'], True)
                    self.assertEqual(len(self.lifecycle(controller, 'clone')), 1)
                    self.assertEqual(len(self.lifecycle(controller, 'start')), 1)
                    self.assertEqual(len(self.lifecycle(controller, 'stop')), 1)
                    self.assertEqual(len(self.lifecycle(controller, 'drop')), 1)
                    self.assert_artifacts_retained(controller)

    def test_PASS_without_exact_true_eligibility_cannot_confirm(self):
        for eligible in [False, None, 1, 'true']:
            with self.subTest(eligible=eligible):
                controller = FakeController(self.root / str(eligible), {'goose32-prototypeB':
                    [{}, {'classification': 'PASS', 'eligible': eligible}]})
                controller.run_case(cases()[0])
                self.assertEqual(controller.case_records[0]['status'], 'CONFIRMATION_STOP_PASS')
                self.assertEqual(len(controller.phase_calls), 2)
                self.assertNotIn('hold', [p['stage'] for p in controller.phase_calls])

    def test_local_PASS_retains_native_flags_and_raw_errors_verbatim(self):
        controller = FakeController(self.root)
        controller.run_case(cases()[0])
        record = controller.case_records[0]
        saved = json.loads((self.root / 'cases/goose32-prototypeB/session.json').read_text())
        self.assertEqual(record['phases'], controller.returned_results)
        self.assertEqual(saved['phases'], controller.returned_results)
        self.assertEqual(record['status'], 'CONFIRMATION_PASSED')
        for phase in saved['phases']:
            self.assertIs(phase['native_verdict']['lg_limited'], True)
            self.assertIs(phase['native_qualified'], False)
            self.assertEqual(phase['observed_timeline_errors'], 7)
            self.assertEqual(phase['raw_error_sentinel'], 'SYNTHETIC retained errors')
        self.assert_artifacts_retained(controller)

    def test_phase_exception_still_cleans_single_session_and_retains_failed_artifacts(self):
        controller = FakeController(self.root, phase_exception=('goose32-prototypeB', 'probe'))
        controller.run_case(cases()[0])
        self.assertEqual(controller.case_records[0]['status'], 'INVALID_SESSION')
        self.assertEqual(len(controller.phase_calls), 2)
        for action in ['clone', 'start', 'stop', 'drop']:
            self.assertEqual(len(self.lifecycle(controller, action)), 1)
        self.assertIsNone(controller.live_db); self.assertIsNone(controller.live_app)
        self.assert_artifacts_retained(controller)

    def test_actual_outer_run_keeps_B_then_Rust_order_after_B_stops(self):
        controller = FakeController(self.root, {'goose32-prototypeB':
            [{}, {'classification': 'FAIL_SLO', 'eligible': False}]})
        controller.run()
        self.assertEqual([r['case'] for r in controller.case_records], ['goose32-prototypeB', 'rust7'])
        self.assertEqual([r['status'] for r in controller.case_records],
                         ['CONFIRMATION_STOP_FAIL_SLO', 'CONFIRMATION_PASSED'])
        self.assertEqual([(p['case'], p['stage'], p['users']) for p in controller.phase_calls],
                         [('goose32-prototypeB', 'warmup', 10000), ('goose32-prototypeB', 'probe', 140000),
                          ('rust7', 'warmup', 10000), ('rust7', 'probe', 130000), ('rust7', 'hold', 130000)])
        self.assertEqual(controller.database_serial, 2)
        self.assertEqual(controller.app_serial, 2)
        self.assertNotEqual(controller.phase_calls[0]['database'], controller.phase_calls[-1]['database'])
        self.assertEqual(len(self.lifecycle(controller, 'clone')), 2)
        self.assertEqual(len(self.lifecycle(controller, 'drop')), 2)
        self.assertEqual([x[2]['case'] for x in controller.trace if x[:2] == ('event', 'case_start')],
                         ['goose32-prototypeB', 'rust7'])
        self.assert_artifacts_retained(controller)

    def test_cleanup_failure_prevents_starting_next_case(self):
        for action in ['stop', 'drop']:
            with self.subTest(action=action):
                controller = FakeController(self.root / action, fail_cleanup={action})
                self.assertEqual(controller.run(), 1)
                self.assertEqual([r['case'] for r in controller.case_records], ['goose32-prototypeB'])
                self.assertEqual(controller.app_serial, 1)
                self.assertIn(action + '_error', controller.case_records[0])
                self.assert_artifacts_retained(controller)


if __name__ == '__main__':
    unittest.main(verbosity=2)
