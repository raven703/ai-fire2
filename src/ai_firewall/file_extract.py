"""Bounded local document extraction. Run only inside the OCR sandbox process."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import warnings
import zipfile

MAX_PIXELS=16_000_000
MAX_PARTS=2000
MAX_TEXT=6000  # leaves room for native JSON exact-row admission
MAX_PAGES=20


class Incomplete(Exception):
    pass


def extract(path,extension):
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    from defusedxml import ElementTree as ET
    Image.MAX_IMAGE_PIXELS=MAX_PIXELS
    warnings.simplefilter('error',Image.DecompressionBombWarning)
    blocks=[];reasons=[];pixels=0;ocr_pages=0
    def add(text,source,**metadata):
        text=text.strip()
        if not text:return
        if sum(len(b['text']) for b in blocks)+len(text)>MAX_TEXT:raise Incomplete('text_limit')
        blocks.append(dict(text=text,source=source,**metadata))
    def ocr(image,source):
        nonlocal pixels,ocr_pages
        ocr_pages+=1
        if ocr_pages>MAX_PAGES:raise Incomplete('page_limit')
        if image.width*image.height>MAX_PIXELS:raise Incomplete('pixel_limit')
        pixels+=image.width*image.height
        if pixels>100_000_000:raise Incomplete('total_pixel_limit')
        image=ImageOps.exif_transpose(image).convert('RGB')
        candidates=[]
        with tempfile.TemporaryDirectory(dir='/tmp') as directory:
            # OSD is best effort; uncertain non-upright text remains REVIEW.
            image.save(directory+'/osd.png')
            orientation=subprocess.run(['tesseract',directory+'/osd.png','stdout','--psm','0'],capture_output=True,timeout=8)
            import re
            rotation=re.search(rb'Rotate: (90|180|270)',orientation.stdout)
            if rotation:image=image.rotate(-int(rotation[1]),expand=True)
            gray=ImageOps.grayscale(image)
            prepared=ImageEnhance.Contrast(ImageOps.autocontrast(gray,cutoff=0)).enhance(1.15)
            prepared=prepared.filter(ImageFilter.MedianFilter(3))
            for index,variant in enumerate((image,prepared)):
                filename=f'{directory}/{index}.png';variant.save(filename)
                result=subprocess.run(['tesseract',filename,'stdout','-l','rus+eng','--psm','11','tsv'],capture_output=True,timeout=18,check=True)
                words=[]
                for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8')),delimiter='\t'):
                    if row.get('text','').strip() and float(row['conf'])>=0:
                        words.append(dict(text=row['text'],confidence=float(row['conf']),bbox=[int(row[k]) for k in ('left','top','width','height')]))
                confidence=sum(w['confidence'] for w in words)/len(words) if words else 0
                candidates.append((words,confidence))
        if not any(words for words,_ in candidates):reasons.append('empty_ocr');return
        # Inspect both variants: never discard a lower-confidence candidate that
        # might contain an identifier missed by the supposedly better variant.
        seen=set()
        for index,(words,confidence) in enumerate(candidates):
            text=' '.join(w['text'] for w in words)
            if not text or text in seen:continue
            seen.add(text)
            add(text,source,method='ocr',confidence=confidence,variant='original' if index==0 else 'prepared',words=words,status='recognized')
        best=max(candidates,key=lambda item:item[1])
        if best[1]<65 or sum(w['confidence']<35 for w in best[0])>max(1,len(best[0])//5):reasons.append('low_ocr_confidence')
    def images(data,source):
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {'PNG','JPEG','TIFF','WEBP'}:raise Incomplete('unsupported_image')
            count=getattr(image,'n_frames',1)
            if count>MAX_PAGES:raise Incomplete('frame_limit')
            for frame in range(count):
                image.seek(frame);ocr(image.copy(),f'{source}/frame/{frame+1}')
    data=Path(path).read_bytes()
    try:
        if extension=='txt':
            if b'\0' in data:raise Incomplete('binary_text')
            add(data.decode('utf-8-sig'),'text',method='text',status='extracted')
        elif extension=='pdf':
            import pymupdf as fitz
            if not data.startswith(b'%PDF-'):raise Incomplete('format_mismatch')
            with fitz.open(path) as doc:
                if doc.needs_pass or not 1<=len(doc)<=MAX_PAGES:raise Incomplete('encrypted_or_page_limit')
                if doc.embfile_count():reasons.append('embedded_files')
                for i,page in enumerate(doc):
                    if list(page.widgets() or []):reasons.append('pdf_forms')
                    text=page.get_text('text',sort=True)
                    add(text,f'page/{i+1}/text',method='text',status='extracted')
                    width,height=page.rect.width*200/72,page.rect.height*200/72
                    if width*height>MAX_PIXELS:raise Incomplete('pdf_pixel_limit')
                    # Full-page OCR also covers mixed image/text and vector text.
                    pix=page.get_pixmap(dpi=200,alpha=False)
                    ocr(Image.frombytes('RGB',[pix.width,pix.height],pix.samples),f'page/{i+1}/render')
        elif extension in {'png','jpg','jpeg','tif','tiff','webp'}:
            with Image.open(io.BytesIO(data)) as check:
                expected={'png':'PNG','jpg':'JPEG','jpeg':'JPEG','tif':'TIFF','tiff':'TIFF','webp':'WEBP'}[extension]
                if check.format!=expected:raise Incomplete('format_mismatch')
            images(data,'image')
        elif extension in {'docx','xlsx'}:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos=archive.infolist()
                if len(infos)>MAX_PARTS or len({i.filename for i in infos})!=len(infos):raise Incomplete('zip_parts_limit')
                if sum(i.file_size for i in infos)>40_000_000:raise Incomplete('zip_size_limit')
                for item in infos:
                    if item.flag_bits&1 or item.file_size>12_000_000 or item.file_size>max(1,item.compress_size)*200:raise Incomplete('zip_bomb')
                    if '..' in Path(item.filename).parts or item.filename.startswith('/'):raise Incomplete('zip_path')
                names=archive.namelist();prefix='word/' if extension=='docx' else 'xl/'
                if '[Content_Types].xml' not in names or (prefix+('document.xml' if extension=='docx' else 'workbook.xml')) not in names:raise Incomplete('format_mismatch')
                for name in names:
                    if any(part.lower() in name.lower() for part in ('vbaproject','activex','embeddings/','externallinks/','customxml/')):reasons.append('unsupported_active_or_embedded_part')
                    if name.endswith('.rels'):
                        root=ET.fromstring(archive.read(name))
                        if any(e.attrib.get('TargetMode')=='External' for e in root):reasons.append('external_relationship')
                    if name.startswith(prefix+'media/'):
                        images(archive.read(name),name)
                if any(n.startswith(('word/charts/','word/diagrams/','xl/diagrams/','xl/pivot','xl/connections')) for n in names):reasons.append('unsupported_complex_part')
                if extension=='docx':
                    for name in names:
                        if name.startswith('word/') and name.endswith('.xml'):
                            root=ET.fromstring(archive.read(name))
                            paragraphs=[]
                            for node in root.iter():
                                local=node.tag.rsplit('}',1)[-1]
                                if local in {'p','comment'}:
                                    value=' '.join(e.text or '' for e in node.iter() if e.tag.rsplit('}',1)[-1]=='t')
                                    if value:paragraphs.append(value)
                            all_text=' '.join(e.text or '' for e in root.iter() if e.tag.rsplit('}',1)[-1] in {'t','delText'})
                            add(all_text,name,method='xml',status='extracted')
                            if any(e.tag.rsplit('}',1)[-1] in {'altChunk','object','OLEObject','chart','instrText'} for e in root.iter()):reasons.append('unsupported_docx_part')
                else:
                    import openpyxl
                    book=openpyxl.load_workbook(io.BytesIO(data),read_only=False,data_only=False,keep_links=False)
                    cached=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True,keep_links=False)
                    if len(book.worksheets)>20:raise Incomplete('sheet_limit')
                    cells=0
                    for sheet in book:
                        if sheet.max_row*sheet.max_column>20000:raise Incomplete('cell_limit')
                        values=[]
                        for row in sheet:
                            for cell in row:
                                cells+=1
                                if cells>20000:raise Incomplete('cell_limit')
                                if cell.value is not None:values.append(str(cell.value))
                                if cell.data_type=='f':
                                    value=cached[sheet.title][cell.coordinate].value
                                    if value is not None:values.append(str(value))
                                if cell.comment:values.append(cell.comment.text)
                        add('\n'.join(values),'sheet/'+sheet.title,method='cells',status='extracted')
                    for name in names:
                        if name.startswith(('xl/charts/','xl/drawings/')) and name.endswith('.xml'):
                            root=ET.fromstring(archive.read(name))
                            add(' '.join(e.text or '' for e in root.iter() if e.tag.rsplit('}',1)[-1] in {'t','v'}),name,method='xml',status='extracted')
        else:raise Incomplete('unsupported_format')
    except Incomplete as exc:reasons.append(str(exc))
    except Exception:reasons.append('extraction_failed')
    # Exact duplicate text across text-layer/OCR is admitted once; provenance remains.
    seen=set();unique=[]
    for block in blocks:
        key=' '.join(block['text'].split()).casefold()
        if key not in seen:unique.append(block);seen.add(key)
    if not unique:reasons.append('no_readable_text')
    return dict(blocks=unique,reasons=sorted(set(reasons)),status='REVIEW' if reasons else 'COMPLETE')


if __name__=='__main__':
    # Deny networking even if a parser accidentally attempts an external fetch.
    import ctypes
    lib=ctypes.CDLL('libseccomp.so.2');lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    lib.seccomp_load.argtypes=[ctypes.c_void_p]
    lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    ctx=lib.seccomp_init(0x7fff0000)
    if not ctx:raise SystemExit(1)
    for syscall in (b'socket',b'connect',b'socketpair'):
        if lib.seccomp_rule_add(ctx,0x00050001,lib.seccomp_syscall_resolve_name(syscall),0)!=0:raise SystemExit(1)
    if lib.seccomp_load(ctx)!=0:raise SystemExit(1)
    result=extract(sys.argv[1],sys.argv[2]);sys.stdout.write(json.dumps(result,ensure_ascii=False))
