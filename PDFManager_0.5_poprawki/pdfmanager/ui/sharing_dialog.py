from pathlib import Path
import zipfile
from PySide6.QtWidgets import QFileDialog,QMessageBox
from pdfmanager.security.opening import ALLOWED
from pdfmanager.security.limits import check_file

def prepare_package(window):
    files,_=QFileDialog.getOpenFileNames(window,'Dokumenty do udostępnienia')
    if not files:return
    output,_=QFileDialog.getSaveFileName(window,'Paczka do udostępnienia','','ZIP (*.zip)')
    if not output:return
    output=str(Path(output).with_suffix('.zip'))
    if Path(output).exists() and QMessageBox.question(window,'Paczka','Nadpisać istniejącą paczkę?')!=QMessageBox.Yes:return
    try:
        names=set()
        for value in files:
            path=Path(value);check_file(path)
            if path.suffix.lower() not in ALLOWED|{'.pdf'}:raise ValueError('Niebezpieczny typ pliku w paczce.')
            if path.name.casefold() in names:raise ValueError('Pliki mają powtarzające się nazwy. Zmień nazwy przed pakowaniem.')
            names.add(path.name.casefold())
        import tempfile,os
        fd,temp=tempfile.mkstemp(suffix='.zip',dir=Path(output).parent);os.close(fd)
        try:
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                for value in files:archive.write(value,Path(value).name)
            Path(temp).replace(output)
        finally:Path(temp).unlink(missing_ok=True)
        QMessageBox.information(window,'Paczka gotowa',f'Zapisano: {output}\nMożesz przekazać plik przez wybraną usługę lub pocztę. Paczka nie jest automatycznie wysyłana.')
    except Exception as exc:QMessageBox.warning(window,'Udostępnianie',str(exc))
