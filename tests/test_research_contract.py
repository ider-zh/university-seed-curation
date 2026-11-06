from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/skills/university-curation/scripts/lib'))
from university_curation import research_contract as jobs
from university_curation.records import ROOT
from university_curation.research_schema import GROUPS
from test_research_schema import fixture

class ResearchContractTests(unittest.TestCase):

    def test_review_reconstructs_root_p625_from_independent_entity(self):
        transport, packet = fixture()
        packet['sources']['s2'] = {'kind': 'wikidata', 'url': 'https://www.wikidata.org/w/index.php?oldid=3', 'publisher_role': 'knowledge_base', 'family': 'wikimedia', 'source_qid': 'Q101', 'revision_id': 3, 'retrieved_at': '2026-11-05T00:00:00Z'}
        root = {'id': 'Q101', 'lastrevid': 3, 'claims': {'P625': [{'id': 'Q101$abc', 'rank': 'normal', 'mainsnak': {'property': 'P625', 'datatype': 'globe-coordinate', 'snaktype': 'value', 'datavalue': {'type': 'globecoordinate', 'value': {'latitude': 0, 'longitude': 10, 'precision': 0.01, 'globe': 'http://www.wikidata.org/entity/Q2'}}}}]}}
        packet['source_corpus']['s2'] = jobs.wikidata_corpus(root, {}, ['en'], True)
        packet = jobs.coordinate_aliases(packet)
        delta, _, _ = jobs.compile_delta(transport, packet)
        seed = {'import_id': 'catalog', 'screening_status': 'needs_review', 'channels': ['primary']}
        delta['seed'] = seed
        delta, point = jobs.coordinate_delta(delta, root, packet)
        at = '2026-11-05T00:01:00Z'
        proposal = {'type': 'university-proposal-v1', 'review_status': 'unreviewed', 'qid': 'Q101', 'seed': seed, 'baseline_sha256': 'absent', 'delta': delta, 'candidate': jobs.materialize(None, delta, seed, at, False), 'proposed_at': at, 'coverage': [{'group': x['group'], 'status': x['status']} for x in transport['coverage']], 'retrieval_failures': [], 'open_requests': [], 'research': {'model': jobs.MODEL, 'reasoning_effort': jobs.EFFORT, 'session': 'research', 'prompt_sha256': 'a' * 64, 'schema_sha256': 'b' * 64}}
        self.assertEqual(jobs._verify_proposal(proposal, None, packet, root), point)
        changed = deepcopy(root)
        changed['claims']['P625'][0]['mainsnak']['datavalue']['value']['latitude'] = 1
        with self.assertRaises(ValueError):
            jobs._verify_proposal(proposal, None, packet, changed)

    def test_no_wikipedia_sitelink_does_not_invent_language(self):
        self.assertEqual(jobs.source_languages({'sitelinks': {}, 'claims': {}}), [])

    def test_public_reasons_allow_sources_and_locale_but_not_secrets(self):
        self.assertEqual(jobs._safe_reason('See https://www.wikidata.org/wiki/Q101 and sk-SK locale.'), 'See https://www.wikidata.org/wiki/Q101 and sk-SK locale.')
        for text in ('See .private/source.json', 'Token sk-abcdefghijklmnop1234', 'C:\\private\\record.json', 'Token ghp_abcdefghijklmnop1234', 'Token github_pat_abcdefghijklmnop1234'):
            with self.assertRaises(ValueError):
                jobs._safe_reason(text)

    def test_request_feedback_is_bounded_and_root_coordinates_reserved(self):
        with self.assertRaises(ValueError):
            jobs._open_requests({'open_requests': [{'request_id': 'x'}]})
        proposal, packet = fixture()
        packet['sources']['s2'] = {'kind': 'wikidata', 'source_qid': 'Q101'}
        packet['source_corpus']['s2'] = [{'locator': 'claim:P625:0', 'text': '{"statement_id":"Q101$abc"}'}]
        fact = deepcopy(proposal['facts'][0])
        fact['field'] = 'location.coordinates'
        fact['evidence'] = [{'source_ref': 's2', 'locator': 'statement:Q101$abc', 'original_text': 'x'}]
        proposal['facts'].append(fact)
        with self.assertRaisesRegex(ValueError, 'script-owned'):
            jobs.guard_root_coordinates(proposal, packet)
if __name__ == '__main__':
    unittest.main()
