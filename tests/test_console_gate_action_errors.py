from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/"apps/console/app/gates/page.tsx"
BANNER=ROOT/"apps/console/app/gates/gate-action-error-banner.tsx"

class Tests(unittest.TestCase):
    def test_gate_actions_redirect_expected_errors_back_to_inbox(self):
        text=PAGE.read_text()
        self.assertIn('import {redirect} from "next/navigation";',text)
        self.assertIn('redirect("/gates?error="+encodeURIComponent(safeGateActionError(error)))',text)
        self.assertGreaterEqual(text.count('catch(error){redirectGateError(error);}'),3)
        banner=BANNER.read_text()
        self.assertIn('role="alert"',banner)
        self.assertIn("O gate continua pendente",banner)

    def test_error_banner_removes_only_error_query_param_after_first_render(self):
        text=BANNER.read_text()
        self.assertIn('url.searchParams.delete("error")',text)
        self.assertIn('window.history.replaceState',text)
        self.assertIn('url.searchParams.toString()',text)
        self.assertIn('setVisible(false)',text)
        self.assertIn('aria-label="Fechar aviso"',text)

    def test_error_message_is_bounded_and_redacts_common_secret_shapes(self):
        text=PAGE.read_text()
        self.assertIn('.replace(/Bearer\\s+\\S+/gi,"Bearer [redacted]")',text)
        self.assertIn('.slice(0,360)',text)
        self.assertIn("api[_-]?key",text)

if __name__=="__main__":
    unittest.main()
