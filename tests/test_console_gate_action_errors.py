from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/"apps/console/app/gates/page.tsx"

class Tests(unittest.TestCase):
    def test_gate_actions_redirect_expected_errors_back_to_inbox(self):
        text=PAGE.read_text()
        self.assertIn('import {redirect} from "next/navigation";',text)
        self.assertIn('redirect("/gates?error="+encodeURIComponent(safeGateActionError(error)))',text)
        self.assertGreaterEqual(text.count('catch(error){redirectGateError(error);}'),3)
        self.assertIn('role="alert"',text)
        self.assertIn("O gate continua pendente",text)

    def test_error_message_is_bounded_and_redacts_common_secret_shapes(self):
        text=PAGE.read_text()
        self.assertIn('.replace(/Bearer\\s+\\S+/gi,"Bearer [redacted]")',text)
        self.assertIn('.slice(0,360)',text)
        self.assertIn("api[_-]?key",text)

if __name__=="__main__":
    unittest.main()
