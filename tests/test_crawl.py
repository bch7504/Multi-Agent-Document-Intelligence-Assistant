import unittest

from crawl import _crawl_exclude_dirs, _validate_url


class CrawlTests(unittest.TestCase):
    def test_validate_url_requires_an_absolute_http_url(self):
        self.assertEqual(_validate_url("https://example.com/docs"), "https://example.com/docs")
        for invalid_url in ("example.com", "file:///tmp/data", "javascript:alert(1)"):
            with self.subTest(invalid_url=invalid_url):
                with self.assertRaises(ValueError):
                    _validate_url(invalid_url)

    def test_gitbook_resource_paths_are_excluded_for_the_selected_host(self):
        self.assertEqual(
            _crawl_exclude_dirs("https://docs.example.com/start"),
            (
                "https://docs.example.com/~gitbook/image",
                "https://docs.example.com/spaces/",
                "https://docs.example.com/files/",
            ),
        )


if __name__ == "__main__":
    unittest.main()
