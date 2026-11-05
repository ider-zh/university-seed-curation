"""Deterministic append-only merge of independently reviewed domain observations.

This adapter intentionally does not implement corrections, withdrawals, or arbitrary
JSON patching.  Its input is a freshly compiled pilot transport record.
"""
from copy import deepcopy
from decimal import Decimal

from .pilot_protocol import compile_record, GROUPS
from .preferred import recompute, validate, fields
from .records import instant


def _source_map(out, incoming):
    mapping = {}
    for ref, source in incoming.items():
        matches = [key for key, old in out.items() if old == source]
        if matches:
            mapping[ref] = sorted(matches)[0]
        else:
            n = 1
            while 's' + str(n) in out: n += 1
            mapping[ref] = 's' + str(n)
            out[mapping[ref]] = deepcopy(source)
    return mapping


def _rewrite_sources(node, mapping):
    if isinstance(node, dict):
        return {k: mapping[v] if k == 'source_ref' else _rewrite_sources(v, mapping) for k, v in node.items()}
    if isinstance(node, list): return [_rewrite_sources(v, mapping) for v in node]
    return node


def _numeric_observation(candidate):
    """Return comparable scope and numbers for supported quantitative observations."""
    value = candidate.get('value')
    if not isinstance(value, dict): return None
    if 'latitude' in value and 'longitude' in value:
        return (('coordinates', value.get('globe_qid', 'Q2'), value.get('crs')), (Decimal(str(value['latitude'])), Decimal(str(value['longitude']))))
    if 'amount' in value:
        numbers = (value['amount'],)
    elif 'minimum' in value and 'maximum' in value:
        numbers = (value['minimum'], value['maximum'])
    else: return None
    return (('quantity', value.get('basis'), value.get('currency')), tuple(Decimal(str(n)) for n in numbers))


def _merge_field(old, new):
    if set(new) - {'candidates', 'conflicts', 'preferred', 'subject_ref'}:
        raise ValueError('Unsupported field operation')
    if old.get('subject_ref') != new.get('subject_ref'):
        raise ValueError('Field subject conflict')
    existing = list(old['candidates'])
    ids = {c['id'] for c in existing}; remap = {}
    for candidate in new['candidates']:
        bare = {k: v for k, v in candidate.items() if k != 'id'}
        match = next((c for c in old['candidates'] if {k: v for k, v in c.items() if k != 'id'} == bare), None)
        if match: remap[candidate['id']] = match['id']; continue
        n = 1
        while 'c' + str(n) in ids: n += 1
        ident = 'c' + str(n); ids.add(ident); remap[candidate['id']] = ident
        inserted = {**deepcopy(bare), 'id': ident}
        old['candidates'].append(inserted)
        observed = _numeric_observation(inserted)
        if observed is not None:
            for prior in existing:
                other = _numeric_observation(prior)
                if (prior.get('verification') == 'withdrawn' or other is None or
                    prior.get('period') != inserted.get('period') or other[0] != observed[0] or other[1] == observed[1]):
                    continue
                pair = {prior['id'], ident}
                if not any(c['kind'] == 'value_disagreement' and c['status'] == 'unresolved'
                           and pair <= set(c['candidate_ids']) for c in old.get('conflicts', [])):
                    old.setdefault('conflicts', []).append({'candidate_ids': [prior['id'], ident],
                        'kind': 'value_disagreement', 'status': 'unresolved',
                        'note': 'Different numeric observations have the same stated period and scope.'})
    for conflict in new.get('conflicts', []):
        row = deepcopy(conflict); row['candidate_ids'] = list(dict.fromkeys(remap[x] for x in row['candidate_ids']))
        if len(row['candidate_ids']) < 2: continue
        if not any(c['kind'] == row['kind'] and c['status'] == row['status']
                   and set(c['candidate_ids']) == set(row['candidate_ids']) for c in old.get('conflicts', [])):
            old.setdefault('conflicts', []).append(row)
    if old.get('conflicts') == []: old.pop('conflicts')


