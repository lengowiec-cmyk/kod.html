from .preferences import Preferences
DEFAULT={'Standard':{'dpi':200,'color':'Kolor','ocr':False,'language':'pol','omit_blank':False,'rotation':0},'Archiwizacja':{'dpi':150,'color':'Szarość','ocr':True,'language':'pol','omit_blank':True,'rotation':0}}
class ScanProfiles:
    def __init__(self):self.prefs=Preferences()
    def all(self):return self.prefs.get('scan_profiles',DEFAULT)
    def save(self,name,profile):
        if not name.strip():raise ValueError('Podaj nazwę profilu.')
        if not 72<=int(profile['dpi'])<=600:raise ValueError('DPI poza zakresem.')
        items=self.all();items[name]=profile;self.prefs.put('scan_profiles',items)
    def remove(self,name):
        items=self.all()
        if len(items)<=1:raise ValueError('Pozostaw co najmniej jeden profil.')
        items.pop(name);self.prefs.put('scan_profiles',items)
