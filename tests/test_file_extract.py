"""Synthetic local corpus, executed in the OCR image (no external downloads)."""
import io
import json
import zipfile
from pathlib import Path
import pytest
from PIL import Image,ImageDraw,ImageFont
import pymupdf as fitz
from ai_firewall.file_extract import extract

PERSON='Иван Петрович Соколов'

def picture(text):
    image=Image.new('RGB',(1600,320),'white')
    ImageDraw.Draw(image).text((40,65),text,fill='black',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',40))
    return image


def corpus(root):
    root.mkdir(parents=True,exist_ok=True)
    for name,text in [('person.png','ФИО: '+PERSON),('phone.jpg','Телефон: +7 (999) 123-45-67'),('secret.png','API_KEY: sk-proj-'+'AbC123dEf456'*5)]:picture(text).save(root/name)
    picture('БИК: 044525225').save(root/'bank.tiff',save_all=True,append_images=[picture('Счет: 40702810900000002851')])
    picture('English document: hello world').save(root/'english.webp')
    Image.new('RGB',(100,100),'white').save(root/'bad.png')
    picture('ФИО: '+PERSON+' ИНН: 7707083893').save(root/'scan.png')
    picture('СНИЛС: 112-233-445 95').save(root/'snils.png')
    for name in ('scan.pdf','mixed.pdf','text.pdf','last.pdf'):
        doc=fitz.open()
        if name=='text.pdf':
            page=doc.new_page();page.insert_font(fontname='custom',fontfile='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf');page.insert_text((40,90),'ФИО: '+PERSON,fontname='custom',fontsize=18)
        elif name=='mixed.pdf':
            page=doc.new_page();page.insert_text((40,60),'Ordinary PDF text',fontsize=18);page.insert_image(fitz.Rect(30,110,570,218),filename=str(root/'snils.png'))
        else:
            if name=='last.pdf':
                page=doc.new_page();page.insert_text((40,70),'First page ordinary text',fontsize=18)
            page=doc.new_page();page.insert_image(fitz.Rect(30,60,570,168),filename=str(root/'scan.png'))
        doc.save(root/name);doc.close()
    ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    for name,body in [('table.docx',f'<w:tbl><w:tr><w:tc><w:p><w:r><w:t>{PERSON}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'),('image.docx','<w:p><w:r><w:t>Document image</w:t></w:r></w:p>')]:
        with zipfile.ZipFile(root/name,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml','<Types/>');z.writestr('word/document.xml',f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
            if name=='image.docx':z.write(root/'person.png','word/media/image1.png')
    import openpyxl
    book=openpyxl.Workbook();sheet=book.active;sheet['A1']='ИНН: 7707083893';sheet['A2']='Телефон: +7 (999) 123-45-67'
    hidden=book.create_sheet('Hidden');hidden.sheet_state='hidden';hidden['A1']='ФИО: '+PERSON
    from openpyxl.comments import Comment
    hidden['A2'].comment=Comment('СНИЛС: 112-233-445 95','test')
    book.save(root/'hidden.xlsx')
    (root/'secret.txt').write_text('API_KEY: sk-proj-'+'AbC123dEf456'*5)
    (root/'corrupt.pdf').write_bytes(b'%PDF-broken')
    return root

@pytest.fixture(scope='module')
def files(tmp_path_factory):return corpus(tmp_path_factory.mktemp('corpus'))

@pytest.mark.parametrize('name,expected',[('person.png',PERSON),('phone.jpg','999'),('bank.tiff','044525225'),('english.webp','hello'),('scan.pdf','Соколов'),('mixed.pdf','112'),('text.pdf',PERSON),('last.pdf','Соколов'),('table.docx',PERSON),('image.docx',PERSON),('hidden.xlsx',PERSON),('secret.txt','sk-proj-')])
def test_supported(files,name,expected):
    result=extract(files/name,name.rsplit('.',1)[1])
    assert result['status']=='COMPLETE',result['reasons']
    assert expected in ' '.join(b['text'] for b in result['blocks'])
    if name=='bank.tiff':assert any('frame/2' in b['source'] for b in result['blocks'])
    if name=='last.pdf':assert any('page/2' in b['source'] for b in result['blocks'])

@pytest.mark.parametrize('name',['bad.png','corrupt.pdf'])
def test_fail_closed(files,name):assert extract(files/name,name.rsplit('.',1)[1])['status']=='REVIEW'

def test_zip_bomb_and_mismatch(files):
    p=files/'bomb.docx'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('big','a'*2_000_000)
    assert 'zip_bomb' in extract(p,'docx')['reasons']
    assert extract(files/'person.png','jpg')['status']=='REVIEW'