def _merge(old, new, path=''):
    if isinstance(old, dict) and isinstance(new, dict):
        if 'candidates' in new:
            if 'candidates' not in old: raise ValueError('Field shape collision at ' + path)
            _merge_field(old, new); return
        if path.startswith('/related_entities/') and path.count('/') == 2:
            for key in ('kind', 'qid'):
                if old.get(key) != new.get(key): raise ValueError('Conflicting related context metadata at ' + path)
        for key, value in new.items():
            if key not in old: old[key] = deepcopy(value)
            else: _merge(old[key], value, path + '/' + key)
    elif isinstance(old, list) and isinstance(new, list):
        if path.endswith('/locations') or path.endswith('/milestones'):
            for item in new:
                match = next((v for v in old if v['id'] == item['id']), None)
                if match is None: old.append(deepcopy(item))
                else:
                    # Missing qid is also meaningful: it cannot silently acquire or lose identity.
                    for k in (('id', 'kind', 'qid') if path.endswith('/locations') else ('id', 'kind', 'subject_ref')):
                        if match.get(k) != item.get(k): raise ValueError('Conflicting context metadata at ' + path)
                    _merge(match, item, path + '/' + item['id'])
        else:
            # Alias/relationship field arrays represent independently scoped values.
            for item in new:
                if item not in old: old.append(deepcopy(item))
    elif old != new:
        raise ValueError('Conflicting immutable metadata at ' + path)


def materialize(baseline, delta, seed, changed_at, full_refresh=False):
    instant(changed_at); validate(delta)
    for _, field, _ in fields(delta):
        if any(c['verification'] != 'supported' for c in field['candidates']):
            raise ValueError('Corrections, withdrawals and unsupported candidates require a separate adapter')
        if any(c['status'] != 'unresolved' for c in field.get('conflicts', [])):
            raise ValueError('Resolving existing conflicts requires a separate adapter')
    if baseline is None:
        result = deepcopy(delta)
        result['schema_version'] = '0.2.2'; result['seed'] = deepcopy(seed)
        result['modified_datetime'] = changed_at
        result.pop('update_datetime', None)
        if full_refresh: _complete(result, changed_at, delta['coverage'])
        validate(result); return result
    validate(baseline)
    if baseline['qid'] != delta['qid']: raise ValueError('QID mismatch')
    if baseline['schema_version'] not in ('0.2.1', '0.2.2'): raise ValueError('Unsupported baseline schema')
    out = deepcopy(baseline)
    mapping = _source_map(out.setdefault('sources', {}), delta['sources'])
    add = _rewrite_sources(delta, mapping)
    # Identity status is an independently reviewed context; no other curation metadata is changed.
    out['curation']['identity_status'] = add['curation']['identity_status']
    if 'update_datetime' in out and out['curation']['identity_status'] in ('needs_review', 'conflation_suspected'):
        raise ValueError('Unresolved identity requires a separate correction policy')
    for key in ('identity', 'locations', 'history', 'related_entities', 'population', 'finance', 'leadership', 'profile', 'relationships'):
        if key in add:
            if key not in out: out[key] = deepcopy(add[key])
            else: _merge(out[key], add[key], '/' + key)
    out['coverage'] = deepcopy(add['coverage'])
    out['schema_version'] = '0.2.2'; out['record_revision'] += 1; out['modified_datetime'] = changed_at
    if full_refresh: _complete(out, changed_at, delta['coverage'])
    out = recompute(out); validate(out)
    return out


def _complete(record, at, coverage):
    if record['curation']['identity_status'] not in ('in_scope', 'related', 'excluded'):
        raise ValueError('Unresolved identity cannot complete a full refresh')
    record['curation']['reviewed_groups'] = list(GROUPS)
    record['curation']['refresh_profile'] = 'core-v1'
    record['coverage'] = deepcopy(coverage)
    record['update_datetime'] = at


def compile_delta(proposal, packet):
    return compile_record(proposal, packet)


def check_delta(candidate, review, trust, baseline):
    if review.get('decision') != 'approve' or not review.get('review_session'):
        raise ValueError('Independent approval required')
    full = review.get('refresh_profile') == 'core-v1'
    if full and (set(review.get('reviewed_groups', [])) != set(GROUPS) or review.get('coverage_complete') is not True):
        raise ValueError('Incomplete full refresh review')
    if candidate != materialize(baseline, review['domain_delta'], review['seed'], review['reviewed_at'], full):
        raise ValueError('Candidate differs from bounded reviewed merge')
    return True
