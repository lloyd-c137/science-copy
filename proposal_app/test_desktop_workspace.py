"""Background registration must never open an empty Desktop conversation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from proposal_app.desktop_workspace import ensure_workspace_project

class DesktopWorkspaceTests(unittest.TestCase):
    def test_create_then_reuse_without_opening_desktop(self):
        with tempfile.TemporaryDirectory(prefix='研究 & # ') as directory:
            folder=Path(directory).resolve();project={'id':'native','roots':[{'path':str(folder)}]};rpc=MagicMock()
            rpc.request.side_effect=[{}, {'data':[]}, {'project':project}]
            with patch('proposal_app.desktop_workspace._Rpc',return_value=rpc),patch('proposal_app.desktop_workspace.os.startfile',create=True) as opened:
                result=ensure_workspace_project(folder)
                self.assertEqual(result['project_id'],'native');opened.assert_not_called()
            calls=rpc.request.call_args_list
            self.assertEqual([c.args[0] for c in calls],['config/value/write','project/list','project/create'])
            self.assertEqual(calls[-1].args[1]['roots'],project['roots'])
            first_key=calls[-1].args[1]['idempotencyKey']
            rpc.request.reset_mock();rpc.request.side_effect=[{}, {'project':project}]
            with patch('proposal_app.desktop_workspace._Rpc',return_value=rpc):
                self.assertEqual(ensure_workspace_project(folder)['project_id'],'native')
            self.assertEqual([c.args[0] for c in rpc.request.call_args_list],['config/value/write','project/read'])
            (folder/'.coach/desktop-project.json').unlink()
            rpc.request.reset_mock();rpc.request.side_effect=[{}, {'data':[]}, {'project':project}]
            with patch('proposal_app.desktop_workspace._Rpc',return_value=rpc):ensure_workspace_project(folder)
            self.assertEqual(rpc.request.call_args_list[-1].args[1]['idempotencyKey'],first_key)

    def test_creation_failure_does_not_fall_back_to_blank_window(self):
        with tempfile.TemporaryDirectory() as directory:
            rpc=MagicMock();rpc.request.side_effect=[{}, {'data':[]}, RuntimeError('unsupported')]
            with patch('proposal_app.desktop_workspace._Rpc',return_value=rpc),patch('proposal_app.desktop_workspace.os.startfile',create=True) as opened:
                self.assertEqual(ensure_workspace_project(directory)['status'],'error');opened.assert_not_called()
            self.assertFalse((Path(directory)/'.coach/desktop-project.json').exists())
            rpc.close.assert_called_once()

    def test_existing_project_and_connection_are_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory).resolve();rpc=MagicMock()
            rpc.request.side_effect=[{}, {'data':[{'id':'existing','roots':[{'path':str(folder)}]}]}]
            with patch('proposal_app.desktop_workspace._Rpc',return_value=rpc):result=ensure_workspace_project(folder,keep_connection=True)
            self.assertIs(result['_rpc'],rpc);rpc.close.assert_not_called()
            self.assertEqual(result['project_id'],'existing')

    def test_wrong_root_cannot_be_registered(self):
        with tempfile.TemporaryDirectory() as directory:
            rpc=MagicMock();rpc.request.side_effect=[{}, {'data':[]}, {'project':{'id':'wrong','roots':[]}}]
            with patch('proposal_app.desktop_workspace._Rpc',return_value=rpc):self.assertEqual(ensure_workspace_project(directory)['status'],'error')
            self.assertFalse((Path(directory)/'.coach/desktop-project.json').exists())

    def test_missing_folder_does_not_start_connection(self):
        with tempfile.TemporaryDirectory() as directory,patch('proposal_app.desktop_workspace._Rpc') as factory:
            self.assertEqual(ensure_workspace_project(Path(directory)/'missing')['status'],'error');factory.assert_not_called()
