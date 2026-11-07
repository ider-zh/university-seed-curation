"""Narrow compatibility for a frozen Review affected by refresh-only changes."""
import unittest
from unittest.mock import patch

from university_curation import workflow_contract as contract
from university_curation.research_schema import GROUPS


class ReviewContractCompatibilityTests(unittest.TestCase):
    def test_known_refresh_only_compiler_transition_is_allowed(self):
        outputs = [b'', (contract._NATIVE_REVIEW_PATH + '\n').encode(),
                   b'1ccce38fd841a4656bb925f907386dbfb655adde\n',
                   b'f8f4111d5e3892a6b2b3bb7a4c9d93c8c057e58f\n']
        with patch.object(contract, 'commit', side_effect=lambda repo, ref: ref), \
             patch.object(contract, 'git', side_effect=outputs):
            contract.check_publication_base('.', 'old', 'new')

    def test_unknown_compiler_transition_is_still_blocked(self):
        outputs = [b'', (contract._NATIVE_REVIEW_PATH + '\n').encode(),
                   b'1ccce38fd841a4656bb925f907386dbfb655adde\n',
                   b'0' * 40 + b'\n']
        with patch.object(contract, 'commit', side_effect=lambda repo, ref: ref), \
             patch.object(contract, 'git', side_effect=outputs), \
             self.assertRaisesRegex(ValueError, 'Review contract changed'):
            contract.check_publication_base('.', 'old', 'new')

    def test_unrelated_contract_change_is_still_blocked(self):
        outputs = [b'', b'docs/review-scope-v3.md\n']
        with patch.object(contract, 'commit', side_effect=lambda repo, ref: ref), \
             patch.object(contract, 'git', side_effect=outputs), \
             self.assertRaisesRegex(ValueError, 'Review contract changed'):
            contract.check_publication_base('.', 'old', 'new')

    def test_frozen_full_refresh_must_match_current_survey_rules(self):
        statuses = {g: 'checked' for g in GROUPS}
        statuses['population'] = 'not_found'
        proposal = {'coverage': [{'group': g, 'status': statuses[g]} for g in GROUPS],
                    'retrieval_failures': [], 'delta': {'curation': {'identity_status': 'in_scope'}}}
        verdict = {'decision': 'approve',
                   'coverage_checks': [{'group': g, 'status': statuses[g]} for g in GROUPS],
                   'full_refresh': True}
        contract.check_review_refresh(proposal, verdict)
        statuses['finance'] = 'disputed'
        proposal['coverage'][GROUPS.index('finance')]['status'] = 'disputed'
        verdict['coverage_checks'][GROUPS.index('finance')]['status'] = 'disputed'
        with self.assertRaisesRegex(ValueError, 'full_refresh'):
            contract.check_review_refresh(proposal, verdict)
        verdict['full_refresh'] = False
        contract.check_review_refresh(proposal, verdict)
        statuses['finance'] = 'checked'
        proposal['coverage'][GROUPS.index('finance')]['status'] = 'checked'
        verdict['coverage_checks'][GROUPS.index('finance')]['status'] = 'checked'
        proposal['retrieval_failures'] = [{'error': 'TimeoutError'}]
        contract.check_review_refresh(proposal, verdict)


if __name__ == '__main__':
    unittest.main()
