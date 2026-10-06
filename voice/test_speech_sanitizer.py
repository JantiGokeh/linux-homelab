import unittest

from speech import sanitize_for_speech


class SpeechSanitizerTests(unittest.TestCase):
    def test_removes_markdown_without_removing_words(self):
        source = "- **Overcast**: Cloudy.\n- `Rainy`: Wet."
        self.assertEqual(sanitize_for_speech(source), "Overcast: Cloudy. Rainy: Wet.")

    def test_replaces_markdown_link_with_label(self):
        self.assertEqual(
            sanitize_for_speech("See [the forecast](https://example.com)."),
            "See the forecast.",
        )


if __name__ == "__main__":
    unittest.main()
