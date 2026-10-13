"""Safe structured text: no user HTML, URLs, scripts or external resources."""
import html,math
import pymupdf
from uuid import uuid4
from pdfmanager.pdf_engine.font_resolver import system_font_file,FALLBACK_VARIANTS,_font_covers_text

def render(page,rect,payload):
    if not isinstance(payload,list) or not 1<=len(payload)<=1000:raise ValueError('Zbyt wiele akapitów.')
    archive=pymupdf.Archive();css=[];blocks=[];fonts={};count=0;fallbacks=set()
    def rgb(value):
        if not isinstance(value,(tuple,list)) or len(value)!=3 or any(type(n) is not int or not 0<=n<=255 for n in value):raise ValueError('Nieprawidłowy kolor.')
        return '#%02x%02x%02x'%tuple(value)
    for paragraph in payload:
        align=paragraph.get('align','left')
        if align not in ('left','right','center','justify'):raise ValueError('Nieprawidłowe wyrównanie.')
        indent=paragraph.get('indent',0);spacing=paragraph.get('spacing',1.0)
        if type(indent) is not int or not 0<=indent<=20 or not 0.5<=float(spacing)<=3:raise ValueError('Nieprawidłowy akapit.')
        runs=[]
        for run in paragraph['runs']:
            text=run['text'];count+=len(text)
            if count>100000:raise ValueError('Tekst przekracza limit 100 000 znaków.')
            size=float(run['size'])
            if not math.isfinite(size) or not 1<=size<=300:raise ValueError('Rozmiar czcionki musi wynosić od 1 do 300 pkt.')
            bold=bool(run.get('bold'));italic=bool(run.get('italic'));family=run['family']
            if not isinstance(family,str) or len(family)>200:raise ValueError('Nieprawidłowa czcionka.')
            path=system_font_file(family,bold,italic)
            if path is None:fallbacks.add(family);path=FALLBACK_VARIANTS[bold,italic]
            data=path.read_bytes()
            if not _font_covers_text(data,text):raise ValueError('Wybrana czcionka nie obsługuje wszystkich znaków.')
            key=str(path)
            if key not in fonts:
                name='pdm'+str(len(fonts));fonts[key]=name;archive.add((data,name+'.ttf'));css.append('@font-face{font-family:'+name+';src:url('+name+'.ttf)}')
            decorations=[]
            if run.get('underline'):decorations.append('underline')
            if run.get('strike'):decorations.append('line-through')
            styling='font-family:'+fonts[key]+f';font-size:{size}pt;color:'+rgb(run['color'])
            if decorations:styling+=';text-decoration:'+' '.join(decorations)
            if run.get('background'):styling+=';background-color:'+rgb(run['background'])
            tag='sup' if run.get('script')=='super' else 'sub' if run.get('script')=='sub' else 'span'
            runs.append('<'+tag+' style="'+styling+'">'+html.escape(text).replace('\n','<br>')+'</'+tag+'>')
        styling=f'margin:0;padding:0;line-height:{spacing};text-align:{align};margin-left:{indent*12}pt'
        after=float(paragraph.get('after',0))
        if not math.isfinite(after) or not 0<=after<=100:raise ValueError('Nieprawidłowy odstęp akapitu.')
        styling+=f';margin-bottom:{after}pt'
        if paragraph.get('background'):styling+=';background-color:'+rgb(paragraph['background'])
        if paragraph.get('border'):styling+=';border:1pt solid #385572;padding:3pt'
        prefix=html.escape(str(paragraph.get('prefix','')))
        blocks.append('<div style="'+styling+'">'+prefix+''.join(runs)+'</div>')
    if not count:raise ValueError('Wpisz tekst.')
    spare,scale=page.insert_htmlbox(rect,''.join(blocks),css='*{margin:0;padding:0}'+''.join(css),archive=archive,scale_low=1)
    if spare<0:raise ValueError('Tekst nie mieści się w polu. Powiększ pole albo zmniejsz czcionkę. Zmiana nie została zapisana.')

    return sorted(fallbacks)

def insert_rich_text(path,page_index,rect,payload,original=None):
    from pdfmanager.pdf_engine.io_utils import mutate_pdf_file
    def mutate(doc):
        page=doc[page_index];box=pymupdf.Rect(rect)
        if box.is_empty or not page.rect.contains(box):raise ValueError('Pole tekstowe musi mieścić się na stronie.')
        box=box*page.derotation_matrix
        if original:
            from pdfmanager.pdf_engine.text_edit import PyMuPDFTextEditBackend
            background,_=PyMuPDFTextEditBackend._detect_background_color(page,pymupdf.Rect(original))
            page.add_redact_annot(pymupdf.Rect(original),fill=background);page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,graphics=0)
        fallback=render(page,box,payload)
        return {'fallback_fonts':fallback}
    return mutate_pdf_file(path,mutate)

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['insert_rich_text']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
