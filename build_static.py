from pathlib import Path
import shutil,json,hashlib,re
root=Path(__file__).parent;demo=root/'demo';demo.mkdir(exist_ok=True)
for file in (root/'app/web').glob('*'):shutil.copy2(file,demo/file.name)
text=(demo/'index.html').read_text().replace('href="/','href="./').replace('src="/','src="./').replace('<script src="./app.js">','<script src="./runtime.js"></script><script src="./app.js">')
(demo/'index.html').write_text(text)
shutil.copytree(root/'starter',demo/'starter',dirs_exist_ok=True)
(demo/'python').mkdir(exist_ok=True)
for name in ['server.py','catalog.py','persistence.py']:shutil.copy2(root/'app'/name,demo/'python'/name)
shutil.copy2(root/'browser_adapter.py',demo/'python/browser_adapter.py')
with (demo/'studio.css').open('a') as f:f.write('\n#boot{position:fixed;inset:0;z-index:1000;background:radial-gradient(ellipse at 50% 30%,#243b36,#11171e 65%);display:grid;place-items:center;text-align:center}#boot h1{font-weight:400;font-size:32px;letter-spacing:-.04em}#boot p{color:#a8c0ba;line-height:1.8;font-size:13px}.boot-mark{font-size:60px;color:#9cdcc1}header{flex-wrap:wrap;height:auto;min-height:68px}header button{font-size:10px}\n')

manifest=[json.loads(p.read_text()) for p in (root/"starter").glob("*.json") if p.name!="manifest.json"]
(demo/"starter/manifest.json").write_text(json.dumps(manifest,indent=2))

# Keep the UI, worker and Python engine on the same published revision.
assets=sorted((root/'app/web').glob('*'))+sorted((demo/'python').glob('*.py'))+[demo/'runtime.js',demo/'worker.js']
revision=hashlib.sha256(b''.join(p.read_bytes() for p in assets)).hexdigest()[:12]
index=demo/'index.html'
index.write_text(re.sub(r'((?:src|href)="\./[^"?]+\.(?:js|css))"',lambda m:m[1]+'?v='+revision+'"',index.read_text()))
