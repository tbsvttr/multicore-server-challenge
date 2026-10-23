#!/usr/bin/env python3
"""Light saved-monitor tests using synthetic rows; never reads active trials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from primitives import GiB, cpu_budget_matches, monitor


class CPUBudgetTests(unittest.TestCase):
    def test_equivalent_positive_quotas_match_exact_cpu_budget(self):
        for value in ['800000 100000', '1600000 200000', '4000000 500000',
                      ' 800000\t100000\n', '000800000 0100000']:
            with self.subTest(value=value):
                self.assertTrue(cpu_budget_matches(value, 8))
        self.assertTrue(cpu_budget_matches('800000 100000', 8.0))
        self.assertTrue(cpu_budget_matches('250000 100000', 2.5))

    def test_wrong_positive_ratios_rejected_in_both_directions(self):
        for value in ['799999 100000', '800001 100000', '700000 100000',
                      '900000 100000', '1600000 100000', '800000 200000']:
            with self.subTest(value=value):
                self.assertFalse(cpu_budget_matches(value, 8))

    def test_unlimited_negative_zero_and_malformed_rejected(self):
        for value in [None, 8, b'800000 100000', '', 'max 100000', '-1 100000',
                      '800000 -100000', '-800000 -100000', '0 100000', '800000 0',
                      '0 0', '800000', '800000 100000 extra', '800000.0 100000',
                      '+800000 100000', '800000 1e5', '800000\n100000',
                      '800000\x00100000', '８０００００ １０００００']:
            with self.subTest(value=value):
                self.assertFalse(cpu_budget_matches(value, 8))
        for cpus in [0, -8, True, False, '8', None, float('nan'), float('inf')]:
            with self.subTest(cpus=cpus):
                self.assertFalse(cpu_budget_matches('800000 100000', cpus))


class MonitorTests(unittest.TestCase):
    memory = 16 * GiB
    meta = {'window_start_ms': 1000, 'window_end_ms': 3000}
    labels = {'monitor_has_samples', 'strict_wall_and_monotonic_order',
              'full_measurement_window_bracketed', 'max_sample_gap_at_most_3s',
              'cgroup_budget_continuous', 'total_cpu_counter_nondecreasing',
              'no_measurement_oom', 'wall_to_monotonic_drift_below_100ms'}

    def rows(self, values=None):
        values = values or ['800000 100000'] * 3
        return [{'wall_ns': (index + 1) * 10**9,
                 'monotonic_ns': (index + 1) * 10**9,
                 'cpu.max': value, 'cpu': {'usage_usec': (index + 1) * 10**6},
                 'memory.max': str(self.memory), 'memory.swap.max': '0',
                 'memory.swap.current': '0', 'memory.current': '1024',
                 'memory.peak': '2048',
                 'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0',
                 'app': {'pids': [101], 'cpu_s': (index + 1) * .25},
                 'pg': {'pids': [201, 202], 'cpu_s': (index + 1) * .5}}
                for index, value in enumerate(values)]

    def audit(self, rows, meta=None):
        with tempfile.TemporaryDirectory(prefix='cpu-ratio-synthetic-') as tmp:
            path = Path(tmp) / 'monitor.jsonl'
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            return monitor(path, meta or self.meta, 8, self.memory)

    def verdicts(self, result):
        return {check['check']: check['pass'] for check in result['checks']}

    def test_default_period_preserves_all_existing_gates_and_metrics(self):
        result = self.audit(self.rows())
        self.assertTrue(result['eligible'])
        self.assertEqual(set(self.verdicts(result)), self.labels)
        self.assertEqual(result['warnings'], [])
        self.assertFalse(result['cpu_period_changed'])
        self.assertEqual(result['observed_cpu_periods_us'], [100000])
        self.assertEqual(result['cgroup_cpu_seconds_estimate'], 2)
        self.assertEqual(result['cgroup_quota_utilization_pct'], 12.5)
        self.assertEqual(result['swap_peak_sampled_bytes'], 0)

    def test_200ms_and_mixed_periods_are_eligible_but_warn_and_retain_raw(self):
        baseline = self.audit(self.rows())
        values = ['800000 100000', '1600000 200000', '800000 100000']
        result = self.audit(self.rows(values))
        self.assertTrue(result['eligible'])
        self.assertTrue(result['cpu_period_changed'])
        self.assertEqual(result['observed_cpu_periods_us'], [100000, 200000])
        self.assertEqual([row['cpu.max'] for row in result['cpu_budget_observations']], values)
        self.assertEqual([row['period_us'] for row in result['cpu_budget_observations']], [100000, 200000, 100000])
        self.assertEqual([row['quota_us'] for row in result['cpu_budget_observations']], [800000, 1600000, 800000])
        self.assertEqual([row['sample_index'] for row in result['cpu_budget_observations']], [0, 1, 2])
        self.assertEqual(len(result['warnings']), 2)
        self.assertTrue(any('non-default' in value for value in result['warnings']))
        self.assertTrue(any('changed' in value for value in result['warnings']))
        detail_keys = {'cpu_budget_observations', 'observed_cpu_periods_us', 'cpu_period_changed', 'warnings'}
        self.assertEqual({k:v for k,v in result.items() if k not in detail_keys},
                         {k:v for k,v in baseline.items() if k not in detail_keys})
        constant = self.audit(self.rows(['1600000 200000'] * 3))
        self.assertTrue(constant['eligible'])
        self.assertFalse(constant['cpu_period_changed'])
        self.assertEqual(len(constant['warnings']), 1)

    def test_every_sample_budget_must_match_and_raw_invalid_values_remain(self):
        for value in ['700000 100000', '900000 100000', 'max 100000',
                      '800000 0', '-800000 -100000', 'invalid', None]:
            with self.subTest(value=value):
                result = self.audit(self.rows(['800000 100000', value, '1600000 200000']))
                self.assertFalse(result['eligible'])
                self.assertFalse(self.verdicts(result)['cgroup_budget_continuous'])
                self.assertEqual(result['cpu_budget_observations'][1]['cpu.max'], value)
                self.assertEqual(set(self.verdicts(result)), self.labels)

    def test_memory_swap_oom_clock_and_coverage_failures_remain_ineligible(self):
        cases = [
            ('memory_limit', 'cgroup_budget_continuous', lambda rows: rows[1].update({'memory.max': str(self.memory + 1)})),
            ('memory_usage', 'cgroup_budget_continuous', lambda rows: rows[1].update({'memory.current': str(self.memory + 1)})),
            ('swap_limit', 'cgroup_budget_continuous', lambda rows: rows[1].update({'memory.swap.max': '1'})),
            ('swap_usage', 'cgroup_budget_continuous', lambda rows: rows[1].update({'memory.swap.current': '1'})),
            ('oom', 'no_measurement_oom', lambda rows: rows[2].update({'memory.events': 'oom 1\noom_kill 0\noom_group_kill 0'})),
            ('clock_drift', 'wall_to_monotonic_drift_below_100ms', lambda rows: rows[2].update({'wall_ns': rows[2]['wall_ns'] + 200000000})),
            ('cpu_counter', 'total_cpu_counter_nondecreasing', lambda rows: rows[1].update({'cpu': {'usage_usec': 0}})),
            ('wall_order', 'strict_wall_and_monotonic_order', lambda rows: rows[1].update({'monotonic_ns': rows[0]['monotonic_ns'] - 1})),
        ]
        for name, label, change in cases:
            with self.subTest(case=name):
                rows = self.rows(['1600000 200000'] * 3)
                change(rows)
                result = self.audit(rows)
                self.assertFalse(result['eligible'])
                self.assertFalse(self.verdicts(result)[label])
                self.assertEqual(set(self.verdicts(result)), self.labels)
        coverage = self.audit(self.rows(), {'window_start_ms': 500, 'window_end_ms': 3000})
        self.assertFalse(coverage['eligible'])
        self.assertFalse(self.verdicts(coverage)['full_measurement_window_bracketed'])
        gaps = self.rows()
        gaps[1]['wall_ns'] = gaps[1]['monotonic_ns'] = 5 * 10**9
        gaps[2]['wall_ns'] = gaps[2]['monotonic_ns'] = 9 * 10**9
        gap_result = self.audit(gaps, {'window_start_ms': 1000, 'window_end_ms': 9000})
        self.assertFalse(gap_result['eligible'])
        self.assertFalse(self.verdicts(gap_result)['max_sample_gap_at_most_3s'])

    def test_raw_cpu_observations_survive_insufficient_sample_failure(self):
        result = self.audit(self.rows(['1600000 200000']))
        self.assertFalse(result['eligible'])
        self.assertEqual(result['cpu_budget_observations'][0]['cpu.max'], '1600000 200000')
        self.assertEqual(result['cpu_budget_observations'][0]['period_us'], 200000)
        self.assertEqual(len(result['warnings']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
