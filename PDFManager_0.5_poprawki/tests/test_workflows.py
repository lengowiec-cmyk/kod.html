from pathlib import Path
import io
import zipfile
from datetime import datetime,timedelta,timezone
import pymupdf
import pytest
from PIL import Image,ImageDraw,ImageFont
from pdfmanager.pdf_engine import workflows as ops
from pdfmanager.pdf_engine import annotations

@pytest.fixture
def document(tmp_path):
    path=tmp_path/'original.pdf'
    with pymupdf.open() as doc:
        for i in range(2):
            page=doc.new_page(width=300,height=400)
            page.insert_text((40,80),f'Hello page {i+1}',fontsize=16)
        doc.set_toc([[1,'Chapter',1]])
        doc.save(path)
    return path

@pytest.mark.parametrize('raw,expected',[('*',[0,1,2,3,4]),('1-3,5',[0,1,2,4]),('5,1',[4,0])])
def test_ranges(raw,expected):assert ops.parse_pages(raw,5)==expected

@pytest.mark.parametrize('raw',['0','2-1','1,1','1-9','nan','1-2-3'])
def test_bad_ranges(raw):
    with pytest.raises(ops.WorkflowError):ops.parse_pages(raw,5)


def test_password_round_trip(document,tmp_path):
    encrypted=tmp_path/'protected.pdf';plain=tmp_path/'plain.pdf'
    ops.resave(document,encrypted,new_password='test-only-password')
    with pymupdf.open(encrypted) as doc:
        assert doc.needs_pass
        assert not doc.authenticate('wrong')
    with pytest.raises(ops.WorkflowError):ops.resave(encrypted,plain,password='wrong')
    ops.resave(encrypted,plain,password='test-only-password')
    with pymupdf.open(plain) as doc:
        assert not doc.needs_pass
        assert 'Hello' in doc[0].get_text()
        assert doc.get_toc()==[[1,'Chapter',1]]


def test_text_export(document,tmp_path):
    out=tmp_path/'text.txt';ops.export_text(document,out)
    assert 'Hello page 2' in out.read_text()


def test_merge_pdf_images_zip(document,tmp_path):
    image=tmp_path/'image.png';Image.new('RGB',(100,120),'white').save(image)
    archive=tmp_path/'inputs.zip'
    with zipfile.ZipFile(archive,'w') as z:z.write(image,'../image.png')
    out=tmp_path/'merged.pdf';ops.merge_inputs([document,archive],out)
    with pymupdf.open(out) as doc:assert len(doc)==3
    assert not (tmp_path.parent/'image.png').exists()


def test_crop_resize(document,tmp_path):
    crop=tmp_path/'crop.pdf';ops.crop_document(document,crop,[0],(10,20,30,40))
    with pymupdf.open(crop) as doc:assert tuple(doc[0].rect)==(0,0,260,340)
    out=tmp_path/'resized.pdf';ops.resize_document(document,out,595,842)
    with pymupdf.open(out) as doc:
        assert doc[0].rect.width==595
        assert 'Hello page 1' in doc[0].get_text()


def test_transform_pixels():
    image=Image.new('RGB',(5,3),'white');image.putpixel((0,0),(0,0,0))
    assert ops.transform_image(image,'flip_horizontal').getpixel((4,0))==(0,0,0)
    assert ops.transform_image(image,'flip_vertical').getpixel((0,2))==(0,0,0)
    assert ops.transform_image(image,'rotate',90).size==(3,5)
    assert ops.transform_image(image,'levels',(0,255,1)).getpixel((0,0))==(0,0,0)
    same=ops.transform_image(image,'perspective',[(0,0),(5,0),(5,3),(0,3)])
    assert same.size==image.size
    assert same.getpixel((0,0))==(0,0,0)


def test_transform_pdf(document,tmp_path):
    out=tmp_path/'transformed.pdf';ops.transform_pdf(document,out,'flip_horizontal',dpi=72)
    with pymupdf.open(out) as doc:
        assert len(doc)==2
        assert doc[0].get_images()
        assert doc[0].get_text()==''
    perspective=tmp_path/'perspective.pdf'
    ops.transform_pdf(document,perspective,'perspective_normalized',[(0,0),(1,0),(1,1),(0,1)],dpi=72)
    with pymupdf.open(perspective) as doc:assert len(doc)==2


def test_forms(document,tmp_path):
    with pymupdf.open(document) as doc:
        widget=pymupdf.Widget();widget.field_name='Name';widget.field_type=pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.rect=pymupdf.Rect(30,120,180,150);widget.field_value='Before';doc[0].add_widget(widget)
        data=doc.tobytes()
    document.write_bytes(data)
    fields=ops.form_fields(document);assert fields[0].value=='Before'
    out=tmp_path/'form.pdf';ops.fill_form(document,out,{fields[0].xref:'After'})
    assert ops.form_fields(out)[0].value=='After'
    assert ops.form_fields(document)[0].value=='Before'


def test_attachment_bookmarks(document,tmp_path):
    attachment=tmp_path/'note.txt';attachment.write_text('hello')
    out=tmp_path/'attached.pdf';ops.add_attachment(document,out,attachment)
    assert ops.attachment_names(out)==['note.txt']
    extracted=tmp_path/'copy.txt';ops.extract_attachment(out,'note.txt',extracted);assert extracted.read_text()=='hello'
    toc=tmp_path/'toc.pdf';ops.set_bookmarks(document,toc,[[1,'Second',2]])
    assert ops.bookmarks(toc)==[[1,'Second',2]]


