from pathlib import Path
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image, ImageOps, ImageDraw
from pypdf import PdfReader
import pypdfium2 as pdfium

folder = Path(__file__).parent / 'department_reviews'
qa = folder / 'previews'
ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
for book in folder.glob('*.xlsx'):
    with zipfile.ZipFile(book) as z:
        errors = []
        for name in z.namelist():
            if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                root = ET.fromstring(z.read(name))
                errors += [(name, cell.attrib['r'], cell.find('s:v', ns).text) for cell in root.findall('.//s:c[@t="e"]', ns)]
        assert not errors, errors
        root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        totals = [root.find(f'.//s:c[@r="{cell}"]/s:v', ns).text for cell in ['A7', 'D7']]
        pdf = PdfReader(book.with_suffix('.pdf'))
        text = pdf.pages[0].extract_text()
        assert f'{totals[0]} deliveries' in text and f'{totals[1]} collections' in text
        assert not any(term in z.read('xl/sharedStrings.xml').decode() for term in ['Website Analytics Dashboard', 'Monthly Recurring Revenue', 'Trial-to-Paid'])
        print(book.name, 'cached totals', totals, 'PDF pages', len(pdf.pages), flush=True)

def montage(images, output, thumb=(620, 410), cols=3):
    canvas = Image.new('RGB', (cols * thumb[0], math.ceil(len(images)/cols) * (thumb[1]+28)), '#c4cdd3')
    draw = ImageDraw.Draw(canvas)
    for i, (label, im) in enumerate(images):
        tile = ImageOps.contain(im.convert('RGB'), thumb)
        x, y = (i % cols) * thumb[0], (i // cols) * (thumb[1]+28)
        canvas.paste(tile, (x, y+28))
        draw.text((x+5, y+7), label, fill='black')
    canvas.save(output)

for category in ['catering', 'pharmacy', 'linen', 'waste', 'stores', 'ssd']:
    images = [(p.stem, Image.open(p)) for p in qa.glob(category + '_*.png') if '_pdf_' not in p.name]
    montage(images, qa / ('qa_workbook_' + category + '.png'))
    doc = pdfium.PdfDocument(str(folder / (category + '_department_review.pdf')))
    pages = []
    for i in range(len(doc)):
        page = doc[i]
        image = page.render(scale=0.8).to_pil()
        pages.append((f'{category} PDF page {i+1}', image))
    for start in range(0, len(pages), 12):
        montage(pages[start:start+12], qa / f'qa_pdf_{category}_{start//12+1}.png')

# Render representative final PDF pages at reading size.
for category in ['catering', 'waste']:
    reader = PdfReader(folder / (category + '_department_review.pdf'))
    indices = [0]
    for heading in ['Service timetable', 'Delivery and collection detail', 'Generation rules']:
        indices.append(next(i for i,p in enumerate(reader.pages) if heading in p.extract_text()))
    doc = pdfium.PdfDocument(str(folder / (category + '_department_review.pdf')))
    for i in indices:
        doc[i].render(scale=1.8).to_pil().save(qa / f'{category}_pdf_page_{i+1}.png')
