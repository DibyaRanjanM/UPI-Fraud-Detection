import sys, os
try:
    import PyPDF2
    with open('Project-6.pdf', 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        with open('pdf_content.txt', 'w', encoding='utf-8') as out:
            for page in reader.pages:
                out.write(page.extract_text() + '\n')
except Exception as e:
    print("Error:", e)
