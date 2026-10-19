"""Provider-limit regressions, with no network requests or real waits."""
import copy
import unittest
from unittest.mock import Mock, patch

import test_full_catalog as fixtures
from app import full_pipeline as flow, ui
from app.model_budget import BudgetedModel
from connectors import ConnectorError


class ModelLimitTests(unittest.TestCase):
    @patch('app.model_budget.time.sleep')
    def test_transient_limit_retries_within_shared_budget(self, sleep):
        client = Mock()
        client.timeout = 60
        client.chat_json.side_effect = [ConnectorError('burst', kind='rate_limit', retry_after=8), {'ok': True}]
        run = {}; progress = []
        budget = BudgetedModel(client, run, on_wait=progress.append)
        self.assertEqual({'ok': True}, budget.chat_json([{'role': 'user', 'content': 'test'}]))
        self.assertEqual(2, client.chat_json.call_count)
        self.assertEqual(2, len(run['model_calls']))
        self.assertEqual('rate_limit', run['model_calls'][0]['failure_kind'])
        sleep.assert_called_once_with(8)
        self.assertTrue(progress)
        self.assertEqual(60, client.timeout)

    @patch('app.model_budget.time.sleep')
    def test_persistent_limit_stops_at_four_actual_requests(self, sleep):
        client = Mock(); client.timeout = 60
        client.chat_json.side_effect = ConnectorError('token throughput', kind='token_rate_limit')
        run = {}; budget = BudgetedModel(client, run)
        with self.assertRaises(ConnectorError) as raised:
            budget.chat_json([])
        self.assertEqual('token_rate_limit', raised.exception.kind)
        self.assertEqual(4, client.chat_json.call_count)
        self.assertEqual(4, len(run['model_calls']))
        self.assertEqual([5, 10, 20], [c.args[0] for c in sleep.call_args_list])

    @patch('app.model_budget.time.sleep')
    def test_exhausted_quota_and_network_errors_never_retry(self, sleep):
        for kind in ('quota', 'network_error', 'http_error'):
            client = Mock(); client.timeout = 60
            client.chat_json.side_effect = ConnectorError('stop', kind=kind)
            with self.assertRaises(ConnectorError):
                BudgetedModel(client, {}).chat_json([])
            self.assertEqual(1, client.chat_json.call_count)
        sleep.assert_not_called()

    @patch('app.model_budget.time.sleep')
    @patch('app.model_budget.time.monotonic', return_value=100)
    def test_no_wait_when_deadline_cannot_accommodate_retry(self, monotonic, sleep):
        client = Mock(); client.timeout = 60
        client.chat_json.side_effect = ConnectorError('busy', kind='rate_limit', retry_after=30)
        with self.assertRaises(ConnectorError):
            BudgetedModel(client, {}, seconds=20).chat_json([])
        self.assertEqual(1, client.chat_json.call_count)
        sleep.assert_not_called()

    def test_final_review_limit_hides_draft_and_shows_actionable_diagnosis_once(self):
        fixture = fixtures.FullFlowChecks(); fixture.setUp()
        responses = [copy.deepcopy(fixture.output), ConnectorError('Free allocated quota exceeded.', kind='quota', code=429)]
        with patch.object(flow.BudgetedModel, '_attempt', side_effect=responses):
            report, _ = fixture.execute(fixture.output)
        self.assertEqual('failed', report.status)
        self.assertEqual('quota', report.run['failure_kind'])
        self.assertIn('表达与需求复核', report.message)
        self.assertIn('在线模型', report.message)
        self.assertEqual(429, report.run['model_error']['http_status'])
        self.assertNotIn('story-card', ui.rich_article(report))
        banner = ui._banner(report)
        self.assertIn('模型服务受限', banner)
        self.assertEqual(1, banner.count(report.message))


if __name__ == '__main__':
    unittest.main()
