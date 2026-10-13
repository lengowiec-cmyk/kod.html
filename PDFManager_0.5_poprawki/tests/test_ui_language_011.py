"""Regression coverage for immediate language changes and preserved user data."""
import json
from string import Formatter
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QLabel,QLineEdit,QListWidget,QTableWidget,QTableWidgetItem,
    QToolButton,QWidget,QComboBox,QFontComboBox,QTabWidget,QVBoxLayout,QDialogButtonBox)
from pdfmanager.i18n.translator import translator,Translator,LOCALES_DIR
from pdfmanager.i18n.bindings import install_ui_translations,current_source,select_source

@pytest.fixture
def window(qapp):
    from pdfmanager.ui.main_window import MainWindow
    original=translator.language;translator.set_language('pl');w=MainWindow();w.show();qapp.processEvents()
    yield w
    w.close();w.deleteLater();qapp.processEvents();translator.set_language(original)

def test_catalog_keys_placeholders_and_menu_coverage():
    catalogs={l:json.loads((LOCALES_DIR/f'ui_{l}.json').read_text()) for l in ('pl','en','uk')}
    fields=lambda text:{name for _,name,_,_ in Formatter().parse(text) if name is not None}
    for lang,catalog in catalogs.items():
        assert set(catalog)==set(catalogs['pl'])
        for key,value in catalog.items():
            assert value
            assert fields(value)==fields(catalogs['pl'][key]),(lang,key)
    for key in ['Stemple i teksty','Zapisz ustawienia','Edytuj tekst PDF','Szafki','Schowek','Usuń hasło']:
        assert catalogs['en'][key]!=catalogs['pl'][key]

def test_all_workspace_tabs_and_word_buttons_change_immediately(window,qapp):
    expected={'pl':['Start','Skrzynka','Organizuj','Edytor PDF','Edytor obrazu','Szukaj','Wydatki','Automatyzacja'],
              'en':['Home','Inbox','Organize','PDF editor','Image editor','Search','Expenses','Automation'],
              'uk':['Головна','Вхідні','Упорядкування','Редактор PDF','Редактор зображень','Пошук','Витрати','Автоматизація']}
    original_actions={action:action.text() for action in window.findChildren(QAction)}
    window._shell.tabs.setCurrentIndex(3)
    for lang in ['en','uk','pl','en','pl']:
        window._select_language(lang);qapp.processEvents()
        assert [window._shell.tabs.tabText(i) for i in range(8)]==expected[lang]
        assert window._shell.tabs.currentIndex()==3
        assert window._word_format.buttons['apply_pdf'].text()==translator.text('Zastosuj do PDF')
        assert window._word_format.styles.itemText(2)==translator.text('Nagłówek 1')
        assert window._word_format.buttons['paste'].toolTip()==translator.text('Wklej')
        assert window._action_drive_save.text()==translator.text('Dodaj do kolejki Google Drive')
        assert window._drive_queue_status.text()==translator.text('Drive: oczekuje {waiting} • konflikty {conflicts}',waiting=0,conflicts=0)
        for button in window._shell.ribbon.findChildren(QToolButton):
            assert button.text()==button.defaultAction().iconText()
        if lang == "pl":
            assert {action:action.text() for action in original_actions}==original_actions
        for action in window.findChildren(QAction):
            assert not any(ch in action.text() for ch in 'ąćęłńóśźż') if lang=='en' else True

