"""Versioned independent factual review scope; structural checks still cover all fields."""

VERSION = 'core-review-v3'
KEY_EVENTS = {'predecessor_establishment', 'vocational_origin', 'institution_establishment',
              'higher_education_status', 'university_status', 'charter', 'merger', 'split',
              'closure', 'reopening', 'jurisdiction_change'}


def secondary_request(row):
    # Only explicit secondary paths can retire historical objections. Unknown paths
    # and eligibility/subject/schema errors remain blocking, regardless of wording.
    field = row['field'].removeprefix('$.')
    return (field.startswith(('leadership.', 'profile.')) and
            row['category'] not in ('subject_mismatch', 'schema_error'))


def select(delta, facts, contexts):
    reviewed = []; skipped = []
    milestones = delta.get('history', {}).get('milestones', [])
    date_paths = {f'$.history.milestones[{i}].date' for i,m in enumerate(milestones)
                  if m['kind'] in KEY_EVENTS}
    for row in facts:
        path = row['field']
        critical = (path.startswith(('$.identity.', '$.relationships.')) or
                    '.population.' in path or '.finance.' in path or
                    path.endswith('.coordinates') or
                    path in date_paths)
        (reviewed if critical else skipped).append(row)
    selected = []
    used_subjects = {row['subject'] for row in reviewed}
    for row in contexts:
        if (row['id'] == 'identity' or row['id'] in used_subjects or
                row['id'].startswith('related:') or
                any(row['id'] == 'milestone:'+m['id'] and m['kind'] in KEY_EVENTS for m in milestones)):
            selected.append(row)
        else: skipped.append(row)
    # Country attribution is checked without expanding review to street addresses.
    for row in facts:
        if row['field'].endswith('.address'):
            country = {k:v for k,v in row['candidate'].get('value', {}).items()
                       if k in ('country_name', 'country_qid')}
            if country:
                selected.append({'id':'country:'+row['id'], 'subject':row['subject'],
                                 'country':country, 'evidence':row['candidate']['evidence']})
    return reviewed, selected, sorted(row['id'] for row in skipped)


def scope(delta):
    from .research_contract import _fact_scope
    return select(delta, *_fact_scope(delta))


def receipt_scope(delta):
    facts, contexts, skipped = scope(delta)
    return {'version':VERSION, 'reviewed_ids':sorted(r['id'] for r in facts+contexts),
            'not_independently_reviewed_ids':skipped}


def validate_receipt(delta, verdict):
    facts, contexts, _ = scope(delta)
    if (verdict.get('review_scope') != receipt_scope(delta) or
            verdict.get('facts_checked') != len(facts) or verdict.get('contexts_checked') != len(contexts)):
        raise ValueError('Review scope or coverage mismatch; prepare fresh core Review')
