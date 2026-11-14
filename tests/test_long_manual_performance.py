import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/myway/skills/office-docs/scripts/long-manual/gen_toc.py"
SPEC = importlib.util.spec_from_file_location("manual_gen_toc", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TableOfContentsTests(unittest.TestCase):
    def test_pages_are_normalized_once_and_first_match_is_preserved(self):
        output = io.StringIO()
        inputs = {"titles.json": io.StringIO(json.dumps(["First title", "missing", "First title"]))}
        def open_file(name, mode="r", **kwargs):
            return mock.MagicMock(__enter__=lambda _: output if "w" in mode else inputs[name],
                                  __exit__=lambda *_: False)
        completed = mock.Mock(stdout="First  title\fFirst title\f")
        with mock.patch.object(MODULE.sys, "argv", ["gen_toc.py", "a.pdf", "titles.json", "out.json"]), \
             mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run, \
             mock.patch("builtins.open", side_effect=open_file), \
             mock.patch.object(MODULE, "norm", wraps=MODULE.norm) as normalise:
            MODULE.main()
        self.assertEqual([entry["page"] for entry in json.loads(output.getvalue())], [1, None, 1])
        self.assertEqual(normalise.call_count, 6)  # three pages plus three titles
        self.assertEqual(run.call_args.kwargs["timeout"], 120)


if __name__ == "__main__":
    unittest.main()
