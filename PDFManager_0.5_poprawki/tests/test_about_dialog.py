from unittest.mock import patch

from pdfmanager.ui.main_window import ABOUT_DEDICATION, MainWindow


def test_about_dialog_contains_bold_dedication(qapp, tmp_path):
    win = MainWindow()
    captured = {}

    with patch("pdfmanager.ui.main_window.QMessageBox") as mock_box_cls:
        instance = mock_box_cls.return_value
        instance.setText.side_effect = lambda text: captured.setdefault("text", text)
        win._show_about()

    assert f"<b>{ABOUT_DEDICATION}</b>" in captured["text"]
    instance.exec.assert_called_once()
