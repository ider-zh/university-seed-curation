"""The unified workflow must not silently bypass Review or refresh sources."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from university_curation import native_review, unified_publish
from university_curation import web_sources


class UnifiedWorkflowTests(unittest.TestCase):
    def test_review_requires_snapshot_for_direct_publication(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/'.private'/'review'
            root.mkdir(parents=True)
            (root/'job.json').write_text('{"type":"native-review-job-v1","shared_source_cache":true,"offline_research_snapshot":false}')
            attempt=root/'compile-attempts'/'attempt'; attempt.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError,'offline Research-snapshot'):
                unified_publish._verified(Path(directory),'base',{},root,attempt,{}, {},'digest')

    def test_research_prompt_has_bounded_external_budget(self):
        from university_curation.native_research import _prompt
        prompt=_prompt({'qid':'Q1'},'review policy')
        for requirement in ('Stage 1:', 'Stage 2:', '8 external search queries',
                            '12 opened external pages', '5 external domains',
                            '2 navigation hops', '15 minutes'):
            self.assertIn(requirement, prompt)

    def test_review_prompt_prohibits_repeat_fetch(self):
        prompt=native_review._prompt({'qid':'Q1'},'review policy')
        self.assertIn('Do not fetch sources again',prompt)

    @patch('university_curation.web_sources._host',return_value='university.example')
    def test_external_captures_are_bounded_and_reviewable_offline(self,_host):
        with TemporaryDirectory() as directory:
            directory=Path(directory)/'.private'/'external'; directory.mkdir(parents=True)
            sources={}; corpus={}; calls=[]
            def fake_fetch(url):
                calls.append(url)
                return [{'locator':'paragraph:1','text':'Founded in 1888 as a higher education institution.'}]
            leads={'search_queries':['university founding official'], 'elapsed_seconds':20,
                   'pages':[{'url':'https://university.example/history','publisher_role':'institution_official',
                             'query_index':0,'depth':0}]}
            report=web_sources.collect(leads,sources,corpus,directory,fetch=fake_fetch)
            self.assertEqual((report['queries'],report['pages'],report['domains']),(1,1,1))
            self.assertEqual(len(calls),1)
            web_sources.verify_packet({'sources':sources,'source_corpus':corpus})
            web_sources.collect(leads,{}, {},directory,fetch=fake_fetch)
            self.assertEqual(len(calls),1)  # 30-day capture reuse without new HTTP
            corpus['s1'][0]['text']='tampered claim'
            with self.assertRaisesRegex(ValueError,'digest mismatch'):
                web_sources.verify_packet({'sources':sources,'source_corpus':corpus})

    def test_external_budget_hard_limits(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'budget exceeded'):
                web_sources.collect({'search_queries':['search']*9,'elapsed_seconds':1,'pages':[]},
                                    {},{},Path(directory)/'.private'/'web')

    @patch('university_curation.web_sources._host',return_value='university.example')
    def test_optional_page_failure_preserves_other_captures_and_budget(self,_host):
        with TemporaryDirectory() as directory:
            sources={'s1':{'kind':'wikidata'}}; corpus={'s1':[]}
            leads={'search_queries':['official history'],'elapsed_seconds':1,'pages':[
                {'url':'https://university.example/'+path,'publisher_role':'institution_official',
                 'query_index':0,'depth':0} for path in ('failed','success')]}
            def fetch(url):
                if url.endswith('failed'): raise TimeoutError('unavailable')
                return [{'locator':'paragraph:1','text':'A captured institutional history.'}]
            report=web_sources.collect(leads,sources,corpus,Path(directory)/'.private',fetch=fetch)
            self.assertEqual(report['pages'],2)
            self.assertEqual(len(report['retrieval_failures']),1)
            self.assertEqual(len(report['captures']),1)
            self.assertEqual(set(sources),{'s1','s2'})
            self.assertTrue(sources['s2']['url'].endswith('success'))
            web_sources.verify_packet({'sources':sources,'source_corpus':corpus})

    @patch('university_curation.web_sources._host',side_effect=web_sources.ExternalSourceUnavailable('DNS failed'))
    def test_dns_failure_returns_a_disclosed_incomplete_survey(self,_host):
        with TemporaryDirectory() as directory:
            leads={'search_queries':['official'],'elapsed_seconds':1,'pages':[
                {'url':'https://university.example/','publisher_role':'institution_official',
                 'query_index':0,'depth':0}]}
            report=web_sources.collect(leads,{}, {},Path(directory)/'.private')
            self.assertEqual(report['captures'],[])
            self.assertEqual((report['pages'],report['domains']),(1,1))
            self.assertEqual(len(report['retrieval_failures']),1)

    @patch('university_curation.web_sources._host',side_effect=ValueError('non-public IP'))
    def test_contract_violations_still_fail_closed(self,_host):
        with TemporaryDirectory() as directory:
            leads={'search_queries':['official'],'elapsed_seconds':1,'pages':[
                {'url':'https://university.example/','publisher_role':'institution_official',
                 'query_index':0,'depth':0}]}
            with self.assertRaisesRegex(ValueError,'non-public'):
                web_sources.collect(leads,{}, {},Path(directory)/'.private')

    def test_unreadable_page_is_a_failed_capture(self):
        response=MagicMock()
        response.__enter__.return_value=response
        response.headers.get_content_type.return_value='text/html'
        response.headers.get_content_charset.return_value='utf-8'
        response.read.return_value=b'\xff\xfe unreadable'
        with patch.object(web_sources,'build_opener') as opener:
            opener.return_value.open.return_value=response
            with self.assertRaisesRegex(web_sources.ExternalSourceUnavailable,'decoding failed'):
                web_sources._fetch('https://university.example/')


if __name__=='__main__': unittest.main()
