# Robot LinkedIn ArConciergerie : connexion de la page, contrôle et publication (Community Management API)
# Publie sur la page LinkedIn les posts et Reels prévus pour Instagram/Facebook (pas les stories), avec le texte Facebook.
# Les jetons LinkedIn sont conservés chiffrés (clé = secret LINKEDIN_CLIENT_SECRET) dans .github/social/linkedin.enc
import json, os, re, sys, time, secrets, subprocess, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
CID, SECRET = os.environ.get('LINKEDIN_CLIENT_ID', '').strip(), os.environ.get('LINKEDIN_CLIENT_SECRET', '').strip()
os.environ['LINKEDIN_CLIENT_SECRET'] = SECRET
MODE = os.environ.get('MODE', 'publier')
BASE = 'https://alexisriccobene.github.io/arconciergerie-social/'
REDIRECT = BASE + 'linkedin.html'
SCOPES = 'w_organization_social r_organization_social rw_organization_admin'
ENC, ETAT, PLAN, DONE = '.github/social/linkedin.enc', '.github/social/linkedin_etat.json', '.github/social/plan.json', '.github/social/publie_linkedin.json'
IMG, VID = '.github/social/img/', '.github/social/videos/'
REST = 'https://api.linkedin.com/rest'
DEBUT = '2026-11-18T13:00'  # rien d'antérieur n'est publié sur LinkedIn

def versions():
    n = datetime.now(ZoneInfo('Europe/Paris')); y, m = n.year, n.month
    out = []
    for k in range(1, 12):  # versions mensuelles récentes (LinkedIn garde environ un an de versions)
        mm, yy = m - k, y
        while mm < 1: mm += 12; yy -= 1
        out.append('%d%02d' % (yy, mm))
    return out
VERSION = [None]

def http(method, url, body=None, token=None, headers=None, raw=False, form=False):
    h = dict(headers or {})
    if token: h['Authorization'] = 'Bearer ' + token
    if url.startswith(REST): h.setdefault('X-Restli-Protocol-Version', '2.0.0')
    data = None
    if form: data = urllib.parse.urlencode(body).encode(); h['Content-Type'] = 'application/x-www-form-urlencoded'
    elif raw: data = body
    elif body is not None: data = json.dumps(body).encode(); h['Content-Type'] = 'application/json'
    tries = versions() if url.startswith(REST) and not VERSION[0] else [VERSION[0]]
    last = None
    for v in tries:
        if url.startswith(REST): h['LinkedIn-Version'] = v
        r = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(r, timeout=300) as x:
                if url.startswith(REST): VERSION[0] = v
                txt = x.read(); return (json.loads(txt) if txt.strip() else {}), dict(x.headers)
        except urllib.error.HTTPError as e:
            msg = e.read()[:600].decode(errors='replace'); last = RuntimeError('LinkedIn %s %s : %s' % (e.code, url.split('?')[0].replace(REST, ''), msg))
            if url.startswith(REST) and (e.code == 426 or 'NONEXISTENT_VERSION' in msg or 'VERSION_MISSING' in msg): continue
            raise last
    raise last

def sauver(tok):
    subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-salt', '-a', '-A', '-pass', 'env:LINKEDIN_CLIENT_SECRET', '-out', ENC], input=json.dumps(tok).encode(), check=True)
def charger():
    p = subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-a', '-A', '-pass', 'env:LINKEDIN_CLIENT_SECRET', '-in', ENC], capture_output=True, check=True)
    return json.loads(p.stdout)

def jetons(r, ancien=None):
    if 'access_token' not in r: raise RuntimeError('LinkedIn n a pas délivré de jeton : ' + json.dumps(r)[:400])
    t = time.time(); a = ancien or {}
    return {'access_token': r['access_token'], 'access_expire': t + r.get('expires_in', 0) - 600,
            'refresh_token': r.get('refresh_token', a.get('refresh_token')),
            'refresh_expire': t + r['refresh_token_expires_in'] if r.get('refresh_token_expires_in') else a.get('refresh_expire'),
            'scope': r.get('scope', a.get('scope')), 'org': a.get('org')}

