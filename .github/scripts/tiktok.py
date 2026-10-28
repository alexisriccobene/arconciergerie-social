# Robot TikTok ArConciergerie : connexion du compte, contrôle et publication (Content Posting API)
# Les jetons TikTok sont conservés chiffrés (clé = secret TIKTOK_CLIENT_SECRET) dans .github/social/tiktok.enc
import json, os, sys, time, secrets, subprocess, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
KEY, SECRET = os.environ.get('TIKTOK_CLIENT_KEY', '').strip(), os.environ.get('TIKTOK_CLIENT_SECRET', '').strip()
os.environ['TIKTOK_CLIENT_SECRET'] = SECRET  # sans espace parasite copié par erreur
MODE = os.environ.get('MODE', 'publier')
BASE = 'https://alexisriccobene.github.io/arconciergerie-social/'
REDIRECT = BASE + 'tiktok.html'
ENC, ETAT, PLAN, DONE = '.github/social/tiktok.enc', '.github/social/tiktok_etat.json', '.github/social/plan.json', '.github/social/publie.json'
API = 'https://open.tiktokapis.com/v2'

def req(url, data=None, token=None, js=False):
    h = {}
    if token: h['Authorization'] = 'Bearer ' + token
    if js: h['Content-Type'] = 'application/json; charset=UTF-8'; body = json.dumps(data).encode()
    elif data is not None: h['Content-Type'] = 'application/x-www-form-urlencoded'; body = urllib.parse.urlencode(data).encode()
    else: body = None
    r = urllib.request.Request(url, data=body, headers=h, method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(r, timeout=120) as x: return json.loads(x.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError('TikTok %s %s : %s' % (e.code, url.split('?')[0].replace(API, ''), e.read()[:500].decode(errors='replace')))

def sauver(tok):
    p = subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-salt', '-a', '-A', '-pass', 'env:TIKTOK_CLIENT_SECRET', '-out', ENC],
                       input=json.dumps(tok).encode(), check=True)
def charger():
    p = subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-a', '-A', '-pass', 'env:TIKTOK_CLIENT_SECRET', '-in', ENC], capture_output=True, check=True)
    return json.loads(p.stdout)

def jetons(r):
    if 'access_token' not in r: raise RuntimeError('TikTok n a pas délivré de jeton : ' + json.dumps(r)[:400])
    t = time.time()
    return {'access_token': r['access_token'], 'refresh_token': r['refresh_token'], 'open_id': r.get('open_id'), 'scope': r.get('scope'),
            'access_expire': t + r.get('expires_in', 0) - 300, 'refresh_expire': t + r.get('refresh_expires_in', 0)}

def acces():
    tok = charger()
    if time.time() > tok['access_expire']:
        tok = jetons(req(API + '/oauth/token/', {'client_key': KEY, 'client_secret': SECRET, 'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token']}))
        sauver(tok)
    return tok

