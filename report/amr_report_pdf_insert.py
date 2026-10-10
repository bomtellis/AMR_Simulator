"""Insert prepared report pages while reusing existing PDF pages and links."""
import io
import os
from pathlib import Path
import tempfile

from pypdf import PdfReader, PdfWriter


def validate_insertion(existing_pdf, output_pdf, insert_after_page=None):
    source, output = Path(existing_pdf).resolve(), Path(output_pdf).resolve()
    if source == output:
        raise ValueError('Save the combined report to a different PDF to preserve the original.')
    reader = PdfReader(source)
    if reader.is_encrypted:
        raise ValueError('Select an unencrypted existing PDF.')
    count = len(reader.pages)
    position = count if insert_after_page is None else insert_after_page
    if isinstance(position, bool) or not isinstance(position, int) or not 0 <= position <= count:
        raise ValueError(f'Insert after page must be between 0 and {count}; leave blank to append.')
    return position


def insert_pdf_sections(existing_pdf, sections_pdf, output_pdf, insert_after_page=None):
    """0 inserts before the first page; None appends. Source PDFs stay intact.

    Reports/supplements retain printed page numbers and contents links.
    No existing chart, drawing or table is rendered again.
    """
    position = validate_insertion(existing_pdf, output_pdf, insert_after_page)
    source, sections, output = map(Path, (existing_pdf, sections_pdf, output_pdf))
    if sections.resolve() == output.resolve():
        raise ValueError('The prepared sections PDF and output PDF must be different files.')
    original = PdfReader(io.BytesIO(source.read_bytes()))
    supplement = PdfReader(io.BytesIO(sections.read_bytes()))
    if supplement.is_encrypted:
        raise ValueError('Select an unencrypted sections PDF.')
    if not supplement.pages:
        raise ValueError('The sections PDF has no pages to insert.')
    writer = PdfWriter()
    writer.append(original, import_outline=True)
    writer.merge(position, supplement, outline_item='Inserted report sections', import_outline=True)
    if original.metadata:
        writer.add_metadata({str(k): str(v) for k, v in original.metadata.items() if v is not None})
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer.write(stream)
        verification = PdfReader(temporary)
        if len(verification.pages) != len(original.pages) + len(supplement.pages):
            raise ValueError('Combined report page count did not match the input PDFs.')
        os.replace(temporary, output)
    finally:
        writer.close()
        if temporary and temporary.exists():
            temporary.unlink()
    return output
