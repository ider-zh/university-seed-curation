from copy import deepcopy
from collections import Counter
import unittest
from university_curation.coordinates import projection
from university_curation.research_contract import coordinate_delta
from university_curation.preferred import validate
from university_curation.records import ROOT, encode, record_path
from test_research_schema import fixture
from university_curation.research_schema import compile_record
NOW='2026-11-05T00:00:00Z'

class CoordinateStorageTests(unittest.TestCase):

    def setUp(self):
        proposal, packet = fixture()
        self.record = compile_record(proposal, packet)[0]
        self.record['update_datetime']=NOW
        self.record['curation'].update(reviewed_groups=['identity','geography','history','population','finance','profile'],refresh_profile='core-v1')
        self.record['sources']['s2'] = {'kind': 'wikidata', 'source_qid': 'Q101', 'revision_id': 5, 'url': 'https://www.wikidata.org/w/index.php?oldid=5', 'retrieved_at': NOW, 'publisher_role': 'knowledge_base', 'family': 'wikimedia'}
        self.entity = {'id': 'Q101', 'lastrevid': 5, 'claims': {'P625': [self.claim()]}}

    def claim(self, sid='Q101$ABC-123', lat=0, lon=0, state='value', rank='normal'):
        snak = {'property': 'P625', 'snaktype': state}
        if state == 'value':
            snak['datavalue'] = {'type': 'globecoordinate', 'value': {'latitude': lat, 'longitude': lon, 'precision': 0.0001, 'globe': 'http://www.wikidata.org/entity/Q2', 'altitude': None}}
        return {'id': sid, 'rank': rank, 'mainsnak': snak}

    def test_root_coordinate_is_preserved_despite_other_site_and_zero_is_valid(self):
        self.record['locations'][0]['coordinates'] = {'candidates': [{'id': 'c1', 'value': {'latitude': 25, 'longitude': 102, 'crs': 'EPSG:4326'}, 'verification': 'supported', 'evidence': [{'source_ref': 's1', 'locator': 'lead'}]}]}
        from university_curation.preferred import recompute
        self.record = recompute(self.record)
        point = projection(self.record, self.entity)
        result = coordinate_delta(self.record,self.entity)[0]
        self.assertEqual(result['locations'][:-1], self.record['locations'])
        value = result['locations'][-1]['coordinates']['candidates'][0]['value']
        self.assertEqual(value['latitude'], 0)
        self.assertEqual(value['source_precision_degrees'], 0.0001)
        self.assertNotIn('accuracy_metres', value)
        self.assertEqual(result['locations'][-1]['kind'], 'institution')
        self.assertEqual(result['update_datetime'], self.record['update_datetime'])

    def test_lowercase_wikidata_statement_prefix_keeps_original_locator(self):
        self.entity['claims']['P625'] = [self.claim('q101$abc-123', 52.16, 21.04)]
        point = projection(self.record, self.entity)
        self.assertEqual(point['statements'][0]['statement_id'], 'q101$abc-123')
        result = coordinate_delta(self.record,self.entity)[0]
        evidence = result['locations'][-1]['coordinates']['candidates'][0]['evidence'][0]
        self.assertEqual(evidence['locator'], 'statement:q101$abc-123')
        for foreign in ('q102$abc-123', 'q101abc-123', 'Q101$', 'Q101$abc_123'):
            self.entity['claims']['P625'] = [self.claim(foreign)]
            with self.subTest(foreign=foreign), self.assertRaisesRegex(ValueError, 'foreign Wikidata statement'):
                projection(self.record, self.entity)

    def test_linked_item_wrong_revision_non_earth_and_qualified_points_fail_closed(self):
        for mutation in (lambda e: e.update(id='Q174091'), lambda e: e.update(lastrevid=6), lambda e: e['claims']['P625'][0]['mainsnak']['datavalue']['value'].update(globe='http://www.wikidata.org/entity/Q111'), lambda e: e['claims']['P625'][0].update(qualifiers={'P585': [1]})):
            entity = deepcopy(self.entity)
            mutation(entity)
            with self.subTest(entity=entity), self.assertRaises(ValueError):
                projection(self.record, entity)

    def test_unknown_novalue_deprecated_and_multi_point_coverage(self):
        self.entity['claims']['P625'] = [self.claim('Q101$C', state='somevalue'), self.claim('Q101$D', state='novalue'), self.claim('Q101$E', rank='deprecated'), self.claim('Q101$B', 10, 20), self.claim('Q101$A', 11, 21, rank='preferred')]
        point = projection(self.record, self.entity)
        result = coordinate_delta(self.record,self.entity)[0]
        field = result['locations'][-1]['coordinates']
        self.assertEqual(len(field['candidates']), 4)
        self.assertEqual(field['candidates'][0]['value']['latitude'], 11)
        self.assertEqual(field['candidates'][2]['value_state'], 'unknown')
        self.assertEqual(field['candidates'][3]['value_state'], 'no_value')
        self.assertIn('conflicting_candidates', field['preferred']['qualifications'])
        for state in ('somevalue', 'novalue'):
            self.entity['claims']['P625'] = [self.claim('Q101$A', state=state, rank='preferred'), self.claim('Q101$B', 10, 20)]
            result = coordinate_delta(self.record,self.entity)[0]
            self.assertNotIn('preferred', result['locations'][-1]['coordinates'])
            self.assertEqual(result['locations'][-1]['coordinates']['candidates'][0]['source_rank'], 'preferred')

    def test_50000_records_fit_256_buckets(self):
        counts = Counter((record_path(ROOT, 'Q' + str(i)).parent.name for i in range(1, 50001)))
        self.assertEqual(len(counts), 256)
        self.assertTrue(all((100 < n < 300 for n in counts.values())))
