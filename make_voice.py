"""把「數字住哪裡？」要念的話用 edge-tts 錄好，打包成 voice_<id>_core.json / voice_<id>_num.json。
用法：python make_voice.py C   （或 A）
句子清單從 index.html 的 <script id="phr"> 讀，數字與組合句在這裡產生（規則要和頁面 segText 一致）。
"""
import asyncio, base64, json, re, subprocess, sys, tempfile, os
import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
VOICES = {
    'C': dict(voice='zh-CN-XiaoyiNeural', rate='-5%', pitch='+0Hz'),
    'A': dict(voice='zh-TW-HsiaoChenNeural', rate='-5%', pitch='+8Hz'),
}
ZH = '零一二三四五六七八九'
PLACE = ['個位', '十位', '百位']

def zh(n):
    if n == 0: return '零'
    h, t, o = n // 100, n // 10 % 10, n % 10
    s = ''
    if h: s += ZH[h] + '百'
    if t: s += ('' if (t == 1 and not h) else ZH[t]) + '十'
    elif h and o: s += '零'
    if o: s += ZH[o]
    return s

def cnt(n): return '兩' if n == 2 else zh(n)

def segments():
    html = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
    phr = json.loads(re.search(r'<script type="application/json" id="phr">(.*?)</script>', html, re.S).group(1))
    core = dict(phr)
    for c in range(20):
        for suf in ['捆', '根', '個百', '個十', '個一']:
            core[f'k{suf}{c}'] = cnt(c) + suf
    for c in range(10):
        core[f'h百{c}'] = f'百位放{cnt(c)}片'
        core[f'h十{c}'] = f'十位放{cnt(c)}條'
        core[f'h個{c}'] = f'個位放{cnt(c)}個'
    for d in range(1, 10):
        for p in range(3):
            core[f'd{d}_{p}'] = f'{ZH[d]}，住在{PLACE[p]}，是'
    num = {f'n{n}': zh(n) for n in range(1000)}
    return core, num

def trim(mp3: bytes) -> bytes:
    af = ('silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.03,areverse,'
          'silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.06,areverse')
    r = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', 'pipe:0', '-af', af, '-ac', '1', '-ar', '22050',
                        '-b:a', '32k', '-f', 'mp3', 'pipe:1'], input=mp3, capture_output=True)
    if r.returncode or not r.stdout: raise RuntimeError(r.stderr.decode(errors='ignore'))
    return r.stdout

async def one(key, text, cfg, sem, out):
    async with sem:
        for attempt in range(5):
            try:
                buf = b''
                com = edge_tts.Communicate(text, cfg['voice'], rate=cfg['rate'], pitch=cfg['pitch'])
                async for ch in com.stream():
                    if ch['type'] == 'audio': buf += ch['data']
                out[key] = base64.b64encode(await asyncio.to_thread(trim, buf)).decode()
                return
            except Exception as e:
                await asyncio.sleep(1.5 * (attempt + 1))
        print('失敗', key, text, flush=True)

async def main(vid):
    cfg = VOICES[vid]
    core, num = segments()
    for name, items in (('core', core), ('num', num)):
        path = os.path.join(HERE, f'voice_{vid}_{name}.json')
        old = {}
        if os.path.exists(path):
            old = json.load(open(path, encoding='utf-8'))
        out = {k: v for k, v in old.items() if k in items}
        todo = {k: t for k, t in items.items() if k not in out}
        sem = asyncio.Semaphore(8)
        print(vid, name, '要錄', len(todo), '段', flush=True)
        await asyncio.gather(*(one(k, t, cfg, sem, out) for k, t in todo.items()))
        json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        print(vid, name, '完成', len(out), '/', len(items), os.path.getsize(path) // 1024, 'KB', flush=True)

if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
