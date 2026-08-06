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

    def test_image_argument_does_not_consume_prompt(self):
        command, _ = routine.codex_command(
            "Проверить баннер",
            routine.ROOT / "vision.schema.json",
            routine.ROOT / "vision.json",
            "low",
            image=routine.ROOT / "banner.jpg",
        )
        self.assertIn(f"--image={routine.ROOT / 'banner.jpg'}", command)
        self.assertEqual(command[-1], "Проверить баннер")


if __name__ == "__main__":
    unittest.main()
