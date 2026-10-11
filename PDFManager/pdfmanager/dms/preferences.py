import json
from pathlib import Path
from PySide6.QtCore import QSettings

class Preferences:
    def __init__(self,settings=None):self.settings=settings or QSettings('PDFManager','PDFManager')
    def get(self,key,default):
        try:return json.loads(self.settings.value('productivity/'+key,json.dumps(default),type=str))
        except (ValueError,TypeError):return default
    def put(self,key,value):self.settings.setValue('productivity/'+key,json.dumps(value,ensure_ascii=False));self.settings.sync()
    def recent(self,path):
        path=str(Path(path).resolve());self.put('recent',[path]+[p for p in self.get('recent',[]) if p!=path][:19])
    def favorite(self,entry):
        items=self.get('favorites',[])
        if entry not in items:items.append(entry)
        self.put('favorites',items)
    def view(self,path,state=None):
        key='views';items=self.get(key,{})
        path=str(Path(path).resolve())
        if state is None:return items.get(path,{})
        items.pop(path,None);items[path]=state
        self.put(key,dict(list(items.items())[-100:]))