def test_settings_opened_after_switch_and_saved_canonical_values(window,qapp,monkeypatch):
    from pdfmanager.ui.settings_center import SettingsCenter
    translator.set_language('en');dialog=SettingsCenter(window);dialog.show();qapp.processEvents()
    assert dialog.windowTitle()=='PDFManager settings'
    assert dialog.navigation.item(0).text()=='General'
    buttons=dialog.findChild(QDialogButtonBox)
    assert buttons.button(QDialogButtonBox.Save).text()=='Save settings'
    assert dialog.fields['default_view'].itemText(0)=='Single page'
    select_source(dialog.fields['startup_tab'],'Edytor PDF');select_source(dialog.fields['default_view'],'two')
    dialog.navigation.setCurrentRow(4);dialog.fields['compact_ribbon'].setChecked(True)
    translator.set_language('uk');qapp.processEvents()
    assert dialog.navigation.currentRow()==4
    assert buttons.button(QDialogButtonBox.Save).text()=='Зберегти налаштування'
    assert current_source(dialog.fields['startup_tab'])=='Edytor PDF'
    assert dialog.fields['default_view'].currentText()=='Дві сторінки'
    writes={};monkeypatch.setattr(dialog.prefs,'put',lambda key,value:writes.update({key:value}))
    dialog.save()
    assert writes['startup_tab']=='Edytor PDF' and writes['default_view']=='two'
    assert writes['compact_ribbon'] is True
    dialog.deleteLater()

def test_document_tabs_draft_and_font_names_are_preserved(window,qapp):
    page=QWidget();window._tabs.addTab(page,'Zapisz')
    text='Zażółć gęślą jaźń — Київ — invoice 123';window._text_properties.editor.setPlainText(text)
    font=window._word_format.family.currentText();size=window._word_format.size.currentText()
    for lang in ['en','uk','pl']:
        translator.set_language(lang);qapp.processEvents()
        assert window._tabs.tabText(0)=='Zapisz'
        assert window._text_properties.editor.toPlainText()==text
        assert window._word_format.family.currentText()==font
        assert window._word_format.size.currentText()==size
    window._tabs.removeTab(0);page.deleteLater()

def test_user_profiles_snippets_and_filename_enums_are_not_translated(window,qapp):
    from pdfmanager.ui.transport_center import TransportCenter
    from pdfmanager.ui.scan_profiles import ScanProfilesDialog
    transport=TransportCenter(window);scan=ScanProfilesDialog(window)
    transport.profile.addItem('Zapisz');transport.profile.setCurrentText('Zapisz')
    transport.entry.addItem('Nowy');transport.entry.setCurrentText('Nowy')
    scan.names.addItem('Kolor');scan.names.setCurrentText('Kolor')
    transport.show();scan.show();qapp.processEvents();translator.set_language('en');qapp.processEvents()
    assert transport.profile.currentText()=='Zapisz' and transport.entry.currentText()=='Nowy'
    assert scan.names.currentText()=='Kolor'
    assert transport.naming.itemText(3)=='Faktura'
    assert transport.tabs.tabText(0)=='Stamps and text'
    select_source(scan.color,'Szarość');assert scan.color.currentText()=='Grayscale'
    assert scan.profile()['color']=='Szarość'
    scan.load('Standard');assert current_source(scan.color)==scan.store.all()['Standard']['color']
    transport.close();scan.close();transport.deleteLater();scan.deleteLater()

def test_generic_bindings_leave_model_contents_and_editable_values_alone(qapp):
    original=translator.language;translator.set_language('pl')
    root=QWidget();layout=QVBoxLayout(root)
    entry=QLineEdit('Nazwa');listing=QListWidget();listing.addItems(['Zapisz','Usuń'])
    table=QTableWidget(1,1);table.setHorizontalHeaderLabels(['Nazwa']);table.setItem(0,0,QTableWidgetItem('Zapisz'))
    combo=QComboBox();combo.addItem('Kolor',{'user':'data'})
    dynamic=QLabel('Dokumenty')
    for widget in [entry,listing,table,combo,dynamic]:layout.addWidget(widget)
    binder=install_ui_translations(root);root.show();qapp.processEvents()
    dynamic.setText('Dokument klienta 123')
    translator.set_language('en');qapp.processEvents()
    assert entry.text()=='Nazwa' and listing.item(0).text()=='Zapisz'
    assert table.item(0,0).text()=='Zapisz' and table.horizontalHeaderItem(0).text()=='Name'
    assert combo.currentText()=='Color' and combo.currentData()=={'user':'data'}
    assert current_source(combo)=='Kolor'
    assert dynamic.text()=='Dokument klienta 123'
    root.close();root.deleteLater();translator.set_language(original)
