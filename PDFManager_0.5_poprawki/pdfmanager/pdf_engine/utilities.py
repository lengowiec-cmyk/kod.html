from pathlib import Path
import io
from PIL import Image,ImageStat,ImageOps
import pymupdf
from pdfmanager.security.limits import safe_open,pixmap
from .io_utils import atomic_write_bytes

def barcode_pdf(source):
    import zxingcpp
    results=[]
    with safe_open(source) as doc:
        for page in doc:
            from pdfmanager.dms.jobs import checkpoint
            checkpoint(page.number,len(doc),'Rozpoznawanie kodów')
            image=Image.open(io.BytesIO(pixmap(page,dpi=150,alpha=False,colorspace=pymupdf.csRGB).tobytes('png')))
            for item in zxingcpp.read_barcodes(image):results.append({'page':page.number,'format':str(item.format),'text':item.text})
    return results

def prepare_scan(source,output,profile):
    with safe_open(source) as doc,pymupdf.open() as result:
        for page in doc:
            from pdfmanager.dms.jobs import checkpoint
            checkpoint(page.number,len(doc),'Przygotowanie skanu')
            image=Image.open(io.BytesIO(pixmap(page,dpi=int(profile['dpi']),alpha=False,colorspace=pymupdf.csRGB).tobytes('png')))
            gray=ImageOps.grayscale(image)
            histogram=gray.histogram()
            dark=sum(histogram[:253])
            if profile.get('omit_blank') and not page.get_text().strip() and dark<=max(8,int(image.width*image.height*1e-6)):continue
            if profile['color']=='Szarość':image=gray
            elif profile['color']=='Czerń i biel':image=gray.point(lambda value:255 if value>160 else 0).convert('1')
            if profile.get('rotation'):image=image.rotate(-int(profile['rotation']),expand=True,fillcolor='white')
            buffer=io.BytesIO();image.save(buffer,format='PNG');target=result.new_page(width=page.rect.width,height=page.rect.height);target.insert_image(target.rect,stream=buffer.getvalue())
        if not len(result):raise ValueError('Wszystkie strony rozpoznano jako puste. Wyłącz pomijanie pustych stron.')
        data=result.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output,data)

def split_by_codes(source,folder):
    import tempfile,re
    codes=barcode_pdf(source)
    if not codes:raise ValueError('Nie znaleziono kodów do podziału.')
    markers={}
    for item in codes:markers.setdefault(item['page'],item['text'])
    output=Path(tempfile.mkdtemp(prefix=Path(source).stem+'_kody_',dir=folder));results=[]
    with safe_open(source) as doc:
        starts=sorted(set([0,*markers]))
        for index,start in enumerate(starts):
            end=starts[index+1] if index+1<len(starts) else len(doc)
            label=re.sub(r'[^\w-]+','_',markers.get(start,'Dokument')).strip('_')[:50] or 'Kod'
            target=output/f'{index+1:03d}_{label}.pdf'
            with pymupdf.open() as part:
                part.insert_pdf(doc,from_page=start,to_page=end-1,widgets=True);data=part.tobytes(garbage=3,deflate=True)
            atomic_write_bytes(target,data);results.append(target)
    return results

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['barcode_pdf','prepare_scan','split_by_codes']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
