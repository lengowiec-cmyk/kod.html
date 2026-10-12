"""Independent Python document workflows; no KillerPDF source is included.

Export operations preserve the input and close all file handles before saving.
"""
from __future__ import annotations

from pdfmanager.security.limits import pixmap as limited_pixmap

from pdfmanager.security.limits import safe_open
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import shutil
import subprocess
import zipfile
import math
import pymupdf
from PIL import Image, ImageOps
import numpy as np
from .io_utils import atomic_write_bytes, mutate_pdf_file
from .extended_ops import _check_output


class WorkflowError(ValueError):
    pass


def open_pdf(source: Path, password: str = '') -> pymupdf.Document:
    doc = safe_open(source)
    if doc.needs_pass and not doc.authenticate(password):
        doc.close()
        raise WorkflowError('Dokument wymaga poprawnego hasła.')
    return doc


def parse_pages(expression: str, count: int) -> list[int]:
    """One-based ranges, preserving order; duplicates and invalid pages fail."""
    if not expression.strip() or expression.strip() == '*':
        return list(range(count))
    indices = []
    try:
        for part in expression.split(','):
            numbers = [int(n.strip()) for n in part.split('-')]
            if len(numbers) == 1:
                indices.append(numbers[0]-1)
            elif len(numbers) == 2 and numbers[0] <= numbers[1]:
                indices.extend(range(numbers[0]-1, numbers[1]))
            else:
                raise ValueError
    except ValueError as exc:
        raise WorkflowError('Podaj strony np. 1-3,5 lub * dla wszystkich.') from exc
    if not indices or len(indices) != len(set(indices)) or any(i < 0 or i >= count for i in indices):
        raise WorkflowError('Nieprawidłowy zakres lub powtórzone strony.')
    return indices


def export_text(source: Path, output: Path) -> None:
    _check_output(source, output)
    with open_pdf(source) as doc:
        text = '\n\n'.join(page.get_text(sort=True) for page in doc)
    atomic_write_bytes(output, text.encode('utf-8'))


