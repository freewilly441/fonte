import unittest

from app import KnowledgeApp


class FakeTclObj:
    def __str__(self) -> str:
        return "#ffffff"


class BrokenStr:
    def __str__(self) -> str:
        raise RuntimeError("boom")


class FakeStyle:
    def __init__(self, background, foreground):
        self._background = background
        self._foreground = foreground

    def lookup(self, style_name: str, option: str):
        if style_name == "TFrame" and option == "background":
            return self._background
        if style_name == "TLabel" and option == "foreground":
            return self._foreground
        return None


class FakeWidget:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)


class TextSurfaceStyleTests(unittest.TestCase):
    def test_tcl_to_str_handles_none_and_str_errors(self):
        app = KnowledgeApp.__new__(KnowledgeApp)

        self.assertEqual(app._tcl_to_str(None), "")
        self.assertEqual(app._tcl_to_str(FakeTclObj()), "#ffffff")
        self.assertEqual(app._tcl_to_str(BrokenStr()), "")

    def test_apply_text_surface_style_handles_tcl_obj_background(self):
        app = KnowledgeApp.__new__(KnowledgeApp)
        app._style = FakeStyle(background=FakeTclObj(), foreground="#111111")
        widget = FakeWidget()

        KnowledgeApp._apply_text_surface_style(app, widget)

        self.assertEqual(widget.config["selectbackground"], "#BFD7FF")

    def test_apply_text_surface_style_empty_background_uses_dark_branch(self):
        app = KnowledgeApp.__new__(KnowledgeApp)
        app._style = FakeStyle(background="", foreground="#111111")
        widget = FakeWidget()

        KnowledgeApp._apply_text_surface_style(app, widget)

        self.assertEqual(widget.config["selectbackground"], "#3B557A")


if __name__ == "__main__":
    unittest.main()
