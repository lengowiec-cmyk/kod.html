from pathlib import Path
from .preferences import Preferences
from .scan_pipeline import process_scans,document_name
from .files import transfer_file

class Rules:
    def __init__(self):self.prefs=Preferences()
    def all(self):return self.prefs.get('routing_rules',[])
    def save(self,rule,index=None):
        if not rule['name'].strip() or not rule['match'].strip():raise ValueError('Podaj nazwę i warunek reguły.')
        if not Path(rule['target']).is_dir():raise ValueError('Wybierz dostępny folder docelowy.')
        rule=dict(rule,target=str(Path(rule['target']).resolve()))
        items=self.all()
        if index is None:items.append(rule)
        else:items[index]=rule
        self.prefs.put('routing_rules',items)
    def remove(self,index):items=self.all();items.pop(index);self.prefs.put('routing_rules',items)

def route_documents(paths,rules,*,ocr=False,language='pol',pattern='{date}_{source}_{counter}'):
    from pdfmanager.security.isolation import call
    from pdfmanager.pdf_engine.utilities import barcode_pdf
    from pdfmanager.pdf_engine.workflows import merge_inputs,ocr_document
    import tempfile
    results=[]
    for number,value in enumerate(paths):
        source=Path(value)
        from .jobs import checkpoint,Cancelled
        checkpoint(number,len(paths),'Reguły: '+source.name)
        try:
            with tempfile.TemporaryDirectory(prefix='pdfmanager-rule-') as temporary:
                draft=Path(temporary)/'draft.pdf';merge_inputs([source],draft)
                if ocr:
                    recognized=Path(temporary)/'recognized.pdf';ocr_document(draft,recognized,language);draft=recognized
                text='\n'.join(call('document.texts',draft));codes=None;matched=None
                for rule in rules:
                    if not rule.get('enabled',True):continue
                    if rule['kind']=='Nazwa':candidate=source.name
                    elif rule['kind']=='Tekst PDF':candidate=text
                    else:
                        if codes is None:codes='\n'.join(item['text'] for item in barcode_pdf(draft))
                        candidate=codes
                    if rule['match'].casefold() in candidate.casefold():matched=rule;break
                if not matched:results.append((source,'Brak dopasowania',''));continue
                target=Path(matched['target']);name=document_name(pattern,source,number+1);output=target/name
                if output.exists():
                    import uuid
                    output=target/(output.stem+'_'+uuid.uuid4().hex[:8]+'.pdf')
                transfer_file(draft,output);results.append((source,matched['name'],str(output)))
        except Cancelled:raise
        except Exception as exc:results.append((source,'Błąd',str(exc)))
    return results
