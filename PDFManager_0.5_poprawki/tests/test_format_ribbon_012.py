"""Style gallery and colored vector controls still edit the actual PDF draft."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QTextCursor,QIcon
from pdfmanager.i18n.translator import translator
from pdfmanager.ui.word_format import payload

def test_style_tile_clicks_apply_format_after_language_switch(qapp):
    from pdfmanager.ui.main_window import MainWindow
    original=translator.language;window=MainWindow();window.show();bar=window._word_format;editor=window._text_properties.editor
    editor.setPlainText('Zażółć gęślą jaźń');cursor=editor.textCursor();cursor.select(QTextCursor.Document);editor.setTextCursor(cursor)
    translator.set_language('uk');qapp.processEvents();bar.style_tiles[4].click()
    run=payload(editor)[0]['runs'][0]
    assert run['size']==28 and run['bold']
    assert bar.styles.currentIndex()==4 and bar.style_tiles[4].isChecked()
    assert bar.style_tiles[4].text()=='Назва документа'
    bar.style_tiles[5].click();run=payload(editor)[0]['runs'][0]
    assert run['size']==14 and run['italic'] and not run['bold']
    assert sum(tile.isChecked() for tile in bar.style_tiles)==1
    translator.set_language('en');qapp.processEvents()
    assert bar.buttons['bold'].toolTip()=='Bold' and bar.buttons['bold'].accessibleName()=='Bold'
    assert editor.toPlainText()=='Zażółć gęślą jaźń'
    window.close();translator.set_language(original)

def test_vector_controls_render_at_high_dpi(qapp):
    from pdfmanager.ui.office_icons import office_icon
    for name in ['paste','copy','cut','painter','color','highlight','left','apply_pdf']:
        icon=office_icon(name)
        pix=icon.pixmap(QSize(32,32),2.0,QIcon.Normal,QIcon.Off)
        assert not pix.isNull() and pix.width()==64 and pix.devicePixelRatio()==2
        image=pix.toImage()
        assert any(image.pixelColor(x,y).alpha()>0 for x in range(64) for y in range(64))
        assert pix.toImage()!=icon.pixmap(QSize(32,32),2.0,QIcon.Disabled,QIcon.Off).toImage()
