
from pdfmanager.security.limits import safe_open
"""Positioned text/image insertion with transactional saves and overflow validation."""
import pymupdf
from uuid import uuid4
from pdfmanager.pdf_engine.io_utils import mutate_pdf_file
from pdfmanager.pdf_engine.font_resolver import resolve_font

def insert_content_at(path,page_index,rect,*,text='',style=None,image=None,font_file=None):
    def mutate(doc):
        page=doc[page_index];box=pymupdf.Rect(rect)
        if box.is_empty or not page.rect.contains(box):
            raise ValueError('Obszar musi mieścić się w granicach strony. Zmniejsz rozmiar lub zmień pozycję.')
        # Convert displayed page coordinates to the unrotated content coordinate system.
        box=box*page.derotation_matrix
        previous=set(page.get_contents())
        if image:
            import io
            from PIL import Image
            from pdfmanager.security.limits import check_pixels
            with Image.open(io.BytesIO(image)) as source_image:check_pixels(source_image.width,source_image.height)
            page.insert_image(box,stream=image,keep_proportion=True)
        else:
            if not text.strip():raise ValueError('Wpisz tekst lub wybierz obraz.')
            font=resolve_font(page,style.font_name,text,style.bold,style.italic)
            if font_file is not None:
                from pathlib import Path
                from pdfmanager.pdf_engine.font_resolver import ResolvedFont, _font_covers_text
                buffer=Path(font_file).read_bytes()
                if not _font_covers_text(buffer,text):raise ValueError('Czcionka nie obsługuje wszystkich znaków.')
                font=ResolvedFont('custom_'+uuid4().hex,None,buffer,False)
            page.insert_font(fontname=font.fontname,fontbuffer=font.fontbuffer,fontfile=str(font.fontfile) if font.fontfile else None)
            remaining=page.insert_textbox(box,text,fontname=font.fontname,fontsize=style.font_size,color=tuple(c/255 for c in style.color_rgb))
            if remaining<0:raise ValueError('Tekst nie mieści się w polu. Powiększ pole lub zmniejsz czcionkę.')
        import json,uuid
        object_id=uuid.uuid4().hex
        for xref in set(page.get_contents())-previous:
            doc.xref_set_key(xref,'PDFManagerObject',pymupdf.get_pdf_str(json.dumps({'id':object_id,'rect':list(box)})))
        return object_id
    return mutate_pdf_file(path,mutate)

def inserted_objects(path,page_index):
    import json
    with safe_open(path) as doc:
        page=doc[page_index];objects={}
        for xref in page.get_contents():
            kind,value=doc.xref_get_key(xref,'PDFManagerObject')
            if kind=='string':
                data=json.loads(value);objects[data['id']]=data
        return list(objects.values())

def transform_inserted(path,page_index,object_id,rect):
    """Transform only streams tagged by this editor, never redact nearby content."""
    import json
    def mutate(doc):
        page=doc[page_index];target=pymupdf.Rect(rect)
        bounds=page.rect*page.derotation_matrix
        if target.is_empty or not bounds.contains(target):raise ValueError('Element musi mieścić się na stronie.')
        found=False
        for xref in page.get_contents():
            kind,value=doc.xref_get_key(xref,'PDFManagerObject')
            if kind!='string':continue
            data=json.loads(value)
            if data['id']!=object_id:continue
            original=pymupdf.Rect(data['rect']);sx=target.width/original.width;sy=target.height/original.height
            tx=target.x0-sx*original.x0;ty=target.y0-sy*original.y0
            matrix=page.transformation_matrix*pymupdf.Matrix(sx,0,0,sy,tx,ty)*~page.transformation_matrix
            stream=doc.xref_stream(xref)
            command=('q '+' '.join(f'{value:.8f}' for value in matrix)+' cm\n').encode()
            doc.update_stream(xref,command+stream+b'\nQ\n')
            data['rect']=list(target);doc.xref_set_key(xref,'PDFManagerObject',pymupdf.get_pdf_str(json.dumps(data)));found=True
        if not found:raise ValueError('Nie znaleziono elementu dodanego przez PDFManager.')
    return mutate_pdf_file(path,mutate)

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['insert_content_at', 'inserted_objects', 'transform_inserted']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
