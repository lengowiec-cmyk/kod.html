import importlib,json,sys
from pathlib import Path
from . import isolation

def limits():
    # These limits isolate crashes/resources; they are not an AppContainer.
    if sys.platform!='win32':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(240,240))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    else:
        import ctypes
        from ctypes import wintypes
        class BASIC(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):_fields_=[(n,ctypes.c_ulonglong) for n in ('ro','wo','oo','rt','wt','ot')]
        class EXT(ctypes.Structure):_fields_=[('basic',BASIC),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateJobObjectW.restype=wintypes.HANDLE;kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        job=kernel.CreateJobObjectW(None,None);data=EXT();data.basic.flags=0x100|0x2000|0x2;data.basic.process_time=240*10_000_000;data.process_memory=2*1024**3
        if not job or not kernel.SetInformationJobObject(job,9,ctypes.byref(data),ctypes.sizeof(data)) or not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):raise RuntimeError('Nie można ustanowić limitów procesu PDF w Windows.')
        globals()['_job_handle']=job

def execute(operation,args,kwargs):
    import pymupdf
    from .limits import safe_open,pixmap,MAX_ATTACHMENT_BYTES
    if operation.startswith('document.'):
        action=operation.split('.',1)[1];path=args[0]
        if action not in {'info','texts','render','search','text_region','links','thumbnail_batch'}:raise ValueError('Nieznana operacja dokumentu.')
        with safe_open(path) as doc:
            if action=='info':return {'pages':len(doc),'protected':doc.needs_pass,'sizes':[tuple(p.rect) for p in doc] if not doc.needs_pass else [],'rotations':[tuple(p.rotation_matrix) for p in doc] if not doc.needs_pass else []}
            if doc.needs_pass:raise ValueError('PDF wymaga hasła.')
            if action=='texts':
                texts=[p.get_text(sort=True) for p in doc]
                if sum(len(t) for t in texts)>16*1024*1024:raise ValueError('Tekst PDF przekracza limit indeksowania.')
                return texts
            if action=='thumbnail_batch':
                start=args[1];zoom=args[2];result=[]
                for index in range(start,min(start+8,len(doc))):
                    page=doc[index];scale=min(zoom,140/page.rect.width,190/page.rect.height)
                    result.append((index,pixmap(page,matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csRGB,alpha=False).tobytes('png')))
                return result
            page=doc[args[1]]
            if action=='render':return pixmap(page,matrix=pymupdf.Matrix(args[2],args[2]),colorspace=pymupdf.csRGB,alpha=False).tobytes('png')
            if action=='search':return [tuple(r*page.rotation_matrix) for r in page.search_for(args[2])]
            if action=='text_region':return page.get_text('text',clip=pymupdf.Rect(args[2]),sort=True)
            if action=='links':
                result=[]
                for link in page.get_links():
                    item={k:v for k,v in link.items() if k in ('kind','uri','page')};item['from']=tuple(link['from']*page.derotation_matrix);result.append(item)
                return result
        raise ValueError('Nieznana operacja dokumentu.')
    module,name=operation.split('.',1)
    if module=='text_edit' and name in ('extract_spans','apply_edit'):
        engine=importlib.import_module('pdfmanager.pdf_engine.text_edit').get_default_text_edit_engine()
        return getattr(engine,name)(*args,**kwargs)
    if module not in isolation.ALLOWED_MODULES:raise ValueError('Operacja spoza listy dozwolonych.')
    mod=importlib.import_module('pdfmanager.pdf_engine.'+module)
    if name not in mod.ISOLATED_FUNCTIONS:raise ValueError('Operacja spoza listy dozwolonych.')
    # Restore integer-keyed form dictionaries after JSON transport.
    if name=='fill_form' and len(args)>2:args=(*args[:2],{int(k):v for k,v in args[2].items()},*args[3:])
    return getattr(mod,name)(*args,**kwargs)

def main(request_path):
    isolation.WORKER_MODE=True
    request=Path(request_path);response=request.with_name('response.json')
    try:
        if request.stat().st_size>64*1024*1024:raise ValueError('Zbyt duże zlecenie PDF.')
        limits();item=json.loads(request.read_text(encoding='utf-8'))
        value=execute(item['op'],isolation.decode(item['args']),isolation.decode(item['kwargs']))
        result={'ok':True,'value':isolation.encode(value)}
    except Exception as exc:result={'ok':False,'type':type(exc).__name__,'error':str(exc)[:2000]}
    response.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');return 0
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
