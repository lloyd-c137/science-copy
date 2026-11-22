"""Optional, bounded PDF text extraction with explicit physical-page locations."""

MAX_PAGES = 200


def extract(raw, max_bytes):
    try:
        import pymupdf
    except ImportError:
        return None, 'PDF正文未解析：请安装 requirements-pdf.txt 中的 PyMuPDF', {'format': 'pdf', 'complete': False}

    metadata = {'format': 'pdf', 'complete': False, 'pages': [], 'unparsed_pages': []}
    try:
        with pymupdf.open(stream=raw, filetype='pdf') as pdf:
            metadata['total_pages'] = len(pdf)
            if pdf.needs_pass:
                return None, 'PDF已加密，未读取正文', metadata
            chunks = []
            used = 0
            chars = 0
            line = 1
            has_text = False
            limited = len(pdf) > MAX_PAGES
            for number in range(min(len(pdf), MAX_PAGES)):
                text = pdf[number].get_text('text', sort=True).replace('\x00', '').strip()
                page_has_text = bool(text)
                if not page_has_text:
                    text = '（本页无可提取文字；图片、扫描内容未解析）'
                chunk = f'【PDF 第 {number + 1} 页】\n{text}\n\n'
                encoded = chunk.encode('utf-8')
                if used + len(encoded) > max_bytes:
                    limited = True
                    break  # Do not present a partial page as a complete citation.
                has_text = has_text or page_has_text
                if not page_has_text:
                    metadata['unparsed_pages'].append(number + 1)
                metadata['pages'].append({'page': number + 1, 'start_offset': chars,
                    'end_offset': chars + len(chunk), 'start_line': line,
                    'end_line': line + chunk.count('\n') - 1,
                    'text_extracted': number + 1 not in metadata['unparsed_pages']})
                chunks.append(chunk)
                used += len(encoded)
                chars += len(chunk)
                line += chunk.count('\n')
            metadata['processed_pages'] = len(chunks)
            metadata['extraction_limited'] = limited
            metadata['complete'] = not limited and not metadata['unparsed_pages']
            coverage = f'PDF文字层，已提取页范围1–{len(chunks)}，共{len(pdf)}页；不含图片、图形、批注或OCR，页码为文件物理页码'
            if metadata['unparsed_pages']:
                coverage += '；无文字/扫描页未解析：' + '、'.join(map(str, metadata['unparsed_pages']))
            if limited:
                coverage += f'；达到提取上限（{MAX_PAGES}页或{max_bytes // 1024}KiB正文），后续页未读取'
            if not has_text or not chunks:
                return None, 'PDF未取得可读取正文；' + coverage, metadata
            return ''.join(chunks), coverage, metadata
    except Exception:
        # Malformed or unsupported documents must not break a project search.
        return None, 'PDF正文解析失败，未读取；请提供可打开的文本型PDF', metadata
