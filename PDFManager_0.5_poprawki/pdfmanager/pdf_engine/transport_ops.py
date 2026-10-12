"""Transport PDF operations executed exclusively in bounded PDF workers."""
from pathlib import Path
import math
import pymupdf
from pdfmanager.security.limits import safe_open, pixmap
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

def _color(value):
    if len(value)!=7 or not value.startswith('#'):raise ValueError('Podaj kolor #RRGGBB.')
    return tuple(int(value[i:i+2],16)/255 for i in (1,3,5))

def _font(name='sans'):
    return pymupdf.Font(fontfile=str(Path(__file__).resolve().parents[1]/'resources/fonts/DejaVuSans.ttf'))

def _box(page, text, options):
    values=[float(options.get(k,v)) for k,v in [('x',24),('y',24),('width',235),('height',75),('size',12)]]
    if not all(math.isfinite(v) for v in values) or min(values[2:])<=0 or not 5<=values[4]<=72:raise ValueError('Nieprawidłowe wymiary lub rozmiar czcionki.')
    x,y,w,h,size=values;rect=pymupdf.Rect(x,y,x+w,y+h)
    if not page.rect.contains(rect):raise ValueError('Pole wychodzi poza stronę. Zmień pozycję lub rozmiar.')
    color=_color(options.get('color','#176c79'))
    font=pymupdf.Font(fontfile=options['fontfile']) if options.get('fontfile') else _font(options.get('font','sans'))
    # TextWriter embeds Unicode font; Polish letters remain searchable.
    writer=pymupdf.TextWriter(page.rect)
    if writer.fill_textbox(rect+ (5,5,-5,-5),text,font=font,fontsize=size):raise ValueError('Tekst nie mieści się w polu. Powiększ pole lub zmniejsz czcionkę.')
    if options.get('border',False):page.draw_rect(rect,color=color,width=1.5)
    writer.write_text(page,color=color)

def mark(source, output, text, options, pages=None):
    if not text.strip() or len(text)>5000:raise ValueError('Podaj tekst do 5000 znaków.')
    with safe_open(source) as doc:
        indices=list(range(len(doc))) if pages is None else pages
        if not indices:raise ValueError('Wybierz strony.')
        for i in indices:
            if not 0<=i<len(doc):raise ValueError('Nieprawidłowy numer strony.')
            _box(doc[i],text,options)
        data=doc.tobytes(garbage=4,deflate=True)
    atomic_write_bytes(output,data)

def package(paths, output, title, number=True):
    if not paths:raise ValueError('Wybierz dokumenty w kolejności pakietu.')
    with pymupdf.open() as result:
        cover=result.new_page(width=595,height=842)
        _box(cover,title,{'x':40,'y':50,'width':515,'height':100,'size':22,'color':'#176c79'})
        lines='\n'.join(f'{i+1}. {Path(p).name}' for i,p in enumerate(paths))
        # Cover has finite capacity rather than silently dropping names.
        _box(cover,lines,{'x':40,'y':170,'width':515,'height':610,'size':11,'color':'#334155'})
        toc=[]
        for path in paths:
            with safe_open(path) as source:
                if len(result)+len(source)>5000:raise ValueError('Pakiet przekracza limit 5000 stron.')
                toc.append([1,Path(path).name,len(result)+1]);result.insert_pdf(source,widgets=True)
        result.set_toc(toc)
        if number:
            for i,page in enumerate(result):
                _box(page,f'{i+1} / {len(result)}',{'x':20,'y':page.rect.height-28,'width':100,'height':24,'size':9,'color':'#334155'})
        atomic_write_bytes(output,result.tobytes(garbage=4,deflate=True))

def batch_transform(source,output,rotation=0,compress=False,number=False):
    with safe_open(source) as doc:
        if rotation not in (0,90,180,270):raise ValueError('Nieprawidłowy obrót.')
        for i,page in enumerate(doc):
            if rotation:page.set_rotation((page.rotation+rotation)%360)
            if number:_box(page,f'{i+1} / {len(doc)}',{'x':20,'y':page.rect.height-28,'width':100,'height':24,'size':9,'color':'#334155'})
        data=doc.tobytes(garbage=4 if compress else 3,deflate=True)
    atomic_write_bytes(output,data)

def comparison_pdf(left,right,output):
    import numpy as np
    from PIL import Image
    import io
    with safe_open(left) as a,safe_open(right) as b,pymupdf.open() as report:
        summary=[]
        for i in range(max(len(a),len(b))):
            from pdfmanager.dms.jobs import checkpoint
            checkpoint(i,max(len(a),len(b)),'Porównanie wersji')
            images=[]
            for doc in (a,b):
                if i<len(doc):images.append(Image.open(io.BytesIO(pixmap(doc[i],dpi=72,alpha=False,colorspace=pymupdf.csRGB).tobytes('png'))).convert('RGB'))
                else:images.append(Image.new('RGB',(595,842),'#eeeeee'))
            width=max(im.width for im in images);height=max(im.height for im in images)
            if width*height>20_000_000:raise ValueError('Porównanie przekracza limit obrazu.')
            canvases=[]
            for im in images:
                c=Image.new('RGB',(width,height),'white');c.paste(im,(0,0));canvases.append(c)
            aa,bb=[np.asarray(im).astype('int16') for im in canvases];mask=np.any(abs(aa-bb)>12,axis=2)
            overlay=np.asarray(canvases[1]).copy();overlay[mask]=(255,95,95)
            page=report.new_page(width=900,height=600)
            for index,im in enumerate([canvases[0],canvases[1],Image.fromarray(overlay)]):
                buf=io.BytesIO();im.save(buf,format='PNG');page.insert_image(pymupdf.Rect(index*300+8,35,(index+1)*300-8,570),stream=buf.getvalue())
            _box(page,f'Strona {i+1}: oryginał | nowa wersja | różnice ({mask.mean()*100:.2f}%)',{'x':10,'y':5,'width':880,'height':28,'size':11,'color':'#334155'})
            summary.append({'page':i+1,'difference':round(float(mask.mean()*100),3)})
        atomic_write_bytes(output,report.tobytes(garbage=4,deflate=True));return summary

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['mark','package','batch_transform','comparison_pdf']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
