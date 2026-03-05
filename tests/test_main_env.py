import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from confluence_mcp.main import load_dotenv


class DotenvLoaderTests(unittest.TestCase):
    def test_explicit_env_file_is_loaded(self):
        original = dict(os.environ)
        try:
            os.environ.pop("CONFLUENCE_BASE_URL", None)
            os.environ.pop("CONFLUENCE_AUTH_MODE", None)
            with tempfile.TemporaryDirectory() as td:
                env_path = Path(td) / "custom.env"
                env_path.write_text(
                    "\ufeffCONFLUENCE_BASE_URL=https://example.local\nCONFLUENCE_AUTH_MODE=pat\n",
                    encoding="utf-8",
                )
                loaded, _ = load_dotenv(str(env_path))
                self.assertEqual(str(loaded), str(env_path.resolve(strict=False)))
                self.assertEqual(os.getenv("CONFLUENCE_BASE_URL"), "https://example.local")
                self.assertEqual(os.getenv("CONFLUENCE_AUTH_MODE"), "pat")
        finally:
            os.environ.clear()
            os.environ.update(original)


if __name__ == "__main__":
    unittest.main()
