from pathlib import Path, PureWindowsPath
import json
from PySide6.QtCore import QSettings

DEFAULT_TEMPLATES={'Zlecenie transportowe':['01 Zlecenie','02 CMR','03 POD','04 Faktury','05 Korespondencja'],'Klient':['01 Dokumenty','02 Umowy','03 Faktury','04 Korespondencja'],
                   'Projekt':['01 Administracja','02 Dokumentacja','03 Rozliczenia']}

def validate_relative(value):
    value=value.replace('\\','/')
    parts=value.split('/')
    if not value or PureWindowsPath(value).is_absolute() or PureWindowsPath(value).drive:
        raise ValueError('Wymagana jest względna nazwa folderu.')
    for part in parts:
        if part in ('','.','..') or part.rstrip(' .')!=part or any(c in part for c in '<>:"|?*') or any(ord(c)<32 for c in part):
            raise ValueError('Nieprawidłowa nazwa folderu Windows.')
        if part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
            raise ValueError('Nazwa zarezerwowana przez Windows.')
    return Path(*parts)

class CabinetStore:
    def __init__(self, settings=None):self.settings=settings or QSettings('PDFManager','PDFManager')
    def read(self):
        return json.loads(self.settings.value('dms/cabinets','[]',type=str))
    def templates(self):return json.loads(self.settings.value('dms/templates',json.dumps(DEFAULT_TEMPLATES),type=str))
    def save_template(self,name,folders):
        if not name.strip():raise ValueError('Podaj nazwę szablonu.')
        for folder in folders:validate_relative(folder)
        templates=self.templates();templates[name.strip()]=folders
        self.settings.setValue('dms/templates',json.dumps(templates,ensure_ascii=False));self.settings.sync()
    def add(self,name,root):
        root=Path(root).resolve()
        if not name.strip() or not root.is_dir():raise ValueError('Podaj nazwę i istniejący katalog szafki.')
        entries=self.read()
        if any(Path(e['root'])==root or e['name'].casefold()==name.strip().casefold() for e in entries):raise ValueError('Szafka o tej nazwie lub lokalizacji już istnieje.')
        entries.append({'name':name.strip(),'root':str(root)})
        self.settings.setValue('dms/cabinets',json.dumps(entries,ensure_ascii=False));self.settings.sync()
    def create_client(self,root,name,template):
        root=Path(root).resolve();relative=validate_relative(name)
        if len(relative.parts)!=1:raise ValueError('Nazwa klienta musi być pojedynczą nazwą folderu.')
        if not root.is_dir():raise ValueError('Katalog szafki jest niedostępny.')
        folders=[validate_relative(f) for f in self.templates()[template]]
        client=root/relative;client.mkdir() # Do not modify an existing client.
        try:
            for folder in folders:(client/folder).mkdir(parents=True,exist_ok=True)
        except Exception:
            import shutil
            shutil.rmtree(client)
            raise
        return client
