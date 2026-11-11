from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConsoleDynamicRenderingTests(unittest.TestCase):
    def test_root_layout_forces_authenticated_console_to_render_per_request(self) -> None:
        source = (ROOT / "apps" / "console" / "app" / "layout.tsx").read_text(encoding="utf-8")

        self.assertIn('export const dynamic="force-dynamic";', source)
        self.assertIn("authenticated Control Plane", source)


if __name__ == "__main__":
    unittest.main()
