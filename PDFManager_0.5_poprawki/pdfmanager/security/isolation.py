"""JSON-only allowlisted PDF workers: timeout, resource limits, no pickle/eval."""
from pathlib import Path
import base64,dataclasses,functools,importlib,json,os,subprocess,sys,tempfile,time
WORKER_MODE=False
ALLOWED_MODULES={'annotations','page_ops','content','extended_ops','workflows','utilities','transport_ops'}
TYPES={'TextSpan':'text_edit','EditResult':'text_edit','AnnotationInfo':'annotations','FormField':'workflows'}
class ProcessingError(RuntimeError):pass

def encode(value):
    if isinstance(value,Path):return {'$path':str(value.resolve())}
    if isinstance(value,bytes) and len(value)>32*1024*1024:raise ProcessingError('Porcja danych przekracza limit 32 MB.')
    if isinstance(value,bytes):return {'$bytes':base64.b64encode(value).decode()}
    if dataclasses.is_dataclass(value):return {'$type':type(value).__name__,'fields':encode(dataclasses.asdict(value))}
    if isinstance(value,tuple):return {'$tuple':[encode(v) for v in value]}
    if isinstance(value,list):return [encode(v) for v in value]
    if isinstance(value,dict):return {'$dict':[[str(k),encode(v)] for k,v in value.items()]}
    return value

def decode(value):
    if isinstance(value,list):return [decode(v) for v in value]
    if isinstance(value,dict):
        if '$dict' in value:return {k:decode(v) for k,v in value['$dict']}
        if '$path' in value:return Path(value['$path'])
        if '$bytes' in value:return base64.b64decode(value['$bytes'],validate=True)
        if '$tuple' in value:return tuple(decode(v) for v in value['$tuple'])
        if '$type' in value:
            name=value['$type']
            if name not in TYPES:raise ProcessingError('Nieznany typ danych procesu PDF.')
            cls=getattr(importlib.import_module('pdfmanager.pdf_engine.'+TYPES[name]),name)
            return cls(**decode(value['fields']))
        return {k:decode(v) for k,v in value.items()}
    return value

def call(operation,*args,**kwargs):
    from pdfmanager.dms.jobs import checkpoint
    from .antivirus import scan_arguments
    scan_arguments(args)
    with tempfile.TemporaryDirectory(prefix='pdfmanager-worker-') as folder:
        folder=Path(folder);request=folder/'request.json';response=folder/'response.json'
        request.write_text(json.dumps({'op':operation,'args':encode(args),'kwargs':encode(kwargs)},ensure_ascii=False),encoding='utf-8')
        os.chmod(request,0o600)
        command=[sys.executable,'--pdf-worker',str(request)] if getattr(sys,'frozen',False) else [sys.executable,'-m','pdfmanager.security.worker',str(request)]
        env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONPATH=str(Path(__file__).resolve().parents[2]))
        proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=env,start_new_session=True,cwd=str(Path(__file__).resolve().parents[2]))
        deadline=time.monotonic()+300
        try:
            while True:
                checkpoint()
                try:_,stderr=proc.communicate(timeout=.15);break
                except subprocess.TimeoutExpired:
                    if time.monotonic()>deadline:raise ProcessingError('Przekroczono czas obsługi dokumentu.')
            if proc.returncode or not response.is_file():raise ProcessingError('Proces dokumentu został zatrzymany lub plik jest uszkodzony.')
            if response.stat().st_size>64*1024*1024:raise ProcessingError('Wynik dokumentu przekracza limit danych.')
            result=json.loads(response.read_text(encoding='utf-8'))
            if not result['ok']:
                kind=result.get('type');message=result.get('error','Błąd PDF')[:2000]
                if kind in ('ValueError','DocumentLimitError'):raise ValueError(message)
                if kind=='FileExistsError':raise FileExistsError(message)
                if kind in ('PageOpError','TextEditError','WorkflowError'):
                    module={'PageOpError':'page_ops','TextEditError':'text_edit','WorkflowError':'workflows'}[kind]
                    raise getattr(importlib.import_module('pdfmanager.pdf_engine.'+module),kind)(message)
                raise ProcessingError(message)
            value=decode(result['value'])
            if operation.endswith('form_fields') and len(value)>1000:raise ProcessingError('Dokument zawiera ponad 1000 pól formularza.')
            if operation=='document.links' and len(value)>2000:raise ProcessingError('Zbyt wiele linków na stronie.')
            return value
        finally:
            if proc.poll() is None:
                if os.name!='nt':
                    import signal
                    os.killpg(proc.pid,signal.SIGKILL)
                else:proc.kill()
                proc.communicate()

def enable_module_isolation(module,namespace,names):
    if WORKER_MODE:return
    for name in names:
        function=namespace[name]
        def wrap(fn,name):
            @functools.wraps(fn)
            def remote(*args,**kwargs):return call(module.rsplit('.',1)[-1]+'.'+name,*args,**kwargs)
            return remote
        namespace[name]=wrap(function,name)

def engine_method(function):
    @functools.wraps(function)
    def remote(self,*args,**kwargs):
        if WORKER_MODE:return function(self,*args,**kwargs)
        return call('text_edit.'+function.__name__,*args,**kwargs)
    return remote
