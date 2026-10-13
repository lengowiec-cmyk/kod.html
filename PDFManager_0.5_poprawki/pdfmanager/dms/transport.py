"""Transport workflows: original templates, safe names and explicit checklists."""
from pathlib import Path
from datetime import date, datetime
import json, re
from pdfmanager.dms.cabinets import validate_relative
from pdfmanager.dms.preferences import Preferences

STAMPS = ['ZATWIERDZONO', 'DO POPRAWY', 'OPŁACONO', 'BRAK PODPISU', 'DOKUMENT KOMPLETNY', 'POD PODPIS', 'OTRZYMANO', 'KOPIA', 'POD POTWIERDZONY']
SNIPPETS = {'Potwierdzenie odbioru':'Prosimy o potwierdzenie odbioru dokumentów.', 'Brak podpisu':'Prosimy o uzupełnienie podpisu i daty odbioru.', 'Dokumenty rozliczeniowe':'Prosimy o przesłanie podpisanego CMR oraz potwierdzenia dostawy POD.', 'Instrukcja dla kierowcy':'Po rozładunku prosimy o przesłanie czytelnego skanu wszystkich stron CMR.'}
PROFILES = {name:{'x':24,'y':24,'width':235,'height':75,'size':12,'color':'#176c79'} for name in ('CMR','POD','Zlecenie transportowe','Faktura')}
FOLDERS=['01 Zlecenie','02 CMR','03 POD','04 Faktury','05 Korespondencja']

def component(text):
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',str(text)).strip(' .')[:80]
    if not value:raise ValueError('Uzupełnij dane do nazwy pliku.')
    validate_relative(value)
    return value

def filename(order, kind, contractor, when=None):
    when=when or date.today().isoformat();date.fromisoformat(when)
    return f'{when}_{component(order)}_{component(kind)}_{component(contractor)}.pdf'

def render_tokens(text, order='', contractor='', employee='', **details):
    values={'data':date.today().isoformat(),'godzina':datetime.now().strftime('%H:%M'),'pracownik':employee,'zlecenie':order,'kontrahent':contractor}
    allowed={'awb','hawb','mawb','trasa','przewoznik','sztuki','masa','uwagi'}
    if set(details)-allowed:raise ValueError('Nieobsługiwane pole wstawki.')
    values.update({key:details.get(key,'') for key in allowed})
    for key,value in values.items():text=text.replace('{'+key+'}',str(value))
    return text

class Library:
    def __init__(self):self.preferences=Preferences()
    def read(self):
        value=self.preferences.get('transport_library',{'stamps':STAMPS,'snippets':SNIPPETS,'profiles':PROFILES})
        for name in ('AWB','HAWB','MAWB','Packing list','Customs'):
            value.setdefault('profiles',{}).setdefault(name,{'x':24,'y':24,'width':300,'height':150,'size':12,'color':'#176c79'})
        return value
    def favorites(self):
        value=self.preferences.get('template_favorites',None)
        if value is None:return []
        from pdfmanager.security.cache import CacheCipher
        from .recovery import data_dir
        return json.loads(CacheCipher(data_dir()/'workflow').decrypt(value))
    def add_favorite(self,value):
        rows=self.favorites();rows.insert(0,value);rows=rows[:50];raw=json.dumps(rows,ensure_ascii=False)
        if len(raw.encode())>500000:raise ValueError('Ulubione wzory są zbyt duże.')
        from pdfmanager.security.cache import CacheCipher
        from .recovery import data_dir
        self.preferences.put('template_favorites',CacheCipher(data_dir()/'workflow').encrypt(raw))
    def save(self,value):
        if len(json.dumps(value))>100000:raise ValueError('Biblioteka jest zbyt duża.')
        self.preferences.put('transport_library',value)

def create_order(root, order, contractor, profile='road'):
    from .transport_templates import ORDER_PROFILES
    if profile not in ORDER_PROFILES:raise ValueError('Nieprawidłowy profil zlecenia.')
    if not order.strip() or not contractor.strip():raise ValueError('Uzupełnij numer zlecenia i kontrahenta.')
    parent=Path(root).resolve()
    if not parent.is_dir():raise ValueError('Wybierz istniejący katalog zleceń.')
    target=parent/component(order+'_'+contractor);target.mkdir()
    try:
        for name in (FOLDERS if profile=='road' else ORDER_PROFILES[profile]['folders']):(target/name).mkdir()
        save_checklist(target,{'order':order,'contractor':contractor,'profile':profile,'checks':{},'documents':{}})
    except Exception:
        import shutil
        shutil.rmtree(target);raise
    return target

def read_checklist(folder):
    path=Path(folder)/'zlecenie.pdfmanager.json'
    if path.stat().st_size>100000:raise ValueError('Nieprawidłowy plik zlecenia.')
    return json.loads(path.read_text(encoding='utf-8'))

def save_checklist(folder,value):
    from pdfmanager.pdf_engine.io_utils import atomic_write_bytes
    atomic_write_bytes(Path(folder)/'zlecenie.pdfmanager.json',json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8'))

def missing_documents(folder):
    data=read_checklist(folder)
    from .transport_templates import ORDER_PROFILES
    required=ORDER_PROFILES.get(data.get('profile','road'),ORDER_PROFILES['road'])['required']
    return [name for name in required if not data.get('checks',{}).get(name)]