def resave(source: Path, output: Path, password: str = '', new_password: str | None = None) -> None:
    _check_output(source, output)
    with open_pdf(source, password) as doc:
        if new_password is None:
            data = doc.tobytes(garbage=4, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
        else:
            if not new_password:
                raise WorkflowError('Hasło nie może być puste.')
            data = doc.tobytes(garbage=4, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                              owner_pw=new_password, user_pw=new_password,
                              permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY)
    atomic_write_bytes(output, data)


def batch_resave(folder: Path, output_dir: Path) -> list[tuple[str, str]]:
    import csv
    if folder.resolve() == output_dir.resolve():
        raise WorkflowError('Wybierz osobny katalog docelowy.')
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.pdf')
    if not sources:
        raise WorkflowError('Folder nie zawiera plików PDF.')
    targets = [output_dir/p.name for p in sources]
    if any(p.exists() for p in targets) or (output_dir/'report.csv').exists():
        raise WorkflowError('Wybierz pusty folder docelowy.')
    results = []
    from pdfmanager.dms.jobs import checkpoint
    for position,(source, target) in enumerate(zip(sources, targets)):
        checkpoint(position,len(sources),'Przetwarzanie: '+source.name)
        try:
            resave(source, target)
            results.append((source.name, 'OK'))
        except Exception as exc:
            results.append((source.name, f'ERROR: {exc}'))
    stream = io.StringIO()
    csv.writer(stream).writerows([('file', 'status'), *results])
    atomic_write_bytes(output_dir/'report.csv', stream.getvalue().encode('utf-8'))
    return results


def merge_inputs(paths: list[Path], output: Path) -> None:
    """Merge PDFs, supported images, folders and ZIP contents without extracting paths."""
    max_bytes = 512*1024*1024
    total_bytes = 0
    if not paths:
        raise WorkflowError('Wybierz pliki.')
    def append(out, name, data):
        nonlocal total_bytes
        total_bytes += len(data)
        if total_bytes > max_bytes:
            raise WorkflowError('Przekroczono limit 512 MB wejścia.')
        suffix = Path(name).suffix.lower()
        if suffix == '.pdf':
            with safe_open(stream=data, filetype='pdf') as doc:
                if doc.needs_pass:
                    raise WorkflowError(f'Plik {Path(name).name} wymaga hasła.')
                out.insert_pdf(doc, widgets=True)
        elif suffix in ('.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'):
            with Image.open(io.BytesIO(data)) as image:
                from pdfmanager.security.limits import check_pixels
                check_pixels(image.width,image.height)
                from pdfmanager.dms.jobs import checkpoint
                for frame in range(getattr(image, 'n_frames', 1)):
                    checkpoint(frame,getattr(image,'n_frames',1),'Przetwarzanie obrazu')
                    image.seek(frame)
                    rgb = ImageOps.exif_transpose(image).convert('RGB')
                    stream = io.BytesIO();rgb.save(stream, format='PNG')
                    density=image.info.get('dpi');known_density=density is not None
                    try:
                        dx,dy=float(density[0]),float(density[1])
                        if not (72<=dx<=600 and 72<=dy<=600):dx=dy=150;known_density=False
                    except (TypeError,ValueError,IndexError):dx=dy=150;known_density=False
                    width,height=rgb.width*72/dx,rgb.height*72/dy
                    if not known_density or min(dx,dy)<=96:
                        max_width,max_height=(842,595) if width>height else (595,842)
                        scale=min(1,max_width/width,max_height/height);width*=scale;height*=scale
                    page = out.new_page(width=width, height=height)
                    page.insert_image(page.rect, stream=stream.getvalue())
        else:
            raise WorkflowError(f'Nieobsługiwany format: {suffix}')
    with safe_open() as out:
        from pdfmanager.dms.jobs import checkpoint
        for position,path in enumerate(paths):
            checkpoint(position,len(paths),'Scalanie: '+Path(path).name)
            path = Path(path)
            _check_output(path, output)
            if path.is_dir():
                items = sorted(p for p in path.iterdir() if p.suffix.lower() in ('.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'))
                for item in items:
                    _check_output(item, output)
                    if item.stat().st_size > max_bytes-total_bytes:raise WorkflowError('Za duży plik.')
                    append(out, item.name, item.read_bytes())
            elif path.suffix.lower() == '.zip':
                with zipfile.ZipFile(path) as archive:
                    entries=archive.infolist()
                    if len(entries)>2000:raise WorkflowError('Archiwum przekracza limit 2000 elementów.')
                    if any(e.file_size>50*1024*1024 and e.file_size>max(1,e.compress_size)*200 for e in entries):raise WorkflowError('Podejrzany stopień kompresji archiwum.')
                    for entry in sorted(archive.infolist(), key=lambda e: e.filename):
                        if entry.is_dir() or Path(entry.filename).suffix.lower() not in ('.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'):
                            continue
                        if entry.file_size > max_bytes-total_bytes:raise WorkflowError('Za duże archiwum ZIP.')
                        append(out, entry.filename, archive.read(entry))
            else:
                if path.stat().st_size > max_bytes-total_bytes:raise WorkflowError('Za duży plik.')
                append(out, path.name, path.read_bytes())
        if not len(out):raise WorkflowError('Nie znaleziono obsługiwanych dokumentów.')
        data = out.tobytes(garbage=3, deflate=True)
    atomic_write_bytes(output, data)


def crop_document(source: Path, output: Path, indices: list[int], margins: tuple[float,float,float,float]) -> None:
    _check_output(source, output)
    if any(not math.isfinite(v) or v < 0 for v in margins):raise WorkflowError('Marginesy muszą być nieujemne.')
    with open_pdf(source) as doc:
        for i in indices:
            page = doc[i]
            left, top, right, bottom = margins
            r = page.cropbox
            box = pymupdf.Rect(r.x0+left, r.y0+top, r.x1-right, r.y1-bottom)
            if box.is_empty:raise WorkflowError('Marginesy usuwają całą stronę.')
            page.set_cropbox(box)
        data = doc.tobytes(garbage=3, deflate=True)
    atomic_write_bytes(output, data)


def resize_document(source: Path, output: Path, width: float, height: float) -> None:
    _check_output(source, output)
    if not all(math.isfinite(v) and 72 <= v <= 14400 for v in (width,height)):
        raise WorkflowError('Wymiary strony muszą wynosić 72–14400 punktów.')
    with open_pdf(source) as doc, safe_open() as out:
        for page in doc:
            target = out.new_page(width=width,height=height)
            target.show_pdf_page(target.rect, doc, page.number, keep_proportion=True)
        data = out.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output, data)


