from wayback_seance.extract import decode_html, extract


def test_extract_title_text_meta_and_skips_scripts():
    page = extract(
        b"""<html><head><title> Old &amp; Gold </title><meta name="description" content="A  home"></head>
        <body><script>var x = 'nope';</script><h1>Hello there</h1><p>One two three four words.</p>
        <p>One two three four words.</p><img alt="logo"><style>p{}</style><div>|</div></body></html>"""
    )
    assert page.title == "Old & Gold"
    assert page.description == "A home"
    assert page.headings == ["Hello there"]
    assert "nope" not in page.text
    assert page.lines.count("One two three four words.") == 1
    assert "logo" in page.text
    assert not page.is_empty


def test_og_title_and_empty_page():
    page = extract('<meta property="og:title" content="Vine"><meta property="og:description" content="Loops">')
    assert page.title == "Vine" and page.description == "Loops"
    assert extract("<html><body></body></html>").is_empty


def test_excerpt_prefers_prose_and_trims():
    page = extract("<p>Home</p><p>" + "word " * 300 + "</p><p>A short sentence with words.</p>")
    ex = page.excerpt(100)
    assert ex.endswith("…") and len(ex) <= 102
    assert extract("<p>Home</p><p>About</p>").excerpt() == "Home / About"
    two = extract("<p>Alpha beta gamma delta.</p><p>Epsilon zeta eta theta.</p>")
    assert two.excerpt() == "Alpha beta gamma delta. / Epsilon zeta eta theta."
    assert two.excerpt(30) == "Alpha beta gamma delta."


def test_decode_html_charsets():
    assert decode_html('<meta charset="utf-8">café'.encode()) == '<meta charset="utf-8">café'
    assert decode_html(b"caf\xe9") == "café"  # cp1252 fallback
    assert "café" in decode_html('<meta charset="bogus-enc">café'.encode())


def test_binary_noise_counts_as_empty_but_accents_do_not():
    noise = bytes(range(128, 256)) * 4
    assert extract(b"<p>" + noise + b"</p>").is_empty
    assert not extract("<title>Café</title><p>Où est la bibliothèque? Très bien, merci.</p>").is_empty
    assert not extract("<title>Яндекс</title><p>Найдётся всё</p>").is_empty
