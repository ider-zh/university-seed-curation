import unittest
from copy import deepcopy
from university_curation.review_scope import scope, receipt_scope, validate_receipt, secondary_request

class ReviewScopeTests(unittest.TestCase):
    def delta(self):
        field=lambda value:{'candidates':[{'id':'c1','value':value,'evidence':[]}]}
        return {'qid':'Q1','curation':{'identity_status':'in_scope'},
            'identity':{'name':field('University')},'population':{'students_total':field(100)},
            'finance':{'budget':field(1000)},'leadership':{'president':field('Leader')},
            'profile':{'motto':field('Motto'),'summary':field('Overview')},
            'locations':[{'id':'campus','kind':'campus','address':field({'country_name':'Example','street':'Street'}),
                          'coordinates':field({'latitude':1,'longitude':2}),'campus_count':field(3)}],
            'history':{'milestones':[{'id':'foundation','kind':'institution_establishment','subject_ref':'institution','date':field(1900)},
                                     {'id':'opening','kind':'campus_opening','subject_ref':'location:campus','date':field(2000)}]}}
    def test_core_scope_excludes_secondary_but_preserves_country_and_subject(self):
        facts,contexts,skipped=scope(self.delta()); paths={r['field'] for r in facts}
        self.assertIn('$.population.students_total',paths); self.assertIn('$.finance.budget',paths)
        self.assertIn('$.history.milestones[0].date',paths)
        self.assertIn('$.history.milestones[1].date:c1',skipped)
        self.assertIn('$.leadership.president:c1',skipped); self.assertIn('$.profile.motto:c1',skipped)
        self.assertIn('$.locations[0].campus_count:c1',skipped)
        self.assertTrue(any(c['id']=='location:campus' for c in contexts))
        country=next(c for c in contexts if c['id'].startswith('country:'))
        self.assertEqual(country['country'],{'country_name':'Example'})
    def test_missing_or_forged_receipt_scope_rejected(self):
        d=self.delta(); f,c,_=scope(d)
        verdict={'review_scope':receipt_scope(d),'facts_checked':len(f),'contexts_checked':len(c)}
        validate_receipt(d,verdict)
        verdict['review_scope']['reviewed_ids'].pop()
        with self.assertRaises(ValueError): validate_receipt(d,verdict)
        with self.assertRaises(ValueError): validate_receipt(d,{})
    def test_only_unambiguous_secondary_objections_are_waived(self):
        self.assertTrue(secondary_request({'field':'leadership.chair.preferred','category':'scope_conflict'}))
        self.assertFalse(secondary_request({'field':'profile.summary','category':'subject_mismatch'}))
        self.assertFalse(secondary_request({'field':'identity','category':'evidence_gap'}))
        self.assertFalse(secondary_request({'field':'location_address','category':'evidence_gap'}))
