import tempfile
import unittest
from pathlib import Path

from sentiment_index.config import DEFAULT_CONFIG
from sentiment_index.settings import (
    add_term,
    load_runtime_config,
    load_runtime_lexicon,
    load_settings,
    remove_term,
    save_settings,
)


class SettingsTest(unittest.TestCase):
    def test_add_and_remove_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings(load_settings(), path=path)

            add_term("keywords", "카카오", path=path)
            self.assertIn("카카오", load_settings(path)["keywords"])

            remove_term("keywords", "카카오", path=path)
            self.assertNotIn("카카오", load_settings(path)["keywords"])

    def test_runtime_config_and_lexicon_use_saved_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = load_settings()
            settings["keywords"] = ["비트코인", "카카오"]
            settings["lexicon"]["fomo"] = ["몰빵", "추격매수", "뒤늦게탑승"]
            save_settings(settings, path=path)

            config = load_runtime_config(DEFAULT_CONFIG, path=path)
            lexicon = load_runtime_lexicon(path=path)

            self.assertEqual(config.keywords, ("비트코인", "카카오"))
            self.assertIn("뒤늦게탑승", lexicon.fomo)


if __name__ == "__main__":
    unittest.main()
