# Récupère les fiches et photos des villas publiées sur arconciergerie.com (sources des visuels).
import json, os, re, html, io, urllib.request
from PIL import Image
UA = {'User-Agent': 'Mozilla/5.0 (ArConciergerie publication)'}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r: return r.read()
OUT = 'out'; os.makedirs(OUT, exist_ok=True)
liste = get('https://arconciergerie.com/nos-villas/').decode('utf-8', 'replace')
liens = sorted(set(re.findall(r'https://arconciergerie\.com/villas/[a-z0-9\-]+/', liste)))
fiches = []
for u in liens:
    slug = u.rstrip('/').split('/')[-1]
    try: h = get(u).decode('utf-8', 'replace')
    except Exception as e: print('ERREUR', u, e); continue
    titre = html.unescape((re.search(r'<title>(.*?)</title>', h, re.S) or [None, slug])[1]).split('|')[0].split(' - ')[0].strip()
    corps = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S)
    texte = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', corps))).strip()
    imgs, vus = [], set()
    for m in re.findall(r'https://arconciergerie\.com/wp-content/uploads/[^"\'\s\)]+?\.(?:jpe?g|png|webp)', h, re.I):
        base = re.sub(r'-\d{2,4}x\d{2,4}(?=\.\w+$)', '', m); base = re.sub(r'-scaled(?=\.\w+$)', '', base)
        k = base.lower()
        if k in vus or 'logo' in k or 'icon' in k or 'favicon' in k: continue
        vus.add(k); imgs.append(base)
    d = os.path.join(OUT, slug); os.makedirs(d, exist_ok=True); n = 0
    for src in imgs:
        try:
            im = Image.open(io.BytesIO(get(src))).convert('RGB')
            if min(im.size) < 700: continue
            im.thumbnail((2000, 2000)); n += 1
            im.save(os.path.join(d, '%02d.jpg' % n), quality=86)
        except Exception as e:
            print('img', src, e)
        if n >= 25: break
    fiches.append({'slug': slug, 'url': u, 'titre': titre, 'photos': n, 'texte': texte[:6000]})
    print(slug, n, 'photos')
json.dump(fiches, open(os.path.join(OUT, 'villas.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
