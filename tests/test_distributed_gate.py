from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_gate as gate
from university_curation.attestations import sha, sign
from university_curation.distributed_protocol import signed_comment
from university_curation.records import encode

REPO, QID, PR = 'owner/repo', 'Q101', 8
HEAD, BASE = '1' * 40, '2' * 40


class Client:
    repository = REPO

    def __init__(self):
        self.heads = [HEAD]
        self.posts = []

    def pull(self, number):
        head = self.heads.pop(0) if len(self.heads) > 1 else self.heads[0]
        return {'number': number, 'base': {'ref': 'main'},
                'head': {'sha': head, 'repo': {'full_name': REPO}}, 'html_url': 'https://example.test/pr'}

    def request(self, method, path, body):
        self.posts.append((method, path, body))


class DistributedGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        private = Path(self.temp.name) / '.private'
        private.mkdir()
        self.trust = {'repository': REPO, 'keys': {}}
        self.keys = {}
        for role in ('research', 'review'):
            key = Ed25519PrivateKey.generate()
            path = private / (role + '.pem')
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            self.trust['keys']['review-' + sha(public)[:16]] = {'status': 'active', 'public_key_hex': public.hex(), 'roles': [role]}
            self.keys[role] = path
        self.proposal = {'qid': QID}
        self.research = self.signed(self.proposal, 'research')
        self.request_id = str(uuid.uuid4())
        self.decision = self.signed(self.approval())
        self.receipt = {'research': self.research, 'review': self.decision}
        self.notes = [self.comment(1, self.decision)]
        self.validation = {'task_kind': 'distributed_research', 'review_pr': PR, 'qids': [QID], 'batch_id': 'batch'}
        self.client = Client()
        self.patchers = [
            patch.object(gate, 'fetch_main', return_value=BASE),
            patch.object(gate, 'fetch_pull', return_value=HEAD),
            patch.object(gate, 'trust_at', return_value=self.trust),
            patch.object(gate, 'git', return_value=b'data/universities/aa/Q101.json\0'),
            patch.object(gate, 'validate_pr', side_effect=lambda *a: self.validation),
            patch.object(gate, 'blob', side_effect=lambda *a: encode(self.receipt)),
            patch.object(gate, 'comments', side_effect=lambda *a: self.notes),
        ]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.temp.cleanup)

    def signed(self, payload, role='review'):
        return sign(payload, self.keys[role], self.trust, role=role)

    def approval(self, responses=None):
        return {'type': 'university-review-decision-v1', 'repository': REPO, 'pr_number': PR,
                'qid': QID, 'reviewed_head_sha': HEAD, 'proposal_sha256': sha(encode(self.proposal)),
                'decision': 'approve', 'reviewed_at': '2026-11-05T01:00:00Z',
                'request_responses': responses or []}

    def objection(self):
        return self.signed({'type': 'university-review-objection-v1', 'repository': REPO, 'pr_number': PR,
            'qid': QID, 'reviewed_head_sha': HEAD, 'proposal_sha256': sha(encode(self.proposal)),
            'request_id': self.request_id, 'field': 'identity', 'category': 'evidence_gap',
            'reason': 'Check source', 'created_at': '2026-11-05T00:00:00Z'})

    @staticmethod
    def comment(number, document):
        return {'id': number, 'body': signed_comment(document)}

    def test_review_from_another_pr_is_rejected(self):
        self.validation['review_pr'] = PR + 1
        with self.assertRaisesRegex(ValueError, 'another PR'):
            gate.check('.', self.client, PR)

    def test_later_signed_objection_blocks_old_approval(self):
        self.notes.append(self.comment(2, self.objection()))
        with self.assertRaisesRegex(ValueError, 'Unresolved'):
            gate.check('.', self.client, PR)

    def test_latest_decision_must_match_receipt(self):
        changed = self.approval()
        changed['decision'] = 'request_changes'
        self.notes.append(self.comment(2, self.signed(changed)))
        with self.assertRaisesRegex(ValueError, 'latest'):
            gate.check('.', self.client, PR)

    def test_current_approval_resolves_prior_objection(self):
        decision = self.signed(self.approval([{'request_id': self.request_id, 'status': 'addressed'}]))
        self.receipt['review'] = decision
        self.notes = [self.comment(1, self.objection()), self.comment(2, decision)]
        self.assertEqual(gate.check('.', self.client, PR)['state'], 'success')

    def test_draft_is_pending(self):
        with patch.object(gate, 'git', return_value=b'data/proposals/batch/manifest.json\0'), \
             patch.object(gate, 'draft_snapshot', return_value=({}, {QID: self.research})):
            result = gate.check('.', self.client, PR)
        self.assertEqual(result['state'], 'pending')
        self.assertEqual(result['qids'], [QID])

    def test_head_change_prevents_posting_status(self):
        self.client.heads = [HEAD, '3' * 40]
        with patch.object(gate, 'check', return_value={'state': 'success', 'status': 'ok', 'head_sha': HEAD}):
            result = gate.update_status('.', self.client, PR)
        self.assertEqual(result['status'], 'superseded')
        self.assertEqual(self.client.posts, [])


if __name__ == '__main__':
    unittest.main()
