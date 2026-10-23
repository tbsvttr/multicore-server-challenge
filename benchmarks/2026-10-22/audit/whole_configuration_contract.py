"""Narrow opt-in for the separately declared portable-PR31/W2/B1 study.

This does not relax matched-knob checks for earlier studies. The frozen plan
must explicitly disclose the exact whole-configuration difference under review.
"""

PORTABLE_SHA = '5679b2f84562b352aa80faa6491ee9a6496224333881d2d96e585d468a6b67e2'
CANDIDATE_SHA = '6ab318a0ab9389dc2e77ec6122ff077a93adbcc183c6285c347104e0f734b6c3'
COMMON_ENV = {'PG_READERS': '3', 'HASHERS': '2', 'BCRYPT_BATCH_MS': '250',
              'READ_BATCH': '32', 'READ_HOLD': '1'}


def portable_comparison_checks(plan, reference, candidate):
    cfg = plan['configuration']
    contract = plan.get('preregistered_acceptance', {})
    differences = contract.get('whole_configuration_differences')
    declared = (plan.get('comparison_kind') == 'whole_configuration'
                or cfg.get('comparison_kind') == 'whole_configuration'
                or differences is not None)
    checks = []

    def add(name, passed, detail=None):
        row = {'check': name, 'pass': bool(passed)}
        if detail is not None:
            row['detail'] = detail
        checks.append(row)

    if not declared:
        shared = ['WORKERS', *COMMON_ENV]
        add('portable_reference_shared_runtime_knobs', all(
            reference['env'].get(k) == candidate['env'].get(k) for k in shared))
        add('portable_reference_explicitly_disclosed', bool(cfg.get('reference_disclosure')))
        return 'matched_runtime_knobs', checks

    differences = differences or {}
    ref, cand = differences.get('reference', {}), differences.get('candidate', {})
    add('whole_configuration_explicit_in_plan_and_configuration',
        plan.get('comparison_kind') == cfg.get('comparison_kind') == 'whole_configuration')
    add('whole_configuration_exact_reviewed_cases_and_binary_pins',
        [c['name'] for c in cfg['cases']] == ['goose31_portable', 'goose']
        and reference['name'] == 'goose31_portable' and candidate['name'] == 'goose'
        and reference.get('expected_binary_sha256') == PORTABLE_SHA
        and candidate.get('expected_binary_sha256') == CANDIDATE_SHA)
    add('whole_configuration_exact_reviewed_runtime_env',
        reference['env'] == {'WORKERS': '4', **COMMON_ENV}
        and candidate['env'] == {'ARTICLE_BATCH': '1', 'WORKERS': '2', **COMMON_ENV})
    add('whole_configuration_equal_knobs_explicitly_disclosed',
        differences.get('equal_runtime_knobs') == list(COMMON_ENV)
        and all(reference['env'].get(k) == candidate['env'].get(k) == v
                for k, v in COMMON_ENV.items()))
    add('whole_configuration_workers_and_article_batch_explicitly_disclosed',
        ref.get('WORKERS') == '4' and cand.get('WORKERS') == '2'
        and ref.get('PG_READERS') == cand.get('PG_READERS') == '3'
        and ref.get('HASHERS') == cand.get('HASHERS') == '2'
        and ref.get('ARTICLE_BATCH') == 'not implemented in PR31'
        and cand.get('ARTICLE_BATCH') == '1')
    pg = contract.get('postgres_connections', {})
    add('whole_configuration_pg_connections_16_vs8_explicitly_disclosed',
        pg.get('reference') == ref.get('postgres_connections') == 16
        and pg.get('candidate') == cand.get('postgres_connections') == 8
        and pg.get('formula') == 'WORKERS*(PG_READERS+1)')
    add('whole_configuration_reference_and_attribution_limit_disclosed',
        bool(cfg.get('reference_disclosure'))
        and bool(differences.get('attribution_limit'))
        and ref.get('json_hmac') == 'original pure Goose'
        and cand.get('json_hmac') == 'native prepared OpenSSL HMAC and native SIMD JSON')
    return 'whole_configuration', checks
