import zipfile
import xml.etree.ElementTree as ET

def extract_text(path):
    z = zipfile.ZipFile(path)
    xml = z.read('word/document.xml')
    root = ET.fromstring(xml)
    text = []
    for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
        p_text = ''.join(node.text for node in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text)
        if p_text:
            text.append(p_text)
    return '\n'.join(text)

if __name__ == '__main__':
    with open('requirements.txt', 'w', encoding='utf-8') as f:
        f.write(extract_text('Desarrollo App Balonmano_ Hoja Ruta.docx'))
