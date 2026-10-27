# Récupère les images des publications Instagram existantes du compte (photos des services).
import json, os, io, re, urllib.request, urllib.parse
from PIL import Image
G='https://graph.facebook.com/v26.0'; T=os.environ['META_PAGE_TOKEN']; PAGE=os.environ['FB_PAGE_ID']
def api(path, **q):
    q['access_token']=T
    return json.loads(urllib.request.urlopen(G+path+'?'+urllib.parse.urlencode(q), timeout=60).read())
ig=api('/'+PAGE, fields='instagram_business_account')['instagram_business_account']['id']
os.makedirs('out', exist_ok=True); index=[]
r=api('/%s/media'%ig, fields='caption,timestamp,media_type,media_url,thumbnail_url,children{media_type,media_url,thumbnail_url}', limit=100)
for m in r.get('data', []):
    cap=(m.get('caption') or '').strip(); t=re.sub(r'[^a-z0-9]+','-',(cap.split('\n')[0] or 'post').lower())[:50].strip('-')
    d=os.path.join('out', m['timestamp'][:10]+'-'+t); os.makedirs(d, exist_ok=True)
    kids=m.get('children',{}).get('data') or [m]; n=0
    for k in kids:
        u=k.get('media_url') if k.get('media_type')!='VIDEO' else k.get('thumbnail_url')
        if not u: continue
        try:
            im=Image.open(io.BytesIO(urllib.request.urlopen(u, timeout=60).read())).convert('RGB'); n+=1
            im.save(os.path.join(d,'%02d.jpg'%n), quality=90)
        except Exception as e: print('img', e)
    index.append({'dossier': os.path.basename(d), 'images': n, 'texte': cap[:1500]}); print(d, n)
json.dump(index, open('out/index.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
