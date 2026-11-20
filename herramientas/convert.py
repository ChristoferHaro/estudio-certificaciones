#!/usr/bin/env python3
"""Conversor: Word de preguntas de certificación -> paquete JSON para la app.

Uso: python convert.py examen.docx --id dp-700 --out site/data/dp700 [--media-url data/dp700/media]
Requiere pandoc. Salida: questions.json + media/ + informe de calidad (report.txt).
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile
from collections import Counter
from difflib import SequenceMatcher
from urllib.parse import unquote

ap = argparse.ArgumentParser()
ap.add_argument('docx'); ap.add_argument('--id', default='dp-700')
ap.add_argument('--out', required=True); ap.add_argument('--media-url', default=None)
a = ap.parse_args()
OUT = a.out; MEDIA_URL = a.media_url or (OUT.split('site/')[-1] + '/media')
os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp()
md_path = os.path.join(tmp, 'ex.md')
subprocess.run(['pandoc', a.docx, '-t', 'gfm', '--wrap=none', f'--extract-media={tmp}/media', '-o', md_path], check=True)
text = open(md_path, encoding='utf-8').read()
shutil.rmtree(os.path.join(OUT, 'media'), ignore_errors=True)
shutil.copytree(os.path.join(tmp, 'media', 'media'), os.path.join(OUT, 'media'))
problems = []

def md2html(md):
    md = fix_links(md)
    md = re.sub(r'<img src="[^"]*?media/media/([^"]+)"[^>]*/>', lambda m: f'<img src="{MEDIA_URL}/{m.group(1)}" loading="lazy" alt="Imagen de la pregunta">', md)
    h = subprocess.run(['pandoc', '-f', 'gfm', '-t', 'html', '--wrap=none'], input=md, capture_output=True, text=True).stdout
    h = re.sub(r'<li>(\s*<p>)?(\s*<strong>Documentaci)', lambda m: '<li class="docref">' + (m.group(1) or '') + m.group(2), h)
    h = h.replace('<a href=', '<a target="_blank" rel="noopener" href=')
    return h.strip()

GOOG = re.compile(r'https?://(?:www\.)?google\.com/search\?q=(https?://[^\s)\]]+)')
UTM = re.compile(r'[?&]utm_[a-z]+=[^&#)\]\s]*')
def fix_links(md):
    md = GOOG.sub(lambda m: unquote(m.group(1)), md)
    return UTM.sub('', md)

def plain(md):
    s = re.sub(r'<[^>]+>', ' ', md); s = re.sub(r'[*_`>#\[\]()]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip().lower()

HDR = re.compile(r'^([^\n.]{3,40})\.\s+(.{2,80}?)\s*[-–—]\s*$')
parts = re.split(r'(?m)^# (?=Pregunta \d)', text)[1:]
cases, questions, firstgroups = {}, [], Counter()
TABS = ['Resumen', 'Entorno existente', 'Problemas', 'Requisitos']

def parse_case(blocks):
    """Devuelve (intro_blocks, tabs{tab:[html-md]}, indice_fin_caso)"""
    idx = [i for i, b in enumerate(blocks) if HDR.match(b.split('\n')[0].strip())]
    if not idx: return None
    last = idx[-1]
    end = last + 1                      # cabecera + su bloque de cuerpo
    intro = blocks[:idx[0]]
    tabs, cur = {}, None
    for b in blocks[idx[0]:end + 1]:
        m = HDR.match(b.split('\n')[0].strip())
        if m:
            g, sub = m.group(1).strip(), m.group(2).strip()
            firstgroups[g] += 1
            cur = 'Problemas' if sub.lower().startswith('problema') else g
            tabs.setdefault(cur, []).append(f'**{sub}**')
        else:
            tabs.setdefault(cur, []).append(b)
    return intro, tabs, end + 1

TOPICS = [
 ('Seguridad y permisos', r'permiso|\brol\b|roles|row-level|\brls\b|\bcls\b|\bols\b|seguridad|enmascar|confidencialidad|private link|identidad|acceso a|compartir'),
 ('Control de versiones y despliegue', r'\bgit\b|devops|deployment pipeline|control de versiones|repositorio|ci/cd|despliegue|\brama\b|branch|variable library'),
 ('Ingesta y orquestación', r'data pipeline|copiar datos|copy data|dataflow|flujo de datos|mirror|espejo|shortcut|acceso directo|ingest|orquest|programa|activador|foreach|conexión|gateway'),
 ('Spark y notebooks', r'spark|notebook|pyspark|delta|v-order|vacuum|optimize|alta concurrencia|livy|\bpool\b|lakehouse'),
 ('T-SQL y Warehouse', r'warehouse|t-sql|sql endpoint|endpoint sql|\bmerge\b|\bctas\b|stored procedure|procedimiento almacenado|dimensi|scd'),
 ('Streaming y KQL', r'eventstream|eventhouse|\bkql\b|kusto|streaming|tiempo real|event hub|reflex|activator|ventana'),
 ('Monitorización y rendimiento', r'monitor|capacidad|capacity|métrica|alerta|rendimiento|caché|cache|latencia|log analytics|\bcu\b|optimizar'),
]
def topic_of(s):
    s = s.lower(); best, bn = 'General', 0
    for name, rx in TOPICS:
        n = len(re.findall(rx, s))
        if n > bn: best, bn = name, n
    return best

for p in parts:
    title, _, body = p.partition('\n')
    m = re.match(r'Pregunta (\d+)(.*)', title.strip())
    n = int(m.group(1)); rest = m.group(2)
    repeat = 'epetida' in rest.lower()
    cm = re.search(r'Caso de estudio\s*[–-]\s*(.+?)\)', rest)
    cname = cm.group(1).strip().replace('Innc.', 'Inc.') if cm else None
    q_md, _, ans_md = body.partition('\n## Respuesta')
    blocks = [b.strip() for b in re.split(r'\n\s*\n', q_md.strip()) if b.strip()]
    qid = f'q{n:03d}'
    case_key = None
    if cname:
        pc = parse_case(blocks)
        if pc:
            intro, tabs, stem_start = pc
            sig = hashlib.md5(json.dumps(tabs, sort_keys=True).encode()).hexdigest()[:6]
            case_key = re.sub(r'\W+', '-', cname.lower()).strip('-') + '-' + sig
            if case_key not in cases:
                order = [t for t in TABS if t in tabs] + [t for t in tabs if t not in TABS]
                cases[case_key] = {'name': cname, 'intro': md2html('\n\n'.join(intro[1:])) if len(intro) > 1 else '',
                                   'tabs': [{'title': t, 'html': md2html('\n\n'.join(tabs[t]))} for t in order]}
            blocks = blocks[stem_start:]
        else:
            problems.append(f'{qid}: marcada como caso de estudio pero no se detectó el caso')
    # opciones = bloques numerados finales
    opts, i = [], len(blocks)
    while i > 0 and re.match(r'^\d+\.\s', blocks[i - 1]):
        i -= 1
    for b in blocks[i:]:
        for it in re.split(r'(?m)^\d+\.\s+', b)[1:]:
            opts.append(re.sub(r'\s+', ' ', it).strip())
    stem_blocks = blocks[:i]
    stem_md = '\n\n'.join(stem_blocks)
    visual = (len(opts) < 2) or bool(re.search(r'ARRASTRAR|HOTSPOT|arrastra|Para responder, ', stem_md))
    if len(opts) < 2: opts = []
    # respuesta
    ans_md = ans_md.strip()
    correct = []
    hm = re.search(r'\*\*Respuestas?\s+(?:correctas?|a buscar)[^*\n]*\*\*:?', ans_md)
    if hm and not visual:
        sec = ans_md[hm.end():].lstrip().split('\n\n**')[0]
        for line in sec.split('\n'):
            line = line.strip()
            if not (line.startswith('-') or line.startswith('**Opci')): continue
            line = '-' + line.lstrip('-') if not line.startswith('-') else line
            label = re.sub(r'\*', '', line[1:]).split(':')[0]
            found = re.findall(r'\b([A-H])\b', label)
            for L in found: correct.append(ord(L) - 65)
            if not found and ':' in re.sub(r'\*', '', line):
                cand = plain(re.sub(r'\*', '', line[1:]).split(':', 1)[1])
                for k, o in enumerate(opts):
                    if cand and (plain(o) == cand or cand.startswith(plain(o) + ' ') or plain(o).startswith(cand) or (len(plain(o)) > 2 and re.search(r'\b' + re.escape(plain(o)) + r'\b', cand))): correct.append(k); break
        correct = sorted(set(c for c in correct if c < len(opts)))
    if visual:
        a_html, inc_html = md2html(ans_md), ''
    else:
        sm = re.search(r'(?m)^\*\*(?:Opciones incorrectas|Análisis detallado de la[s]? opci[oó]n(?:es)? incorrecta|Por qué las demás|Por qué las otras|Por qué las opciones|Por qué los demás|Opciones descartadas)', ans_md)
        if sm: a_html, inc_html = md2html(ans_md[:sm.start()]), md2html(ans_md[sm.start():])
        else: a_html, inc_html = md2html(ans_md), ''
    links = [{'t': re.sub('<[^>]+>', '', t), 'u': u} for u, t in re.findall(r'href="(https?://[^"]+)"[^>]*>(.*?)</a>', a_html + inc_html)]
    for l in links:
        if not l['u'].startswith('https://learn.microsoft.com/'): problems.append(f'{qid}: enlace no oficial/raro: {l["u"][:90]}')
    if not links: problems.append(f'{qid}: respuesta sin enlaces oficiales')
    if not visual and not correct: problems.append(f'{qid}: no se pudo detectar la respuesta correcta')
    if not visual and not inc_html: problems.append(f'{qid}: sin sección de opciones incorrectas separada')
    typ = 'visual' if visual else ('multi' if len(correct) > 1 else 'single')
    stem_html = md2html(stem_md)
    opt_html = [re.sub(r'`([^`]+)`', r'<code>\1</code>', o.replace('<', '&lt;')) for o in opts]
    questions.append({'id': qid, 'n': n, 'case': case_key, 'repeat': repeat, 'group': None, 'repeatOf': None, 'conflict': None,
                      'type': typ, 'topic': topic_of(plain(stem_md) + ' ' + ' '.join(opts) + ' ' + plain(ans_md[:600])),
                      'stem': stem_html, 'options': opt_html, 'correct': correct,
                      'answer': {'correct': a_html, 'incorrect': inc_html}, 'links': links,
                      '_sig': plain(stem_md) + ' | ' + ' | '.join(plain(o) for o in opts),
                      '_ctext': sorted(plain(opts[c]) for c in correct)})

# --- unificar variantes casi idénticas de un mismo caso ---
cnt = Counter(q['case'] for q in questions if q['case'])
def ctext(k): return plain(' '.join(t['html'] for t in cases[k]['tabs']))
remap = {}
for name in {c['name'] for c in cases.values()}:
    keys = sorted([k for k in cases if cases[k]['name'] == name], key=lambda k: -cnt[k])
    canon = keys[0]
    for k in keys[1:]:
        r = SequenceMatcher(None, ctext(canon), ctext(k)).quick_ratio()
        problems.append(f'caso {name}: variante {k} vs {canon}: similitud {r:.3f} ' + ('(unificada)' if r >= 0.97 else '(se mantiene aparte)'))
        if r >= 0.97: remap[k] = canon
for q in questions:
    if q['case'] in remap: q['case'] = remap[q['case']]
for k in remap: cases.pop(k)

# --- grupos de repetidas ---
def toks(s): return set(re.findall(r'\w{3,}', s))
T = {q['id']: toks(q['_sig']) for q in questions}
gcount = 0
for q in questions:
    if not q['repeat']: continue
    best, bs = None, 0
    for o in questions:
        if o['id'] == q['id']: continue
        s = len(T[q['id']] & T[o['id']]) / max(1, len(T[q['id']] | T[o['id']]))
        if s > bs: best, bs = o, s
    if best and bs >= 0.5:
        g = best['group'] or q['group'] or f'g{(gcount := gcount + 1):02d}'
        best['group'] = g; q['group'] = g; q['repeatOf'] = best['id']
        if q['type'] != 'visual' and best['type'] != 'visual':
            q['conflict'] = best['conflict'] = (q['_ctext'] != best['_ctext'])
    else:
        problems.append(f'{q["id"]}: marcada como repetida pero no se encontró el original (similitud {bs:.2f})')
for q in questions: q.pop('_sig'); q.pop('_ctext')

pack = {'id': a.id, 'name': 'Microsoft Fabric DP-700', 'subtitle': 'Data Engineer Associate',
        'source': os.path.basename(a.docx), 'cases': cases, 'questions': questions}
json.dump(pack, open(os.path.join(OUT, 'questions.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
ty = Counter(q['type'] for q in questions)
rep = [f'Preguntas: {len(questions)} {dict(ty)}', f'Casos de estudio distintos: {len(cases)}  ({sum(1 for q in questions if q["case"])} preguntas con caso)',
       f'Repetidas: {sum(q["repeat"] for q in questions)}  grupos: {gcount}  con respuesta distinta: {sum(1 for q in questions if q["conflict"] and q["repeat"])}',
       f'Primeras partes de cabecera de caso: {dict(firstgroups)}', f'Temas: {dict(Counter(q["topic"] for q in questions))}',
       f'Enlaces: {sum(len(q["links"]) for q in questions)}  | Problemas: {len(problems)}'] + problems
open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(rep))
print('\n'.join(rep[:6])); print('\n'.join(problems[:60]))
