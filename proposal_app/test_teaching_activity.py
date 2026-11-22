import unittest
import json
import tempfile
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch
from proposal_app.teaching_context import brief
from proposal_app.coach_launcher import CoachLauncher
from proposal_app import workflow
from proposal_app.test_research_store import fixture, create
from proposal_app import research_service


class TeachingActivityTests(unittest.TestCase):
    def test_stage_change_clears_only_activity_selection(self):
        card = {'current_step': 1, 'tutor_mode': 'observation', 'focus_object_id': 'Q1',
                'research_state': {'tutor_mode': 'observation', 'focus_object_id': 'Q1', 'selected_deliverable': 'D1'},
                'research': {'tutor_mode': 'observation', 'focus_object_id': 'Q1', 'objects': ['kept']}}
        workflow.set_navigation_stage(card, 2)
        for container in (card, card['research_state'], card['research']):
            self.assertNotIn('tutor_mode', container)
            self.assertNotIn('focus_object_id', container)
        self.assertEqual(card['research_state']['selected_deliverable'], 'D1')
        self.assertEqual(card['research']['objects'], ['kept'])
        self.assertTrue(brief(card)['purpose'].startswith('B'))

    def test_same_stage_keeps_current_activity(self):
        card = {'current_step': 3, 'research_state': {'tutor_mode': 'problem', 'focus_object_id': 'P1'}}
        workflow.set_navigation_stage(card, 3)
        self.assertEqual(card['research_state'], {'tutor_mode': 'problem', 'focus_object_id': 'P1'})

    def test_completion_resets_old_activity_for_next_stage(self):
        connection, card, user = fixture()
        self.addCleanup(connection.close)
        card['research_state'] = {'tutor_mode': 'observation', 'focus_object_id': 'Q1'}
        # Synthetic confirmed objects isolate navigation from confirmation permissions.
        card['research']['objects'] = [dict(id=k, kind=k, status='confirmed', content={}) for k in ('curiosity', 'question')]
        workflow.save_progress(card, dict(step=1, workflow_version=workflow.VERSION, complete=True,
                                         confirmed=True, data={'summary': '观察与问法已核对', 'selection_reason': '继续辨认这条线索'}), user)
        self.assertEqual(card['current_step'], 2)
        self.assertNotIn('tutor_mode', card['research_state'])
        self.assertTrue(brief(card)['purpose'].startswith('B'))

    def test_teacher_reopening_resets_activity(self):
        for decision in ('supplement', 'redirect'):
            with self.subTest(decision=decision):
                connection, card, _ = fixture()
                self.addCleanup(connection.close)
                card.update(current_step=6, status='review', submitted_deliverable=dict(id='D', revision=1, activity_version=1))
                card['research_state'] = {'tutor_mode': 'review', 'focus_object_id': 'D', 'selected_deliverable': 'D'}
                card['research']['deliverables'] = [dict(id='D', revision=1, object_refs=[])]
                workflow.review(card, dict(decision=decision, step=4, value='价值依据', feasibility='需补证',
                                          deliverable='补核关键条件', owner='学生', due='2027-01-01'), dict(role='teacher', name='老师'))
                self.assertEqual(card['current_step'], 4 if decision == 'supplement' else 1)
                self.assertNotIn('focus_object_id', card['research_state'])
                self.assertEqual(card['research_state']['selected_deliverable'], 'D')

    def test_dependency_reopening_resets_activity_only_when_navigation_moves(self):
        connection, card, user = fixture()
        self.addCleanup(connection.close)
        create(connection, card, user, 'T1')
        card['current_step'] = 4
        for step in card['steps']:
            step['status'] = 'complete' if step['number'] < 4 else 'pending'
        card['steps'][3]['status'] = 'active'
        card['research_state'] = {'tutor_mode': 'method', 'focus_object_id': 'T1'}
        research_service._affected(connection, card, 'T1')
        self.assertEqual(card['current_step'], 1)
        self.assertNotIn('tutor_mode', card['research_state'])
        card['research_state'].update(tutor_mode='problem', focus_object_id='T1')
        research_service._affected(connection, card, 'T1')
        self.assertEqual(card['research_state']['tutor_mode'], 'problem')
        self.assertEqual(card['research_state']['focus_object_id'], 'T1')

    def test_explicit_activity_round_trip(self):
        card = {'current_step': 3, 'research_state': {'tutor_mode': 'problem'}}
        problem = brief(card)
        self.assertIn('Problem', problem['purpose'])
        card['research_state']['tutor_mode'] = 'method'
        self.assertIn('方法', brief(card)['purpose'])
        card['research_state']['tutor_mode'] = 'problem'
        self.assertEqual(problem, brief(card))
        self.assertEqual(card['current_step'], 3)

    def test_default_observation_does_not_override_later_stage(self):
        self.assertTrue(brief({'current_step': 4, 'tutor_mode': 'observation'})['purpose'].startswith('D'))

    def test_explicit_observation_can_return_to_exploration(self):
        card = {'current_step': 4, 'tutor_mode': 'observation', 'research_state': {'tutor_mode': 'observation'}}
        self.assertIn('观察', brief(card)['purpose'])

    def test_focus_resolves_activity_without_explicit_mode(self):
        card = {'current_step': 3, 'tutor_mode': 'observation', 'research': {'focus_object_id': 'P1', 'objects': [{'id': 'P1', 'kind': 'problem'}]}}
        self.assertIn('Problem', brief(card)['purpose'])

    def test_explicit_mode_wins_over_focus(self):
        card = {'current_step': 3, 'research': {'tutor_mode': 'method', 'focus_object_id': 'P1', 'objects': [{'id': 'P1', 'kind': 'problem'}]}}
        self.assertIn('方法', brief(card)['purpose'])

    def test_unknown_activity_falls_back_to_navigation(self):
        card = {'current_step': 3, 'research_state': {'tutor_mode': 'unknown'}}
        self.assertTrue(brief(card)['purpose'].startswith('C'))

    def test_existing_activity_names_keep_their_teaching_intent(self):
        cases = {'search_diagnosis': '检索', 'hypothesis_development': '解释',
                 'value_judgment': '价值', 'method_comparison': '方法',
                 'critical_validation': '验证', 'revision': '修订',
                 'prediction': '预测', 'questioning': '问法', 'grouping': 'Problem',
                 'searching': '检索', 'reading': '来源', 'reasoning': '解释',
                 'alignment': '核对', 'divergence': '问法'}
        for mode, meaning in cases.items():
            with self.subTest(mode=mode):
                self.assertIn(meaning, brief({'current_step': 6, 'research_state': {'tutor_mode': mode}})['purpose'])

    def test_launch_injects_same_activity_and_reference_as_project_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspaces = MagicMock()
            workspaces.visible.return_value = root
            (root / 'connection.json').write_text(json.dumps({'server': 'http://127.0.0.1:8765'}), 'utf-8')
            launcher = CoachLauncher(root, open_desktop=False, workspaces=workspaces)
            rpc = MagicMock()
            rpc.rows = Queue()
            requests = []
            def receive(raw):
                request = json.loads(raw)
                requests.append(request)
                if request.get('id') == 2:
                    rpc.rows.put({'id': 2, 'result': {'thread': {'id': '11111111-1111-4111-8111-111111111111'}}})
                elif request.get('id') == 3:
                    rpc.rows.put({'id': 3, 'result': {}})
                    rpc.rows.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
            rpc.process.stdin.write.side_effect = receive
            card = {'id': 'P1', 'student_name': '测试学生', 'current_step': 3,
                    'research_state': {'tutor_mode': 'problem'}, 'teaching_brief': {'purpose': '旧提示'}}
            with patch('proposal_app.coach_launcher.install_skill', return_value=Path(__file__).resolve().parent.parent / 'skills/research-proposal-coach'), patch('proposal_app.desktop_workspace.ensure_workspace_project', return_value={'status': 'ready', 'project_id': 'native-project', '_rpc': rpc}):
                launcher.run(('U1', 'P1'), root, root, 'codex', card)
            request = next(r for r in requests if r.get('id') == 2)
            instructions = request['params']['developerInstructions']
            self.assertIn(brief(card)['purpose'], instructions)
            self.assertIn(brief(card)['activity_reference'], instructions)
            self.assertNotIn('旧提示', instructions)


if __name__ == '__main__':
    unittest.main()
