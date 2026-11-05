"""The unified workflow must not silently bypass Review or refresh sources."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from university_curation import native_review, unified_publish


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


if __name__=='__main__': unittest.main()
