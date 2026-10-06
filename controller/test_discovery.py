import unittest

from discovery import format_discovery, public_result_url
from tooling import deterministic_tool_request


class DiscoveryTests(unittest.TestCase):
    def test_routes_news_and_web_search(self):
        registry = {'news.headlines': {}, 'web.search': {}}
        self.assertEqual(deterministic_tool_request('What are the latest headlines?', registry)['tool'], 'news.headlines')
        request = deterministic_tool_request('Search the web for Debian backup tools', registry)
        self.assertEqual(request['tool'], 'web.search')
        self.assertEqual(request['arguments']['query'], 'Debian backup tools')

    def test_blocks_private_result_links(self):
        for url in ('http://127.0.0.1:8092/health', 'http://10.0.0.2:5678', 'http://n8n.local/'):
            self.assertIsNone(public_result_url(url))
        self.assertEqual(public_result_url('https://example.com/article'), 'https://example.com/article')

    def test_spoken_result_points_to_explore(self):
        text = format_discovery({'kind': 'search', 'query': 'Debian', 'count': 1, 'results': [{'title': 'Debian home page'}]})
        self.assertIn('Debian home page', text)
        self.assertIn('Explore', text)


if __name__ == '__main__':
    unittest.main()
