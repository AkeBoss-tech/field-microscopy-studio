/* Python processing stays off the UI thread. Uploaded pixels never leave this worker. */
importScripts('https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.js');
let py,manifest=[];
const sync=populate=>new Promise((resolve,reject)=>py.FS.syncfs(populate,e=>e?reject(e):resolve()));
const progress=message=>postMessage({progress:message});
const ready=(async()=>{
 progress('Starting the image engine…');py=await loadPyodide({indexURL:'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/'});
 progress('Loading NumPy, SciPy and image processing…');await py.loadPackage(['numpy','scipy','scikit-image','pillow','micropip']);
 await py.runPythonAsync("import micropip\nawait micropip.install(['tifffile==2025.5.10','czifile==2019.7.2.2','roifile==2025.5.10'])");
 py.FS.mkdirTree('/app/starter');py.FS.mkdirTree('/store');py.FS.mount(py.FS.filesystems.IDBFS,{},'/store');await sync(true);
 for(const name of ['server.py','catalog.py','persistence.py','review.py','processing.py','experiments.py','measurements.py','corrections.py','external_results.py','trace_links.py','browser_adapter.py']){const r=await fetch('./python/'+name+self.location.search,{cache:'no-store'});if(!r.ok)throw Error('Missing engine file '+name);py.FS.writeFile('/app/'+name,await r.text())}
 manifest=await (await fetch('./starter/manifest.json')).json();
 for(const item of manifest){py.FS.writeFile('/app/starter/'+item.id+'.json',JSON.stringify(item))}
 await py.runPythonAsync("import os,sys\nos.environ.update(STUDIO_ROOT='/app',STUDIO_STORE='/store',STUDIO_UPLOAD_MB='100',STUDIO_MAX_VOXELS='200000000',STUDIO_PROCESS_VOXELS='8000000',STUDIO_LABEL_VOXELS='12000000',STUDIO_STORE_MB='1500')\nsys.path.insert(0,'/app')\nfrom browser_adapter import request");progress('Ready · images stay on this device');
})().catch(e=>{postMessage({fatal:String(e)});throw e});
let serial=Promise.resolve();
onmessage=({data})=>{
 serial=serial.catch(()=>{}).then(async()=>{
  try{
   await ready;
   // runtime.js holds the exclusive workspace lock for this tab.
    const url=new URL(data.path,'http://local'),q=url.searchParams;
    let key=q.get('dataset')||q.get('id');
    if(!key&&data.method==='POST'&&data.path!=='/api/workspace-restore'&&!data.path.startsWith('/api/import')&&!data.path.startsWith('/api/inspect')){
     try{key=JSON.parse(new TextDecoder().decode(data.body)).dataset}catch(e){}
    }
    const source=manifest.find(d=>d.id===key);
    if(source&&!py.FS.analyzePath('/app/'+source.path).exists){
     progress('Loading '+source.name+'…');const r=await fetch('./'+source.path);
     if(!r.ok)throw Error('Cannot load starter scan');
     py.FS.writeFile('/app/'+source.path,new Uint8Array(await r.arrayBuffer()));
     progress('Scan loaded · native pixels preserved');
    }
    py.globals.set('_path',data.path);py.globals.set('_method',data.method);
    py.globals.set('_body',new Uint8Array(data.body||0));
    const result=py.runPython("request(_path,_method,_body)");
    const r=result.toJs({dict_converter:Object.fromEntries});result.destroy();
    if(data.method==='POST'&&r.status<400){progress('Saving to browser storage…');await sync(false);progress('Saved on this device')}
    postMessage({id:data.id,...r},[r.data.buffer]);
  }catch(e){postMessage({id:data.id,status:500,type:'application/json',data:new TextEncoder().encode(JSON.stringify({error:String(e)}))})}
 });
};