def acces():
    tok = charger()
    if time.time() > tok['access_expire'] and tok.get('refresh_token') and time.time() < (tok.get('refresh_expire') or 0):
        r, _ = http('POST', 'https://www.linkedin.com/oauth/v2/accessToken', {'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                    'client_id': CID, 'client_secret': SECRET}, form=True)
        tok = jetons(r, tok); sauver(tok)
    if time.time() > tok['access_expire']: raise RuntimeError('Connexion LinkedIn expirée : écrivez « reconnecter LinkedIn » à Claude.')
    return tok

def etat(extra):
    e = json.load(open(ETAT, encoding='utf-8')) if os.path.exists(ETAT) else {}
    e.update(extra); e['controle'] = datetime.now(ZoneInfo('Europe/Paris')).isoformat(timespec='minutes')
    json.dump(e, open(ETAT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def pages(tok):
    r, _ = http('GET', REST + '/organizationAcls?q=roleAssignee&role=ADMINISTRATOR&state=APPROVED', token=tok['access_token'])
    orgs = [x['organization'] for x in r.get('elements', [])]
    out = []
    for o in orgs:
        try:
            i, _ = http('GET', REST + '/organizations/' + o.split(':')[-1], token=tok['access_token'])
            out.append({'urn': o, 'nom': i.get('localizedName'), 'page': i.get('vanityName')})
        except Exception as e: out.append({'urn': o, 'nom': '?', 'erreur': str(e)[:200]})
    return out

def choisir(lst):
    for p in lst:
        if re.sub(r'\W', '', (p.get('nom') or '') + (p.get('page') or '')).lower().find('arconciergerie') >= 0: return p['urn']
    return lst[0]['urn'] if len(lst) == 1 else None

if not CID or not SECRET:
    print('::warning::LinkedIn non configuré (secrets LINKEDIN_CLIENT_ID et LINKEDIN_CLIENT_SECRET manquants)'); sys.exit(0)

if MODE == 'page':
    url = 'https://www.linkedin.com/oauth/v2/authorization?' + urllib.parse.urlencode({'response_type': 'code', 'client_id': CID,
          'redirect_uri': REDIRECT, 'state': secrets.token_hex(8), 'scope': SCOPES})
    tpl = open('docs/connexion-linkedin.tpl.html', encoding='utf-8').read().replace('{{URL}}', url)
    open('docs/connexion-linkedin.html', 'w', encoding='utf-8').write(tpl); print('page de connexion LinkedIn générée'); sys.exit(0)

if MODE == 'jeton':
    code = urllib.parse.unquote(os.environ.get('LINKEDIN_CODE', '').strip())
    if not code: print('::error::code LinkedIn vide'); sys.exit(1)
    try:
        r, _ = http('POST', 'https://www.linkedin.com/oauth/v2/accessToken', {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT,
                    'client_id': CID, 'client_secret': SECRET}, form=True)
        tok = jetons(r); lst = pages(tok); tok['org'] = choisir(lst); sauver(tok)
        f = lambda t: datetime.fromtimestamp(t, ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y') if t else 'non communiqué'
        etat({'connexion': 'OK', 'pages_administrees': lst, 'page_utilisee': tok['org'], 'scopes': tok.get('scope'), 'version_api': VERSION[0],
              'jeton_valable_jusqu_au': f(tok['access_expire']), 'reconnexion_avant': f(tok.get('refresh_expire') or tok['access_expire'])})
        print('::notice::LinkedIn connecté : %s' % tok['org'])
        if not tok['org']: print('::error::aucune page ArConciergerie trouvée parmi les pages administrées'); sys.exit(1)
    except Exception as e:
        etat({'connexion': 'échec : ' + str(e)[:400]}); print('::error::' + str(e)[:600]); sys.exit(1)
    sys.exit(0)

if not os.path.exists(ENC): print('LinkedIn pas encore connecté'); sys.exit(0)
tok = acces(); ORG = tok.get('org')

def texte(t):
    # Format « little text » de LinkedIn : caractères réservés échappés, hashtags convertis
    out = []
    for mot in re.split(r'(#[\wÀ-ÿ]+)', t):
        if re.fullmatch(r'#[\wÀ-ÿ]+', mot): out.append('{hashtag|\\#|%s}' % mot[1:]); continue
        out.append(re.sub(r'([\\|{}@\[\]()<>#*_~])', r'\\\1', mot))
    return ''.join(out)

def image(fn):
    r, _ = http('POST', REST + '/images?action=initializeUpload', {'initializeUploadRequest': {'owner': ORG}}, tok['access_token'])
    v = r['value']; data = open(IMG + fn, 'rb').read()
    up = urllib.request.Request(v['uploadUrl'], data=data, method='PUT', headers={'Authorization': 'Bearer ' + tok['access_token'], 'Content-Type': 'application/octet-stream'})
    try: urllib.request.urlopen(up, timeout=300).read()
    except urllib.error.HTTPError as e: raise RuntimeError('LinkedIn envoi image %s : %s' % (e.code, e.read()[:300]))
    return v['image']

def attendre(urn, kind):
    for _ in range(60):
        r, _ = http('GET', REST + '/%s/%s' % (kind, urllib.parse.quote(urn, safe='')), token=tok['access_token'])
        if r.get('status') == 'AVAILABLE': return
        if r.get('status') in ('PROCESSING_FAILED',): raise RuntimeError('LinkedIn a refusé le média ' + urn)
        time.sleep(5)

def video(fn):
    f = VID + fn; n = os.path.getsize(f)
    r, _ = http('POST', REST + '/videos?action=initializeUpload', {'initializeUploadRequest': {'owner': ORG, 'fileSizeBytes': n, 'uploadCaptions': False, 'uploadThumbnail': False}}, tok['access_token'])
    v = r['value']; etags = []
    with open(f, 'rb') as fh:
        for part in v['uploadInstructions']:
            fh.seek(part['firstByte']); chunk = fh.read(part['lastByte'] - part['firstByte'] + 1)
            up = urllib.request.Request(part['uploadUrl'], data=chunk, method='PUT', headers={'Content-Type': 'application/octet-stream'})
            with urllib.request.urlopen(up, timeout=300) as x: etags.append(x.headers.get('ETag'))
    http('POST', REST + '/videos?action=finalizeUpload', {'finalizeUploadRequest': {'video': v['video'], 'uploadToken': v.get('uploadToken', ''), 'uploadedPartIds': etags}}, tok['access_token'])
    attendre(v['video'], 'videos'); return v['video']

def publier(p):
    t = texte(p.get('texte_facebook') or p.get('texte_instagram') or '')
    if p.get('type') == 'reel': content = {'media': {'id': video(p['video']), 'title': p.get('theme', 'ArConciergerie')[:200]}}
    else:
        ids = [image(f) for f in p['images'][:20]]
        content = {'media': {'id': ids[0]}} if len(ids) == 1 else {'multiImage': {'images': [{'id': i, 'altText': p.get('theme', '')[:120]} for i in ids]}}
    body = {'author': ORG, 'commentary': t, 'visibility': 'PUBLIC', 'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False,
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []}, 'content': content}
    _, h = http('POST', REST + '/posts', body, tok['access_token'])
    return {k.lower(): v for k, v in h.items()}.get('x-restli-id') or 'publié'

def a_publier(p):
    return p.get('type') in ('post', 'reel') and ('instagram' in p.get('reseaux', []) or 'facebook' in p.get('reseaux', [])) and p['date'] >= DEBUT

if MODE == 'verifier':
    lst = pages(tok)
    if not ORG and choisir(lst): tok['org'] = ORG = choisir(lst); sauver(tok)
    f = lambda t: datetime.fromtimestamp(t, ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y') if t else 'non communiqué'
    etat({'connexion': 'OK', 'pages_administrees': lst, 'page_utilisee': ORG, 'version_api': VERSION[0],
          'jeton_valable_jusqu_au': f(tok['access_expire']), 'reconnexion_avant': f(tok.get('refresh_expire') or tok['access_expire']),
          'posts_prevus': sum(1 for p in json.load(open(PLAN, encoding='utf-8')) if a_publier(p))})
    essai = os.environ.get('LINKEDIN_TEST')
    if essai:
        p = next(x for x in json.load(open(PLAN, encoding='utf-8')) if x['id'] == essai)
        try: etat({'essai ' + essai: publier(p)})
        except Exception as e: etat({'essai ' + essai: 'échec : ' + str(e)[:500]})
    sys.exit(0)

plan = json.load(open(PLAN, encoding='utf-8')); done = json.load(open(DONE, encoding='utf-8')) if os.path.exists(DONE) else {}
now = datetime.now(ZoneInfo('Europe/Paris')); changed = False; errors = []
for p in plan:
    if not a_publier(p): continue
    when = datetime.fromisoformat(p['date']).replace(tzinfo=ZoneInfo('Europe/Paris'))
    if when > now or (now - when).total_seconds() > 20 * 3600: continue
    d = done.setdefault(p['id'], {})
    if d.get('linkedin') or d.get('linkedin_echecs', 0) >= 2: continue
    try:
        d['linkedin'] = publier(p); changed = True; print('::notice::%s publié sur LinkedIn (%s)' % (p['id'], d['linkedin']))
    except Exception as e:
        d['linkedin_echecs'] = d.get('linkedin_echecs', 0) + 1; changed = True; errors.append('%s : %s' % (p['id'], e)); print('::error::' + str(e)[:600])
if changed: json.dump(done, open(DONE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
fin = tok.get('refresh_expire') or tok['access_expire']
if time.time() > fin - 10 * 86400: errors.append('La connexion LinkedIn expire dans moins de 10 jours : écrivez « reconnecter LinkedIn » à Claude.')
if errors:
    print('\n'.join(errors)); sys.exit(1)
