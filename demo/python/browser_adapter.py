"""Reuse the real Python API inside a browser worker; no HTTP server or threads."""
import io,json,types,zipfile
import server as s
class InlinePool:
    def submit(self,fn,*args):fn(*args)
s.POOL=InlinePool()
class BrowserHandler(s.Handler):
    def send(self,obj,status=200,ctype='application/json'):
        self.result={'status':status,'type':ctype,'data':obj if isinstance(obj,bytes) else json.dumps(obj).encode()}
    def log_message(self,*args):pass

def request(path,method,body):
    h=object.__new__(BrowserHandler);h.path=path;h.server=types.SimpleNamespace(server_port=8777)
    raw=body.to_bytes() if hasattr(body,'to_bytes') else bytes(body)
    h.headers={'Host':'127.0.0.1:8777','X-Studio-Request':'1','Content-Length':str(len(raw))}
    h.rfile=io.BytesIO(raw)
    if path=='/api/config':
        h.send(dict(shared=False,browser=True,persistent=True,storage='this browser',upload_limit_mb=100))
    elif path=='/api/workspace-export':
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in s.STORE.rglob('*'):
                if p.is_file():archive.write(p,str(p.relative_to(s.STORE)))
        h.send(buf.getvalue(),ctype='application/zip')
    elif path=='/api/workspace-restore':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos=archive.infolist()
            if len(infos)>20000 or sum(i.file_size for i in infos)>1_500_000_000:raise ValueError('Backup exceeds browser limit')
            for info in infos:
                p=(s.STORE/info.filename).resolve()
                if not p.is_relative_to(s.STORE) or info.filename.split('/')[0] not in ['imports','annotations','runs','recipes']:raise ValueError('Invalid backup path')
            # Merge only into an empty workspace to avoid overwriting newer work.
            if any(s.STORE.glob('annotations/*/latest.json')) or any(s.STORE.glob('imports/*/dataset.json')) or any(s.STORE.glob('runs/*/run.json')) or any(s.STORE.glob('recipes/*.json')):raise ValueError('Restore requires an empty workspace. Keep this backup and use a fresh browser profile.')
            archive.extractall(s.STORE)
        h.send({'restored':True})
    elif method=='POST':h.do_POST()
    else:h.do_GET()
    return h.result
