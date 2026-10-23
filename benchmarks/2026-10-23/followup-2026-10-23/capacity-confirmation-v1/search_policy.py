"""Finite predeclared native-style capacity search; no external effects."""
import math


DEFAULT_PROTOCOL = {
    'warmup_users': 10000, 'start_users': 10000, 'max_users': 160000, 'resolution': 0.05,
    'growth_factor': 2,
    'max_probes': 16, 'max_holds': 4, 'minimum_users': 10,
    'warmup': {'ramp_s': 60, 'measure_s': 120, 'tail_s': 15},
    'probe': {'ramp_s': 60, 'measure_s': 60, 'tail_s': 15},
    'hold': {'ramp_s': 60, 'measure_s': 300, 'tail_s': 15},
    'articles': 500000, 'think_scale': 1.0, 'max_users_per_shard': 20000,
    'max_shards': 8, 'gomaxprocs_per_shard': 2,
    'target_cpus': 8, 'target_memory_bytes': 16 * 1024**3,
    'load_cpus': 4, 'load_memory_bytes': 4 * 1024**3,
    'client_cpu_scope_policy': 'native_whole_vm_v1',
    'load_cpu_limit_pct': 75.0, 'actual_nofile_minimum': 200000,
    'between_phase_minimum_s': 65, 'idle_cpu_pct': 15.0, 'idle_max_s': 90,
    'clock_drift_limit_s': 0.1, 'monitor_gap_limit_s': 3.0,
    'rounding_policy': 'local search: two significant digits; bisection uses strict integer midpoint if rounded midpoint hits either bound',
    'database_policy': 'one fresh full-seed clone and one continuous app session per implementation; no reset between warmup/probes/holds',
    'invalid_policy': 'retain and stop that implementation; invalid phases never enter pass/fail brackets or receive a score; no selective retry',
}


def client_gomaxprocs(protocol, configuration):
    """Version4 requires the same explicit two-P client runtime everywhere."""
    value = protocol.get('gomaxprocs_per_shard')
    configured = configuration.get('gomaxprocs_per_shard')
    if (type(value) is not int or value != 2 or type(configured) is not int
            or configured != value or configuration.get('client_env') != {'GOMAXPROCS': '2'}):
        raise ValueError('v4 requires explicit matching GOMAXPROCS2 configuration, protocol and client_env')
    return value


def growth_factor(protocol, configuration):
    factor = protocol['growth_factor']
    configured = configuration.get('growth_factor', 2)
    if (type(factor) not in (int, float) or factor not in (1.1, 2)
            or type(configured) not in (int, float) or configured != factor):
        raise ValueError('growth_factor must declare matching 1.1 or 2')
    return factor


def client_cpu_scope_policy(protocol, configuration):
    policy = protocol['client_cpu_scope_policy']
    if policy not in ('native_whole_vm_v1', 'dedicated_client_cgroup_v1') or configuration.get(
            'client_cpu_scope_policy', 'native_whole_vm_v1') != policy:
        raise ValueError('client CPU scope policy must be explicitly supported and match configuration')
    return policy


def load_cpus(protocol, configuration):
    """Validate a predeclared external client CPU quota; no server changes."""
    cpus = protocol['load_cpus']
    if (type(cpus) is not int or cpus not in (4, 8)
            or type(configuration.get('load_cpus', 4)) is not int
            or configuration.get('load_cpus', 4) != cpus):
        raise ValueError('external client must declare matching 4 or 8 CPU')
    return cpus


def load_memory_bytes(protocol, configuration):
    """Validate the declared external client budget, independently of Docker."""
    memory = protocol['load_memory_bytes']
    load_cpus(protocol, configuration)
    if (type(memory) is not int or memory not in (4 * 1024**3, 8 * 1024**3)
            or configuration.get('load_memory_bytes', 4 * 1024**3) != memory
            or type(configuration.get('load_memory_bytes', 4 * 1024**3)) is not int):
        raise ValueError('external client must declare matching 4 or 8 GiB memory')
    return memory


def nice(value):
    if value <= 0:
        return 0
    scale = 10 ** max(0, int(math.floor(math.log10(value))) - 1)
    return max(1, int(math.floor(value / scale + 0.5)) * scale)


def shards(users, protocol=DEFAULT_PROTOCOL):
    count = max(1, math.ceil(users / protocol['max_users_per_shard']))
    if count > protocol['max_shards']:
        raise ValueError('predeclared shard ceiling exceeded')
    base, extra = divmod(users, count)
    result, offset = [], 0
    for index in range(count):
        n = base + (index < extra)
        result.append({'box_index': index, 'users': n, 'id_offset': offset, 'host': f'127.0.0.{index + 1}'})
        offset += n
    return result


def next_action(phases, protocol=DEFAULT_PROTOCOL):
    for phase in phases:
        if phase['classification'] not in ['PASS', 'FAIL_SLO']:
            return {'stage': 'stop', 'reason': phase['classification'], 'invalid_or_crashed_phase': phase['id']}
    if not phases:
        return {'stage': 'warmup', 'users': protocol['warmup_users']}
    probes = [p for p in phases if p['stage'] == 'probe']
    holds = [p for p in phases if p['stage'] == 'hold']
    if holds:
        if holds[-1]['classification'] == 'PASS':
            return {'stage': 'stop', 'reason': 'HOLD_PASSED', 'users': holds[-1]['users']}
        if len(holds) >= protocol['max_holds']:
            return {'stage': 'stop', 'reason': 'HOLD_BUDGET_EXHAUSTED'}
        users = min(holds[-1]['users'] - 1, nice(holds[-1]['users'] * (1 - protocol['resolution'])))
        if users < protocol['minimum_users']:
            return {'stage': 'stop', 'reason': 'NO_PASSING_HOLD'}
        return {'stage': 'hold', 'users': users}
    if not probes:
        return {'stage': 'probe', 'users': protocol['start_users']}
    passing = [p['users'] for p in probes if p['classification'] == 'PASS']
    lo = max(passing, default=0)
    failing = [p['users'] for p in probes if p['classification'] == 'FAIL_SLO' and p['users'] > lo]
    hi = min(failing, default=0)
    if len(probes) >= protocol['max_probes']:
        return {'stage': 'hold', 'users': lo, 'probe_budget_exhausted': True} if lo else {'stage': 'stop', 'reason': 'PROBE_BUDGET_EXHAUSTED_NO_PASS'}
    if not lo:
        users = nice(probes[-1]['users'] / 2)
        if probes[-1]['users'] <= protocol['minimum_users'] or users >= probes[-1]['users']:
            return {'stage': 'stop', 'reason': 'NO_PASSING_PROBE'}
        return {'stage': 'probe', 'users': max(protocol['minimum_users'], users)}
    if not hi:
        if lo < protocol['max_users']:
            users = max(lo + 1, nice(lo * protocol['growth_factor']))
            return {'stage': 'probe', 'users': min(users, protocol['max_users'])}
        return {'stage': 'hold', 'users': lo, 'ceiling_reached': True}
    if hi - lo > protocol['resolution'] * lo:
        users = nice((lo + hi) / 2)
        if not lo < users < hi:
            users = (lo + hi) // 2
        if lo < users < hi:
            return {'stage': 'probe', 'users': users}
    return {'stage': 'hold', 'users': lo, 'probe_upper_fail': hi}
