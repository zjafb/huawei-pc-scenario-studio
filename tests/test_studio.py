"""Presentation checks: truthful milestones and safe rendering; no network."""
import unittest
from unittest.mock import patch
from app import full_pipeline,ui
from app.pipeline import Report
from app.studio import workflow,studio_css,studio_js

class StudioChecks(unittest.TestCase):
    def test_missing_input_stops_before_sources_and_model(self):
        events=[]
        with patch('app.catalog.find_product',return_value=None):
            report=full_pipeline.run_task(product='',scene='',platform='',on_progress=events.append)
        self.assertEqual('need_info',report.status)
        self.assertEqual([0,-1],[event['stage'] for event in events])
        self.assertEqual('need_info',events[-1]['state'])
        self.assertEqual(events,report.run['stages'])

    def test_terminal_failure_does_not_turn_unexecuted_nodes_green(self):
        markup=workflow({'stage':-1,'last_stage':1,'state':'failed','detail':'<unsafe>'})
        self.assertEqual(1,markup.count('flow-node done'))
        self.assertEqual(2,markup.count('flow-node waiting'))
        self.assertIn('&lt;unsafe&gt;',markup)
        self.assertNotIn('<unsafe>',markup)

    def test_stream_returns_only_the_real_result_at_completion(self):
        def actual(*args,on_progress):
            on_progress({'stage':2,'state':'active','detail':'model actually started'})
            on_progress({'stage':3,'state':'restricted','detail':'images unavailable'})
            return tuple('actual-'+str(i) for i in range(10))
        with patch.object(ui,'run_ui',side_effect=actual):updates=list(ui.run_ui_stream())
        self.assertEqual(2,len(updates))
        self.assertEqual(tuple('actual-'+str(i) for i in range(10)),updates[-1][:10])
        self.assertIn('受限完成',updates[-1][-1])

    def test_stream_processing_error_keeps_downloads_and_draft_empty(self):
        with patch.object(ui,'run_ui',side_effect=ValueError('synthetic')):result=list(ui.run_ui_stream())[-1]
        self.assertEqual([],result[6]);self.assertIsNone(result[7]);self.assertIsNone(result[9])
        self.assertNotIn('story-card',result[3]);self.assertIn('执行未通过',result[-1])

    def test_local_fonts_and_both_motion_controls_are_present(self):
        css=studio_css();js=studio_js()
        self.assertIn('data:font/woff2;base64,',css)
        self.assertIn('prefers-reduced-motion:reduce',css)
        self.assertIn('html[data-motion=off]',css)
        self.assertNotIn('setInterval',js);self.assertNotIn('setTimeout',js)
        self.assertIn('aria-pressed',js)

if __name__=='__main__':unittest.main()
