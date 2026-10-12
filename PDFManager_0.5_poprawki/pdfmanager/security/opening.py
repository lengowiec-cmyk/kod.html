from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox
# Default deny: only these document formats can be opened outside PDFManager.
ALLOWED={'.txt','.csv','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp','.docx','.xlsx','.pptx','.odt','.ods','.rtf'}

def open_document_file(parent,path):
    path=Path(path)
    if path.suffix.lower() not in ALLOWED:
        QMessageBox.warning(parent,'Bezpieczne otwieranie','Ten typ pliku jest zablokowany. Program nie uruchamia aplikacji, skryptów ani skrótów z listy dokumentów.');return False
    if QMessageBox.question(parent,'Otwórz w innym programie',f'Otworzyć „{path.name}” w domyślnej aplikacji systemu? Otwieraj wyłącznie pliki ze sprawdzonego źródła.')!=QMessageBox.Yes:return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