def transform_image(image: Image.Image, operation: str, value=0) -> Image.Image:
    image = image.convert('RGB')
    if operation == 'flip_horizontal':return ImageOps.mirror(image)
    if operation == 'flip_vertical':return ImageOps.flip(image)
    if operation in ('rotate','deskew'):
        if not math.isfinite(float(value)):raise WorkflowError('Nieprawidłowy kąt.')
        return image.rotate(float(value), resample=Image.Resampling.BICUBIC, expand=True, fillcolor='white')
    if operation == 'levels':
        black, white, gamma = value
        if not (0 <= black < white <= 255 and .1 <= gamma <= 5):raise WorkflowError('Nieprawidłowe poziomy.')
        lut = [round(255*min(1,max(0,(i-black)/(white-black)))**(1/gamma)) for i in range(256)]
        return image.point(lut*3)
    if operation == 'perspective':
        points = np.array(value,dtype=float)
        if points.shape != (4,2) or not np.isfinite(points).all():raise WorkflowError('Podaj cztery narożniki: lewy górny, prawy górny, prawy dolny, lewy dolny.')
        if any(x < 0 or y < 0 or x > image.width or y > image.height for x,y in points):raise WorkflowError('Narożniki muszą leżeć wewnątrz obrazu.')
        turns=[]
        for i in range(4):
            a,b=points[(i+1)%4]-points[i],points[(i+2)%4]-points[(i+1)%4]
            turns.append(a[0]*b[1]-a[1]*b[0])
        if not (all(v>0 for v in turns) or all(v<0 for v in turns)):
            raise WorkflowError('Podaj narożniki wypukłego obszaru w kolejności LG,PG,PD,LD.')
        target=[(0,0),(image.width,0),(image.width,image.height),(0,image.height)]
        matrix=[];vector=[]
        for (x,y),(u,v) in zip(target,points):
            matrix.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]])
            vector.extend([u,v])
        try:coeff=np.linalg.solve(matrix,vector)
        except np.linalg.LinAlgError as exc:raise WorkflowError('Nieprawidłowe narożniki.') from exc
        return image.transform(image.size,Image.Transform.PERSPECTIVE,tuple(coeff),Image.Resampling.BICUBIC,fillcolor='white')
    raise WorkflowError('Nieznana operacja obrazu.')


def transform_pdf(source: Path, output: Path, operation: str, value=0, dpi: int = 150) -> None:
    _check_output(source,output)
    if not 72 <= dpi <= 600:raise WorkflowError('DPI: 72–600.')
    with open_pdf(source) as doc, safe_open() as out:
        for page in doc:
            pix = limited_pixmap(page,dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
            image = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            effective_value = [(x*image.width,y*image.height) for x,y in value] if operation=='perspective_normalized' else value
            image = transform_image(image,'perspective' if operation=='perspective_normalized' else operation,effective_value)
            stream=io.BytesIO();image.save(stream,format='PNG')
            target=out.new_page(width=image.width*72/dpi,height=image.height*72/dpi)
            target.insert_image(target.rect,stream=stream.getvalue())
        data=out.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output,data)


def tesseract_executable() -> str:
    found=shutil.which('tesseract')
    if not found:
        for path in (Path('C:/Program Files/Tesseract-OCR/tesseract.exe'),Path('C:/Program Files (x86)/Tesseract-OCR/tesseract.exe')):
            if path.is_file():return str(path)
        raise WorkflowError('Zainstaluj Tesseract OCR 5 i dodaj go do PATH. OCR działa lokalnie.')
    return found


def ocr_languages() -> list[str]:
    proc=subprocess.run([tesseract_executable(),'--list-langs'],capture_output=True,text=True,timeout=20,check=True)
    from .ocr_models import model_dir
    native=[s.strip() for s in proc.stdout.splitlines()[1:] if s.strip() and s.strip() != 'osd']
    return sorted(set(native+[p.stem for p in model_dir().glob('*.traineddata')]))


