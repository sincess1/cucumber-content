import subprocess
import sys
import unittest

import routine


class ProcessTests(unittest.TestCase):
    def test_run_checked_closes_stdin(self):
        output = routine.run_checked([
            sys.executable,
            "-c",
            "import sys; print('closed' if sys.stdin.read() == '' else 'open')",
        ])
        self.assertEqual(output.strip(), "closed")


if __name__ == "__main__":
    unittest.main()
