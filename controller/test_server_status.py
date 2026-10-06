import json
import tempfile
import time
import unittest
from pathlib import Path
from server_status import read_status, format_status
from tooling import deterministic_tool_request


class ServerStatusTests(unittest.TestCase):
    def test_status_questions_and_no_mutations(self):
        registry = {'server.status': {}}
        for text in ('How is the server doing?', 'Are n8n and Pi-hole running?', 'How much memory and disk space are available?'):
            self.assertEqual(deterministic_tool_request(text, registry)['tool'], 'server.status')
        request = deterministic_tool_request('How much memory and disk space are available?', registry)
        self.assertEqual(request['focus'], ['memory', 'disk'])
        for text in ('Restart the server', 'Stop the running containers', 'Explain how memory works'):
            self.assertIsNone(deterministic_tool_request(text, registry))

    def test_stale_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            path.write_text(json.dumps({'collected_at': time.time() - 300}))
            with self.assertRaises(ValueError):
                read_status(path)
            path.write_text(json.dumps({'collected_at': time.time(), 'ok': True}))
            self.assertTrue(read_status(path)['ok'])

    def test_reports_stopped_and_unhealthy_without_false_reassurance(self):
        services = {name: {'state': 'running', 'health': 'not reported'} for name in ('pihole', 'n8n', 'navidrome', 'val-model')}
        services['pihole']['health'] = 'unhealthy'
        services['n8n']['state'] = 'exited'
        text = format_status({'cpu_percent': 5, 'memory_total': 8 * 1024**3, 'memory_available': 3 * 1024**3, 'disk_free': 100 * 1024**3, 'disk_total': 500 * 1024**3, 'services': services})
        self.assertIn('Pi-hole: running, health check unhealthy', text)
        self.assertIn('n8n: exited', text)
        self.assertIn('5.0 of 8.0 GiB used', text)

    def test_focused_status_omits_unrequested_sections(self):
        services = {name: {'state': 'running', 'health': 'not reported'} for name in ('pihole', 'n8n', 'navidrome', 'val-model')}
        result = {'cpu_percent': 5, 'memory_total': 8 * 1024**3, 'memory_available': 3 * 1024**3, 'disk_free': 100 * 1024**3, 'disk_total': 500 * 1024**3, 'services': services}
        text = format_status(result, ['n8n', 'pihole'])
        self.assertIn('Pi-hole: running', text)
        self.assertIn('n8n: running', text)
        self.assertNotIn('Memory:', text)
        self.assertNotIn('Disk:', text)


if __name__ == '__main__':
    unittest.main()
