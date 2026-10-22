#!/usr/bin/env python3
"""Regression fixtures for monitor coverage and post-tail target validity.

Loads only pure assessment functions through AST; never executes controller CLI
or Docker orchestration. These represent previously misqualified scenarios.
"""
import ast
import copy
import json
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
tree=ast.parse((ROOT/'paired-multi-load-v3.py').read_text())
names={'summarize_monitor','memory_event_counts','assess_target_runtime','actual_app_limits_valid','assert_budget'}
module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
ns={'json':json,'pathlib':pathlib}
exec(compile(module,str(ROOT/'paired-multi-load-v3.py'),'exec'),ns)

def row(t,mono=None):
    return {'wall_ns':int(t*10**9),'monotonic_ns':int((t if mono is None else mono)*10**9),
            'cpu':{'usage_usec':int(t*500000)},'memory.current':'1000','memory.swap.current':'0',
            'memory.events':'oom 0\noom_kill 0\noom_group_kill 0',
            'app':{'cpu_s':t*.1,'rss_bytes':100},'pg':{'cpu_s':t*.2,'rss_bytes':200}}

class Coverage(unittest.TestCase):
    def summary(self,rows):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'witness.jsonl'
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            return ns['summarize_monitor'](p,10000,70000,8)

    def test_complete_bracketing(self):
        r=self.summary([row(t) for t in range(9,72)])
        self.assertTrue(r['valid_sampling']);self.assertTrue(r['full_window_bracketed'])
        self.assertEqual(r['sampled_interval_start_ms'],10000)
        self.assertEqual(r['sampled_interval_end_ms'],70000)

    def test_tail_missing_despite_clean_internal_gaps(self):
        r=self.summary([row(t) for t in range(10,41)])
        self.assertFalse(r['valid_sampling']);self.assertEqual(r['coverage_end_missing_s'],30)

    def test_start_missing_despite_clean_internal_gaps(self):
        r=self.summary([row(t) for t in range(40,71)])
        self.assertFalse(r['valid_sampling']);self.assertEqual(r['coverage_start_missing_s'],30)

    def test_three_second_boundary_tolerance(self):
        self.assertTrue(self.summary([row(t) for t in range(13,68)])['valid_sampling'])

    def test_boundary_tolerance_exceeded(self):
        self.assertFalse(self.summary([row(t) for t in range(14,68)])['valid_sampling'])
        self.assertFalse(self.summary([row(t) for t in range(13,67)])['valid_sampling'])

    def test_gap_straddling_boundary(self):
        rows=[row(6)]+[row(t) for t in range(11,72)]
        self.assertFalse(self.summary(rows)['valid_sampling'])

    def test_internal_gap(self):
        self.assertFalse(self.summary([row(t) for t in range(9,72) if t not in [30,31,32]])['valid_sampling'])

    def test_wall_jump_with_regular_monotonic_samples(self):
        rows=[row(t) for t in range(9,31)]+[row(t+10,t) for t in range(31,62)]
        self.assertFalse(self.summary(rows)['valid_sampling'])

    def test_backwards_timestamp(self):
        rows=[row(t) for t in range(9,72)];rows[20]['wall_ns']=rows[19]['wall_ns']-1
        self.assertFalse(self.summary(rows)['valid_sampling'])

    def test_empty_single_and_outside_window(self):
        for rows in [[],[row(20)],[row(t) for t in range(80,90)]]:
            self.assertFalse(self.summary(rows)['valid_sampling'])

class TargetRuntime(unittest.TestCase):
    def check(self,before,after):return ns['assess_target_runtime'](before,after)
    def events(self,oom=0,kill=0):return {'memory.events':f'oom {oom}\noom_kill {kill}\noom_group_kill 0'}

    def test_healthy_with_historical_oom(self):
        a=self.events(2,1);b={**self.events(2,1),'app_healthy':True}
        self.assertTrue(self.check(a,b)['pass'])

    def test_app_crash_in_tail_cannot_pass(self):
        r=self.check(self.events(),{**self.events(),'app_healthy':False})
        self.assertTrue(r['valid_witness']);self.assertFalse(r['pass'])

    def test_new_oom_even_when_app_health_recovers(self):
        r=self.check(self.events(),{**self.events(1,1),'app_healthy':True})
        self.assertFalse(r['pass']);self.assertEqual(r['oom_deltas']['oom_kill'],1)

    def test_missing_health_or_oom_witness(self):
        for after in [self.events(),{'app_healthy':True},{'app_healthy':True,'memory.events':''}]:
            r=self.check(self.events(),after)
            self.assertFalse(r['valid_witness']);self.assertFalse(r['pass'])

    def test_backwards_oom_counter(self):
        self.assertFalse(self.check(self.events(2,1),{**self.events(),'app_healthy':True})['valid_witness'])

    def test_inputs_and_native_verdict_are_not_changed(self):
        before=self.events();after={**self.events(),'app_healthy':False,'verdict':{'pass':True,'lg_limited':False}}
        saved=copy.deepcopy((before,after));self.check(before,after)
        self.assertEqual((before,after),saved)

class AppLimits(unittest.TestCase):
    def witness(self,soft=200000,hard=200000,uid=501):
        return {'valid':True,'processes':[{'pid':1234,'uid':uid,'uids':[uid]*4,'nofile_soft':soft,'nofile_hard':hard}]}
    def check(self,w):return ns['actual_app_limits_valid'](w,501)
    def test_real_user_and_both_limits(self):self.assertTrue(self.check(self.witness()))
    def test_runuser_reset_soft_limit(self):self.assertFalse(self.check(self.witness(1024,200000)))
    def test_hard_limit_also_required(self):self.assertFalse(self.check(self.witness(200000,1024)))
    def test_wrong_uid(self):self.assertFalse(self.check(self.witness(uid=0)))
    def test_saved_root_uid(self):
        w=self.witness();w['processes'][0]['uids'][2]=0;self.assertFalse(self.check(w))
    def test_missing_or_dead_process(self):
        for w in [None,{}, {'valid':True,'processes':[]}]:self.assertFalse(self.check(w))
    def test_false_identity_witness(self):
        w=self.witness();w['valid']=False;self.assertFalse(self.check(w))
    def test_missing_limit(self):
        w=self.witness();del w['processes'][0]['nofile_hard'];self.assertFalse(self.check(w))
    def test_unlimited_is_at_least_required(self):self.assertTrue(self.check(self.witness('unlimited','unlimited')))

class V3Budget(unittest.TestCase):
    def config(self,cpus,memory):
        return {'HostConfig':{'NanoCpus':cpus*10**9,'Memory':memory,'MemorySwap':memory,'CpusetCpus':''}}
    def test_four_cpu_client_budget(self):ns['assert_budget'](self.config(4,4*1024**3),4,4*1024**3)
    def test_two_cpu_client_no_longer_matches(self):
        with self.assertRaises(AssertionError):ns['assert_budget'](self.config(2,4*1024**3),4,4*1024**3)
    def test_target_eight_cpu_unchanged(self):ns['assert_budget'](self.config(8,16*1024**3),8,16*1024**3)
    def test_cpu_normalization_uses_four(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'witness.jsonl'
            rows=[row(t) for t in range(9,72)]
            for x in rows:x['cpu']['usage_usec']=int(x['monotonic_ns']/10**9*2000000)
            p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
            result=ns['summarize_monitor'](p,10000,70000,4)
            self.assertTrue(result['valid_sampling']);self.assertEqual(result['cgroup_cpu_quota_pct'],50)

if __name__=='__main__':unittest.main(verbosity=2)
