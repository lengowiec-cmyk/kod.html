from dataclasses import replace
import pymupdf
import pytest
from pdfmanager.pdf_engine.content import insert_content_at
from pdfmanager.pdf_engine.text_edit import TextSpan, get_default_text_edit_engine

def test_insert_unicode_and_overflow_preserves_file(tmp_path):
    path=tmp_path/'document.pdf'
    doc=pymupdf.open();doc.new_page();doc.save(path);doc.close()
    style=TextSpan(0,'','',(0,0,0,0),(0,0),'DejaVuSans',18,(255,0,0),True,False)
    insert_content_at(path,0,(30,30,400,160),text='Zażółć gęślą jaźń\nDruga linia',style=style)
    with pymupdf.open(path) as doc:assert 'Zażółć' in doc[0].get_text()
    before=path.read_bytes()
    with pytest.raises(ValueError):insert_content_at(path,0,(30,30,40,40),text='Nie mieści się',style=style)
    assert path.read_bytes()==before

def test_existing_text_size_and_color(tmp_path):
    path=tmp_path/'document.pdf';doc=pymupdf.open();page=doc.new_page();page.insert_text((50,80),'Original');doc.save(path);doc.close()
    engine=get_default_text_edit_engine();span=engine.extract_spans(path,0)[0]
    engine.apply_edit(path,span,'Changed',style=replace(span,font_size=24,color_rgb=(255,0,0)))
    spans=engine.extract_spans(path,0)
    assert spans[0].text=='Changed'
    assert spans[0].font_size==24
    assert spans[0].color_rgb==(255,0,0)