def ocr_document(source: Path, output: Path, language='eng', dpi=200, text_only=False, indices: list[int] | None = None, region: tuple | None = None) -> None:
    _check_output(source,output)
    available=ocr_languages()
    if any(lang not in available for lang in language.split('+')):raise WorkflowError('Brak wybranego modelu językowego Tesseract.')
    if not 72 <= dpi <= 600:raise WorkflowError('DPI: 72–600.')
    texts=[]
    with TemporaryDirectory(prefix='pdfmanager-ocr-') as folder, open_pdf(source) as doc, safe_open() as out:
        folder=Path(folder)
        from .ocr_models import native_model_dir, model_dir, verify_model, MODEL_BLOBS
        native=native_model_dir(tesseract_executable())
        models=folder/'tessdata';models.mkdir()
        for lang in language.split('+'):
            downloaded=model_dir()/(lang+'.traineddata')
            if downloaded.is_file():
                data=downloaded.read_bytes()
                if lang in MODEL_BLOBS:verify_model(lang,data)
                (models/downloaded.name).write_bytes(data)
            elif native and (native/(lang+'.traineddata')).is_file():
                shutil.copyfile(native/(lang+'.traineddata'),models/(lang+'.traineddata'))
            else:raise WorkflowError('Nie znaleziono modelu OCR: '+lang)
        from pdfmanager.dms.jobs import checkpoint,run_process
        selected=list(indices if indices is not None else range(len(doc)))
        for position,i in enumerate(selected):
            checkpoint(position,len(selected),f'OCR: strona {position+1}/{len(selected)}')
            page=doc[i]
            clip=(pymupdf.Rect(region)*page.rotation_matrix) if region else None
            if clip and (clip.is_empty or not page.rect.contains(clip)):raise WorkflowError('Obszar OCR musi leżeć wewnątrz strony.')
            pix=limited_pixmap(page,dpi=dpi,colorspace=pymupdf.csRGB,alpha=False,clip=clip)
            png=folder/'input.png';pix.save(png)
            dest=folder/'result'
            command=[tesseract_executable(),str(png),str(dest),'--tessdata-dir',str(models),'-l',language,'--dpi',str(dpi),'-c','tessedit_create_txt=1' if text_only else 'tessedit_create_pdf=1']
            result=run_process(command,timeout=180)
            if result.returncode:raise WorkflowError(f'OCR nie powiodło się: {result.stderr[-1000:]}')
            if text_only:texts.append(dest.with_suffix('.txt').read_text(encoding='utf-8'))
            else:
                with safe_open(dest.with_suffix('.pdf')) as recognized:out.insert_pdf(recognized)
        checkpoint(len(selected),len(selected),'Zapis wyniku OCR')
        data='\n\n'.join(texts).encode('utf-8') if text_only else out.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output,data)


@dataclass(frozen=True)
class FormField:
    page: int
    xref: int
    name: str
    kind: int
    value: object
    choices: tuple
    on_value: object


def form_fields(source: Path) -> list[FormField]:
    with open_pdf(source) as doc:
        return [FormField(page.number,w.xref,w.field_name,w.field_type,w.field_value,
                          tuple(w.choice_values or ()),w.on_state()) for page in doc for w in (page.widgets() or ())]


def fill_form(source: Path, output: Path, values: dict[int, object]) -> None:
    _check_output(source,output)
    with open_pdf(source) as doc:
        found=set()
        for page in doc:
            for w in page.widgets() or ():
                if w.xref in values:
                    if w.field_type in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE,pymupdf.PDF_WIDGET_TYPE_BUTTON):raise WorkflowError('Tego rodzaju pola nie można wypełnić tekstem.')
                    w.field_value=values[w.xref];w.update();found.add(w.xref)
        if found != set(values):raise WorkflowError('Nie znaleziono wszystkich pól.')
        data=doc.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output,data)


def bookmarks(source: Path) -> list[list]:
    with open_pdf(source) as doc:return doc.get_toc()


def set_bookmarks(source: Path, output: Path, toc: list[list]) -> None:
    _check_output(source,output)
    with open_pdf(source) as doc:
        doc.set_toc(toc)
        data=doc.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output,data)


def redact(source: Path, page_index: int, rect: tuple) -> None:
    def mutate(doc):
        page=doc[page_index];r=pymupdf.Rect(rect)
        if r.is_empty:raise WorkflowError('Wybierz prostokąt.')
        page.add_redact_annot(r,fill=(0,0,0));page.apply_redactions()
    mutate_pdf_file(source,mutate)


def add_ink(source: Path, page_index: int, points: list[tuple[float,float]]) -> None:
    if len(points)<2:return
    def mutate(doc):
        annot=doc[page_index].add_ink_annot([points]);annot.set_colors(stroke=(.1,.3,.8));annot.set_border(width=2);annot.update()
    mutate_pdf_file(source,mutate)


def compare_documents(left: Path, right: Path) -> list[dict]:
    with open_pdf(left) as a, open_pdf(right) as b:
        result=[]
        for i in range(max(len(a),len(b))):
            if i>=len(a) or i>=len(b):
                result.append({'page':i+1,'status':'missing-left' if i>=len(a) else 'missing-right','difference':100.0});continue
            image_a=limited_pixmap(a[i],dpi=72,colorspace=pymupdf.csRGB,alpha=False)
            image_b=limited_pixmap(b[i],dpi=72,colorspace=pymupdf.csRGB,alpha=False)
            if (image_a.width,image_a.height)!=(image_b.width,image_b.height):
                result.append({'page':i+1,'status':'different-size','difference':100.0});continue
            aa=np.frombuffer(image_a.samples,dtype=np.uint8).reshape(-1,3)
            bb=np.frombuffer(image_b.samples,dtype=np.uint8).reshape(-1,3)
            difference=float(np.any(abs(aa.astype(int)-bb.astype(int))>12,axis=1).mean()*100)
            result.append({'page':i+1,'status':'changed' if difference else 'same','difference':round(difference,3)})
        return result