def test_compare(document,tmp_path):
    assert all(row['status']=='same' for row in ops.compare_documents(document,document))
    other=tmp_path/'other.pdf';ops.resave(document,other)
    with pymupdf.open(other) as doc:
        doc[0].insert_text((40,140),'CHANGED');doc.delete_page(1);data=doc.tobytes()
    other.write_bytes(data)
    rows=ops.compare_documents(document,other)
    assert rows[0]['status']=='changed'
    assert rows[1]['status']=='missing-right'


def test_redaction_and_ink(document):
    ops.add_ink(document,0,[(20,20),(25,40),(40,30)])
    annotations.add_arrow(document,0,(15,15),(100,100))
    annotations.add_polygon(document,0,[(100,100),(120,140),(140,100)])
    ops.redact(document,0,(30,50,200,90))
    with pymupdf.open(document) as doc:
        assert 'Hello page 1' not in doc[0].get_text()
        assert len(list(doc[0].annots()))==3


def test_batch_failure_accounted(document,tmp_path):
    source=tmp_path/'in';source.mkdir();(source/'good.pdf').write_bytes(document.read_bytes());(source/'bad.pdf').write_bytes(b'not PDF')
    results=ops.batch_resave(source,tmp_path/'out')
    assert len(results)==2
    assert sum(status=='OK' for _,status in results)==1
    assert (tmp_path/'out/report.csv').exists()


@pytest.mark.parametrize('language',['eng','pol',pytest.param('pol-uppercase',marks=pytest.mark.xfail(strict=True,reason='Known Tesseract tessdata_fast accuracy limit: uppercase Ź is recognized as Ż in the 150-DPI fixture.'))])
def test_real_ocr(tmp_path,language):
    if not __import__('shutil').which('tesseract'):pytest.skip('Tesseract unavailable')
    ocr_language='pol' if language=='pol-uppercase' else language
    if ocr_language not in ops.ocr_languages():pytest.skip('OCR model unavailable: '+ocr_language)
    image=Image.new('RGB',(1400,500),'white');draw=ImageDraw.Draw(image)
    fontpath=Path(__file__).parent.parent/'pdfmanager/resources/fonts/DejaVuSans.ttf'
    font=ImageFont.truetype(str(fontpath),70);draw.text((80,150),'HELLO PDF MANAGER',font=font,fill='black')
    if language in ('pol','pol-uppercase'):draw.text((80,280),'Zażółć gęślą jaźń' if language=='pol' else 'ZAŻÓŁĆ GĘŚLĄ JAŹŃ',font=font,fill='black')
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    source=tmp_path/'scan.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page(width=700,height=250);page.insert_image(page.rect,stream=buffer.getvalue());doc.save(source)
    out=tmp_path/'ocr.pdf';ops.ocr_document(source,out,language=ocr_language,dpi=150)
    with pymupdf.open(out) as doc:assert 'HELLO PDF MANAGER' in doc[0].get_text()
    text=tmp_path/'ocr.txt';ops.ocr_document(source,text,language=ocr_language,text_only=True,dpi=150)
    assert 'HELLO PDF MANAGER' in text.read_text()
    if language=='pol':assert 'Zażółć gęślą jaźń' in text.read_text()
    if language=='pol-uppercase':assert 'ZAŻÓŁĆ GĘŚLĄ JAŹŃ' in text.read_text()


def test_signature_with_ephemeral_certificate(document,tmp_path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.serialization import pkcs12
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'PDFManager TEST ONLY')]);now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.KeyUsage(True,True,False,False,False,False,False,False,False),critical=True).sign(key,hashes.SHA256()))
    pfx=tmp_path/'test-only.pfx'
    pfx.write_bytes(pkcs12.serialize_key_and_certificates(b'test',key,cert,None,serialization.BestAvailableEncryption(b'test-only')))
    out=tmp_path/'signed.pdf';ops.sign_pkcs12(document,out,pfx,'test-only')
    statuses=ops.verify_signatures(out)
    assert len(statuses)==1
    assert statuses[0]['intact'] and statuses[0]['valid']
    assert not statuses[0]['trusted']


def test_reject_crossed_perspective():
    with pytest.raises(ops.WorkflowError):
        ops.transform_image(Image.new('RGB',(100,100)), 'perspective',[(0,0),(100,100),(100,0),(0,100)])


def test_checkbox_round_trip(document,tmp_path):
    with pymupdf.open(document) as doc:
        w=pymupdf.Widget();w.field_name='Consent';w.field_type=pymupdf.PDF_WIDGET_TYPE_CHECKBOX;w.rect=pymupdf.Rect(30,150,50,170)
        doc[0].add_widget(w);data=doc.tobytes()
    document.write_bytes(data)
    field=ops.form_fields(document)[0];out=tmp_path/'checked.pdf'
    ops.fill_form(document,out,{field.xref:field.on_value})
    assert ops.form_fields(out)[0].value==field.on_value


def test_ocr_model_checksum_rejects_corruption():
    from pdfmanager.pdf_engine.ocr_models import verify_model
    with pytest.raises(ValueError):verify_model('pol',b'corrupt model')


def test_nup_print_sheets(document,tmp_path):
    out=tmp_path/'sheets.pdf';ops.nup_document(document,out,2)
    with pymupdf.open(out) as doc:
        assert len(doc)==1
        assert len(doc[0].get_images())==2
        assert doc[0].rect.width>doc[0].rect.height