def etat(extra):
    e = json.load(open(ETAT, encoding='utf-8')) if os.path.exists(ETAT) else {}
    e.update(extra); e['controle'] = datetime.now(ZoneInfo('Europe/Paris')).isoformat(timespec='minutes')
    json.dump(e, open(ETAT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def createur(tok):
    return req(API + '/post/publish/creator_info/query/', {}, tok['access_token'], js=True).get('data', {})

if not KEY or not SECRET:
    print('::warning::TikTok non configuré (secrets TIKTOK_CLIENT_KEY et TIKTOK_CLIENT_SECRET manquants)'); sys.exit(0)

if MODE == 'page':
    # Page de connexion : le lien d'autorisation contient la clé publique de l'application (client key), jamais le secret
    url = 'https://www.tiktok.com/v2/auth/authorize/?' + urllib.parse.urlencode({'client_key': KEY, 'scope': 'user.info.basic,video.upload,video.publish',
          'response_type': 'code', 'redirect_uri': REDIRECT, 'state': secrets.token_hex(8)})
    tpl = open('docs/connexion.tpl.html', encoding='utf-8').read().replace('{{URL}}', url)
    open('docs/connexion.html', 'w', encoding='utf-8').write(tpl); print('page de connexion générée'); sys.exit(0)

if MODE == 'jeton':
    code = os.environ.get('TIKTOK_CODE', '').strip()
    if not code: print('::error::secret TIKTOK_CODE vide'); sys.exit(1)
    try:
        tok = jetons(req(API + '/oauth/token/', {'client_key': KEY, 'client_secret': SECRET, 'code': urllib.parse.unquote(code),
                                                 'grant_type': 'authorization_code', 'redirect_uri': REDIRECT}))
        sauver(tok)
        u = req(API + '/user/info/?fields=open_id,display_name', token=tok['access_token']).get('data', {}).get('user', {})
        c = createur(tok)
        etat({'connexion': 'OK', 'compte': c.get('creator_username'), 'nom': u.get('display_name') or c.get('creator_nickname'), 'scopes': tok.get('scope'),
              'confidentialite_possible': c.get('privacy_level_options'), 'duree_video_max_s': c.get('max_video_post_duration_sec'),
              'reconnexion_avant': datetime.fromtimestamp(tok['refresh_expire'], ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y')})
        print('::notice::TikTok connecté : @%s' % c.get('creator_username'))
    except Exception as e:
        etat({'connexion': 'échec : ' + str(e)[:400]}); print('::error::' + str(e)[:600]); sys.exit(1)
    sys.exit(0)

if not os.path.exists(ENC): print('TikTok pas encore connecté'); sys.exit(0)
tok = acces()

def publier_video(p):
    c = createur(tok)
    priv = 'PUBLIC_TO_EVERYONE' if os.path.exists('.github/social/tiktok_public') and 'PUBLIC_TO_EVERYONE' in c.get('privacy_level_options', []) else 'SELF_ONLY'  # privé tant que l'application n'est pas validée par TikTok
    info = {'title': p['texte_tiktok'][:2200], 'privacy_level': priv, 'disable_comment': False, 'disable_duet': False, 'disable_stitch': False,
            'video_cover_timestamp_ms': p.get('vignette_ms', 1000), 'brand_content_toggle': False, 'brand_organic_toggle': True}
    r = req(API + '/post/publish/video/init/', {'post_info': info, 'source_info': {'source': 'PULL_FROM_URL', 'video_url': BASE + 'm/' + p['video']}}, tok['access_token'], js=True)
    pid = r['data']['publish_id']
    for _ in range(60):
        s = req(API + '/post/publish/status/fetch/', {'publish_id': pid}, tok['access_token'], js=True).get('data', {})
        if s.get('status') == 'PUBLISH_COMPLETE': return {'id': pid, 'confidentialite': priv}
        if s.get('status') == 'FAILED': raise RuntimeError('TikTok a refusé la vidéo : ' + str(s.get('fail_reason')))
        time.sleep(10)
    return {'id': pid, 'confidentialite': priv, 'statut': 'en cours'}

def publier_photos(p):
    c = createur(tok)
    priv = 'PUBLIC_TO_EVERYONE' if os.path.exists('.github/social/tiktok_public') and 'PUBLIC_TO_EVERYONE' in c.get('privacy_level_options', []) else 'SELF_ONLY'  # privé tant que l'application n'est pas validée par TikTok
    info = {'title': p.get('titre_tiktok', '')[:90], 'description': p['texte_tiktok'][:4000], 'privacy_level': priv, 'disable_comment': False, 'auto_add_music': True,
            'brand_content_toggle': False, 'brand_organic_toggle': True}
    src = {'source': 'PULL_FROM_URL', 'photo_cover_index': 0, 'photo_images': [BASE + 'm/' + f for f in p['images_tiktok']]}
    r = req(API + '/post/publish/content/init/', {'post_info': info, 'source_info': src, 'post_mode': 'DIRECT_POST', 'media_type': 'PHOTO'}, tok['access_token'], js=True)
    return {'id': r['data']['publish_id'], 'confidentialite': priv}

if MODE == 'verifier':
    c = createur(tok); etat({'connexion': 'OK', 'compte': c.get('creator_username'), 'confidentialite_possible': c.get('privacy_level_options')})
    if os.environ.get('TIKTOK_TEST'):  # essai de publication demandé
        p = next(x for x in json.load(open(PLAN, encoding='utf-8')) if x['id'] == os.environ['TIKTOK_TEST'])
        etat({'essai ' + p['id']: publier_video(p) if p.get('type') == 'reel' else publier_photos(p)})
    sys.exit(0)

# Publication des contenus TikTok arrivés à échéance
plan = json.load(open(PLAN, encoding='utf-8')); done = json.load(open(DONE, encoding='utf-8')) if os.path.exists(DONE) else {}
now = datetime.now(ZoneInfo('Europe/Paris')); changed = False; errors = []
for p in plan:
    if 'tiktok' not in p.get('reseaux', []): continue
    when = datetime.fromisoformat(p['date']).replace(tzinfo=ZoneInfo('Europe/Paris'))
    if when > now or (now - when).total_seconds() > 20 * 3600: continue
    d = done.setdefault(p['id'], {})
    if d.get('tiktok') or d.get('tiktok_echecs', 0) >= 2: continue
    try:
        d['tiktok'] = publier_video(p) if p.get('type') == 'reel' else publier_photos(p); changed = True
        print('::notice::%s publié sur TikTok' % p['id'])
    except Exception as e:
        d['tiktok_echecs'] = d.get('tiktok_echecs', 0) + 1; changed = True; errors.append('%s : %s' % (p['id'], e)); print('::error::' + str(e)[:600])
if changed: json.dump(done, open(DONE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if time.time() > charger()['refresh_expire'] - 15 * 86400: errors.append('La connexion TikTok expire dans moins de 15 jours : écrivez « reconnecter TikTok » à Claude.')
if errors:
    print('\n'.join(errors)); sys.exit(1)