def attachment_names(source: Path) -> list[str]:
    with open_pdf(source) as doc:return doc.embfile_names()


def add_attachment(source: Path, output: Path, attachment: Path) -> None:
    _check_output(source,output)
    if attachment.stat().st_size > 50*1024*1024:raise WorkflowError('Limit załącznika: 50 MB.')
    with open_pdf(source) as doc:
        if attachment.name in doc.embfile_names():raise WorkflowError('Załącznik o tej nazwie już istnieje.')
        doc.embfile_add(attachment.name,attachment.read_bytes(),filename=attachment.name)
        data=doc.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output,data)


def extract_attachment(source: Path, name: str, output: Path) -> None:
    _check_output(source,output)
    with open_pdf(source) as doc:
        info=doc.embfile_info(name)
        if info.get('size',0)>50*1024*1024:raise WorkflowError('Załącznik przekracza limit 50 MB.')
        data=doc.embfile_get(name)
        if len(data)>50*1024*1024:raise WorkflowError('Załącznik przekracza limit 50 MB.')
    atomic_write_bytes(output,data)


def sign_pkcs12(source: Path, output: Path, certificate: Path, password: str) -> None:
    from pyhanko.sign import signers
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    _check_output(source,output)
    signer=signers.SimpleSigner.load_pkcs12(str(certificate),passphrase=password.encode('utf-8'))
    if signer is None:raise WorkflowError('Nie można odczytać certyfikatu PKCS#12. Sprawdź hasło.')
    with source.open('rb') as stream:
        writer=IncrementalPdfFileWriter(stream)
        buffer=io.BytesIO()
        from uuid import uuid4
        metadata=signers.PdfSignatureMetadata(field_name='PDFManagerSignature_'+uuid4().hex[:12])
        signers.PdfSigner(metadata,signer=signer).sign_pdf(writer,output=buffer)
    atomic_write_bytes(output,buffer.getvalue())


def verify_signatures(source: Path) -> list[dict]:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext
    with source.open('rb') as stream:
        reader=PdfFileReader(stream)
        result=[]
        for signature in reader.embedded_signatures:
            status=validate_pdf_signature(signature,signer_validation_context=ValidationContext(allow_fetching=False))
            result.append({'field':signature.field_name,'intact':status.intact,'valid':status.valid,'trusted':status.trusted,'summary':status.summary()})
        return result


def nup_document(source: Path, output: Path, per_sheet: int = 2, indices: list[int] | None = None) -> None:
    """Compose print sheets as raster pages with visible annotations."""
    _check_output(source,output)
    layouts={1:(1,1),2:(2,1),4:(2,2),6:(2,3),9:(3,3)}
    if per_sheet not in layouts:raise WorkflowError('Strony na arkuszu: 1,2,4,6,9.')
    columns,rows=layouts[per_sheet]
    width,height=(842,595) if per_sheet==2 else (595,842)
    margin=18;cell_width=(width-2*margin)/columns;cell_height=(height-2*margin)/rows
    with open_pdf(source) as doc,safe_open() as out:
        chosen=indices if indices is not None else list(range(len(doc)))
        if not chosen or any(not 0<=i<len(doc) for i in chosen):raise WorkflowError('Nieprawidłowe strony.')
        for offset in range(0,len(chosen),per_sheet):
            target=out.new_page(width=width,height=height)
            for cell,index in enumerate(chosen[offset:offset+per_sheet]):
                x=margin+(cell%columns)*cell_width;y=margin+(cell//columns)*cell_height
                pix=limited_pixmap(doc[index],dpi=200,colorspace=pymupdf.csRGB,alpha=False,annots=True)
                target.insert_image(pymupdf.Rect(x,y,x+cell_width-6,y+cell_height-6),stream=pix.tobytes('png'),keep_proportion=True)
        data=out.tobytes(garbage=3,deflate=True)
    atomic_write_bytes(output,data)

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['export_text', 'resave', 'batch_resave', 'merge_inputs', 'crop_document', 'resize_document', 'transform_pdf', 'ocr_document', 'form_fields', 'fill_form', 'bookmarks', 'set_bookmarks', 'redact', 'add_ink', 'compare_documents', 'attachment_names', 'add_attachment', 'extract_attachment', 'sign_pkcs12', 'verify_signatures', 'nup_document']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
