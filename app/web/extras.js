'use strict';
// Workflow helpers: manual reference counts, clipboard copy, shareable view links, turntable video,
// keyboard help, a short guided tour and auto-preview. All are display/workflow features; none edit data.

// ---- Manual reference counts (lab workbook) ----
const referenceCache=new Map();
async function referenceCounts(){
 const ref=state.meta?.reference_counts;if(!ref)return null;
 if(!referenceCache.has(ref.file))referenceCache.set(ref.file,fetch(ref.file).then(r=>r.ok?r.json():null).catch(()=>null));
 const doc=await referenceCache.get(ref.file);const row=doc?.counts.find(c=>c.image===ref.image&&c.group===ref.group);
 return row?{...row,source:doc.source,legend:doc.legend}:null;
}
function runPopulation(r){const text=((r?.title||'')+' '+(r?.target||'')).toLowerCase();return /\bihc\b|inner hair/.test(text)?'IHC':/\bohc\b|outer hair/.test(text)?'OHC':'all'}
function referenceCard(row,observed,population){
 const card=expNode('section','reference-card');
 const head=expNode('div','reference-head');head.append(expNode('span','reference-kicker','Manual reference'),expNode('span','reference-source',row.source.file+' · '+row.group.replace('PLPCreER-GAP-','')+' '+row.image));card.append(head);
 const grid=expNode('div','reference-grid');
 const cell=(label,value,detail,active)=>{const c=expNode('div','reference-cell'+(active?' active':''));c.append(expNode('span','reference-label',label),expNode('strong','',String(value)));if(detail)c.append(expNode('span','reference-detail',detail));grid.append(c)};
 cell('IHC',row.IHC,'',population==='IHC');
 cell('OHC',row.total_OHC,`rows ${row.OHC1} / ${row.OHC2} / ${row.OHC3}`+(row.OHC4?` / ${row.OHC4} (row 4)`:''),population==='OHC');
 cell('All hair cells',row.IHC+row.total_OHC,'',population==='all');
 card.append(grid);
 if(observed!==null&&observed!==undefined){
  const expected=population==='IHC'?row.IHC:population==='OHC'?row.total_OHC:row.IHC+row.total_OHC,diff=observed-expected;
  const verdict=expNode('p','reference-verdict '+(diff===0?'match':Math.abs(diff)<=Math.max(2,expected*.03)?'close':'off'));
  verdict.textContent=`This run: ${observed} candidates vs ${expected} manual ${population==='all'?'hair cells':population}`+(diff===0?' · same total':` · ${diff>0?'+':''}${diff}`)+'. A matching total does not mean the same cells were found.';
  card.append(verdict);
 }
 card.append(expNode('p','reference-fine',`Manual counts from the lab workbook ${row.source.file}. ${row.legend.OHC4}. ${row.legend.rules}.`));
 return card;
}
{const extrasLoadMeasurements=loadMeasurements;loadMeasurements=async function(){
 await extrasLoadMeasurements();
 const host=measurementState.host;if(!host?.isConnected)return;host.querySelector('.reference-card')?.remove();
 const row=await referenceCounts();if(!row||!host.isConnected)return;
 const r=runMeta(),observed=measurementState.data?.total??null;
 host.querySelector('.measurement-heading')?.after(referenceCard(row,observed,runPopulation(r)));
}}
// The example card states how its counts compare with the lab's.
{const extrasCatalog=resultCatalog;resultCatalog=function(){extrasCatalog();const card=document.querySelector('.example-card');if(!card)return;
 referenceCounts().then(row=>{if(!row||!card.isConnected||card.querySelector('.example-reference'))return;
  const p=expNode('p','example-reference');p.innerHTML=`Lab manual count: <b>${row.IHC}</b> IHC · <b>${row.total_OHC}</b> OHC<br>This example: <b>21</b> IHC · <b>69</b> OHC (2 fewer OHC, at the image edges)`;card.querySelector('.example-fine').before(p)})}}

// ---- View tools: copy image, copy link, record spin ----
function currentCanvas(){const canvases=[...document.querySelectorAll('#main-host .viewport canvas')];return canvases[canvases.length-1]}
function railButton(icon,label,title,onclick){const b=document.createElement('button');b.className='explore-tool-button';b.innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+icon+'"/></svg><span class="explore-tool-label">'+label+'</span>';b.dataset.tip=label;b.setAttribute('aria-label',label);b.title=title;b.onclick=onclick;return b}
const copyImageButton=railButton('M8 8h11v11H8zM5 15V5h10','Copy image','Copy the current view to the clipboard for PowerPoint or Word',async()=>{
 const canvas=currentCanvas();if(!canvas)return status('Open an image view first',true);
 try{const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);status('View copied · paste into PowerPoint, Word or Slides')}
 catch(error){status('Clipboard unavailable in this browser · use Save view instead',true)}});
const shareButton=railButton('M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1','Copy link','Copy a link that reopens this exact view: image, mode, channel, cell and camera',async()=>{
 const url=location.origin+location.pathname+'#view='+encodeView();
 try{await navigator.clipboard.writeText(url);status('Link copied · it reopens this view (runs and annotations must exist in the viewer’s browser)')}catch{prompt('Copy this link',url)}});
const recordButton=railButton('M4 7h11v10H4zM15 10l5-3v10l-5-3','Record spin','Record one full turn of the 3D view as a video',()=>recordSpin());
{const save=document.querySelector('.tool-rail .save-view');save?.after(copyImageButton,shareButton,recordButton)}
{const extrasLayout=renderLayout;renderLayout=function(){extrasLayout();recordButton.hidden=state.mode!=='volume';applyPendingView()}}

async function recordSpin(){
 const v=$('#main-host .viewport[data-kind="volume"]'),canvas=v?.querySelector('canvas');if(!canvas)return;
 if(!canvas.captureStream||!window.MediaRecorder)return status('Video recording is unavailable in this browser',true);
 stopTurntable();recordButton.disabled=true;
 const type=['video/mp4;codecs=avc1','video/webm;codecs=vp9','video/webm'].find(t=>MediaRecorder.isTypeSupported(t))||'video/webm';
 const stream=canvas.captureStream(30),recorder=new MediaRecorder(stream,{mimeType:type,videoBitsPerSecond:8e6}),chunks=[];
 recorder.ondataavailable=e=>e.data.size&&chunks.push(e.data);
 const done=new Promise(resolve=>recorder.onstop=resolve);recorder.start();
 const cam=v.camera,start=cam.yaw,frames=150;
 for(let i=1;i<=frames;i++){cam.yaw=(start+360*i/frames)%360;status(`Recording spin · ${Math.round(100*i/frames)}%`);await draw(v);await new Promise(r=>requestAnimationFrame(r))}
 recorder.stop();await done;stream.getTracks().forEach(t=>t.stop());
 const blob=new Blob(chunks,{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`field-${state.dataset}-spin.${type.includes('mp4')?'mp4':'webm'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
 recordButton.disabled=false;status('Spin video saved');
}

// ---- Shareable view state in the URL hash ----
function encodeView(){
 const cam=$('#main-host .viewport')?.camera;
 const view={d:state.dataset,t:state.tab,m:state.mode,c:state.channel,r:state.run||undefined,f:state.focusObject?.id,n:state.focusObject?state.focusView:undefined,z:state.z,g:state.region3d||undefined,
  cam:cam?[Math.round(cam.yaw*10)/10,Math.round(cam.pitch*1000)/1000,Math.round(cam.zoom*100)/100]:undefined,rd:state.mode==='volume'?state.render:undefined};
 return btoa(unescape(encodeURIComponent(JSON.stringify(view)))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
let pendingView=null;
try{const m=location.hash.match(/view=([\w-]+)/);if(m)pendingView=JSON.parse(decodeURIComponent(escape(atob(m[1].replace(/-/g,'+').replace(/_/g,'/')))))}catch{pendingView=null}
let applyingView=false;
async function applyPendingView(){
 if(!pendingView||applyingView||!state.meta)return;applyingView=true;const view=pendingView;pendingView=null;
 try{
  if(view.d&&view.d!==state.dataset&&[...$('#dataset').options].some(o=>o.value===view.d)){$('#dataset').value=view.d;await selectDataset(view.d)}
  if(view.r&&!state.runs.some(r=>r.id===view.r))status('This link names a run that is not in this browser; showing the source image',true);
  else if(view.r)chooseResult(view.r);
  if(view.rd)Object.assign(state.render,view.rd);
  state.channel=view.c??state.channel;$('#channel').value=state.channel;state.mode=view.m||state.mode;state.tab=view.t||'Explore';state.region3d=view.g||null;
  if(Number.isInteger(view.z))setDepth(view.z);
  if(view.f&&state.run){if(view.n)state.focusView={...state.focusView,...view.n};state.focusObject={run:state.run,id:view.f}}
  renderLayout();
  if(view.cam)requestAnimationFrame(()=>{const cam=$('#main-host .viewport')?.camera;if(cam){[cam.yaw,cam.pitch,cam.zoom]=view.cam;scheduleDraw()}});
  status('Opened shared view');
 }catch(error){status('Could not open the shared view: '+error.message,true)}
 finally{applyingView=false}
}

// ---- Keyboard help ("?") ----
const shortcutGroups=[
 ['Navigate',[['Drag','Pan (2D) · orbit (3D)'],['Scroll / pinch','Zoom'],['Shift + scroll','Move through Z planes'],['Double-click','Fit the image'],['Space + drag','Pan while a drawing tool is active']]],
 ['Annotate',[['P','Point'],['O','Outline'],['B','Freehand outline'],['L','Neurite trace'],['S','Select and edit vertices'],['Enter','Finish drawing'],['Escape','Discard unfinished drawing'],['⌘/Ctrl + Z','Undo · add Shift to redo']]],
 ['Review',[['Click a plane','Move the crosshair'],['Arrow keys','Nudge the crosshair in the focused plane']]],
 ['This sheet',[['?','Show or hide keyboard help']]]];
function openShortcuts(){
 const existing=document.querySelector('.shortcut-dialog');if(existing){existing.close();return}
 const d=expModal('Keyboard & mouse','Shortcuts available in the studio.','shortcut-dialog');const grid=expNode('div','shortcut-grid');
 for(const [title,rows] of shortcutGroups){const s=expNode('section');s.append(expNode('h3','',title));for(const [key,what] of rows){const r=expNode('div','shortcut-row');r.append(expNode('kbd','',key),expNode('span','',what));s.append(r)}grid.append(s)}
 d.append(grid);
}
document.addEventListener('keydown',e=>{if(e.key==='?'&&!e.target.closest('input,textarea,select,[contenteditable]')){e.preventDefault();openShortcuts()}});

// ---- Guided tour ----
const tourSteps=[
 ['header nav.workspace-tabs','Four workspaces','Explore views the image, Process prepares intensity and labels or measures signal, Review checks candidates, and Annotate draws your own marks.'],
 ['#dataset','Choose an image','Two real scans are included. Add your own TIFF or CZI with Add image.'],
 ['#simple-toolbar .mode-buttons','Projection, slices or 3D','Average projection is the default. 2D slices shows one acquired plane; 3D renders the whole stack.'],
 ['#simple-toolbar .channels-menu','Channels & contrast','Toggle channels, change colours, and drag the histogram markers to set brightness and contrast.'],
 ['.tool-rail','View tools','Ruler, grid, scale bar, 3D region, Save view, Copy image, Copy link and Record spin.'],
 ['#result-list','Results & examples','Runs appear here. On the hair-cell scan, Load example shows what a correct IHC/OHC segmentation looks like.']];
function startTour(i=0){
 document.querySelector('.tour-layer')?.remove();if(i>=tourSteps.length){try{localStorage.setItem('field-tour-done','1')}catch{}return}
 const [selector,title,text]=tourSteps[i],target=document.querySelector(selector);if(!target||!target.offsetWidth)return startTour(i+1);
 if(state.tab!=='Explore'&&i>=2){state.tab='Explore';renderLayout()}
 const r=target.getBoundingClientRect(),layer=expNode('div','tour-layer'),spot=expNode('div','tour-spot'),card=expNode('div','tour-card');
 Object.assign(spot.style,{left:r.left-6+'px',top:r.top-6+'px',width:r.width+12+'px',height:r.height+12+'px'});
 card.append(expNode('span','tour-step',`${i+1} of ${tourSteps.length}`),expNode('h3','',title),expNode('p','',text));
 const actions=expNode('div','tour-actions');actions.append(expButton('Skip','',()=>startTour(tourSteps.length)));if(i)actions.append(expButton('Back','',()=>startTour(i-1)));actions.append(expButton(i===tourSteps.length-1?'Done':'Next','primary-action',()=>startTour(i+1)));card.append(actions);
 layer.append(spot,card);document.body.append(layer);
 const below=r.bottom+16+170<innerHeight,left=Math.max(12,Math.min(innerWidth-332,r.left+r.width/2-160));
 Object.assign(card.style,{left:left+'px',top:(below?r.bottom+16:Math.max(12,r.top-16-card.offsetHeight))+'px'});
 card.querySelector('.primary-action').focus();layer.addEventListener('keydown',e=>{if(e.key==='Escape')startTour(tourSteps.length);if(e.key==='ArrowRight')startTour(i+1);if(e.key==='ArrowLeft'&&i)startTour(i-1)});
}
{const menu=document.querySelector('.workspace-menu .dropdown-body');if(menu){menu.append(expButton('Take the tour','',()=>{menu.closest('details').open=false;startTour()}),expButton('Keyboard shortcuts  ?','',()=>{menu.closest('details').open=false;openShortcuts()}))}
 let seen=false;try{seen=localStorage.getItem('field-tour-done')==='1'}catch{}
 if(!seen&&!pendingView){const wait=setInterval(()=>{if(state.meta&&document.querySelector('#main-host .viewport')){clearInterval(wait);setTimeout(()=>startTour(),900)}},400);setTimeout(()=>clearInterval(wait),20000)}}

// ---- Process: optional auto-preview after settings change ----
state.autoPreview=(()=>{try{return localStorage.getItem('field-auto-preview')==='1'}catch{return false}})();
let autoPreviewTimer=null;
function attachAutoPreview(){
 const actions=$('#task-panel .experiment-actions');if(!actions||actions.querySelector('.auto-preview'))return;
 const label=expNode('label','auto-preview');const box=document.createElement('input');box.type='checkbox';box.checked=state.autoPreview;
 box.onchange=()=>{state.autoPreview=box.checked;try{localStorage.setItem('field-auto-preview',box.checked?'1':'0')}catch{}};
 label.append(box,document.createTextNode(' Auto-preview after changes'));label.title='Re-run the crop preview about a second after a setting changes';actions.append(label);
}
document.addEventListener('change',e=>{
 if(!state.autoPreview||state.tab!=='Process'||!e.target.closest?.('.experiment-settings,.algo-overview'))return;
 clearTimeout(autoPreviewTimer);autoPreviewTimer=setTimeout(()=>{if(!experiment.busy&&state.tab==='Process')runPreview().catch(()=>{})},900);
});
document.addEventListener('click',e=>{if(state.autoPreview&&state.tab==='Process'&&e.target.closest?.('.algo-card')){clearTimeout(autoPreviewTimer);autoPreviewTimer=setTimeout(()=>{if(!experiment.busy)runPreview().catch(()=>{})},900)}});
new MutationObserver(()=>{if(state.tab==='Process')attachAutoPreview()}).observe($('#task-panel'),{childList:true,subtree:true});

// ---- High-resolution export with an info strip and PNG metadata ----
const exportPrefs=(()=>{try{return {scale:2,caption:true,...JSON.parse(localStorage.getItem('field-export')||'{}')}}catch{return {scale:2,caption:true}}})();
function saveExportPrefs(){try{localStorage.setItem('field-export',JSON.stringify(exportPrefs))}catch{}}
function viewMetadata(scale){
 const r=runMeta(),meta=state.meta,channels=displayChannels(),settings=channelSettings(),cam=$('#main-host .viewport')?.camera,v=$('#main-host .viewport');
 const modeName=state.mode==='volume'?'3D · '+(renderModes.find(([k])=>k===state.render.mode)?.[1]||state.render.mode)+' · '+(state.render.quality==='precise'?'Precise':'Fast'):state.mode==='slice'?'Single acquired slice · Z '+(state.z+1)+' / '+meta.shape[0]:'Z projection · '+({mean:'average',max:'maximum',sum:'sum'}[state.projection]||state.projection);
 const umPerPixel=state.mode!=='volume'&&v?.transform&&meta.calibrated?meta.spacing[0]/(v.transform.s*scale):null;
 return {
  software:'FIELD microscopy studio',exported:new Date().toISOString(),
  image:{name:meta.name,dataset:state.dataset,source_file:meta.original_source||meta.path,source_sha256:meta.original_sha256||null,shape_zcyx:meta.shape,spacing_xyz_um:meta.calibrated?meta.spacing:null},
  view:{mode:modeName,channel_active:meta.channels[state.channel],projection:state.mode==='projection'?state.projection:undefined,z_plane_1based:state.mode==='slice'?state.z+1:undefined,
   region_xyz_start_end:state.region3d||undefined,camera:state.mode==='volume'&&cam?{yaw_deg:+cam.yaw.toFixed(1),pitch_rad:+cam.pitch.toFixed(3),zoom:+cam.zoom.toFixed(2)}:undefined,
   render:state.mode==='volume'?{...state.render}:undefined,grid:!!state.showGrid,scale_bar:!!state.showScaleBar,export_scale:scale,um_per_output_pixel:umPerPixel?+umPerPixel.toPrecision(5):undefined},
  channels:channels.map(i=>({index_1based:i+1,name:meta.channels[i],color:'rgb('+channelRGB(i).join(',')+')',brightness_pct:settings[i].brightness,contrast_pct:settings[i].contrast,black_point:settings[i].blackPoint,white_point:settings[i].whitePoint,background:settings[i].background})),
  result:r?{run:r.id,title:r.title||r.method,method:r.method,scope:r.scope,xy_factor:r.factor,target:r.target||undefined,overlay:state.overlay}:null,
  cell:state.focusObject?{id:state.focusObject.id,neighbours:state.focusView.neighbors,context_um:state.focusView.context}:null,
  note:'Display rendering for figures. Brightness, contrast and 3D rendering change appearance only; use the source stack for measurement.'};
}
function captionLines(m){
 const lines=[m.image.name+'  ·  '+m.view.mode];
 if(m.result)lines.push('Result: '+m.result.title+(m.cell?`  ·  cell #${m.cell.id} (neighbours ${m.cell.neighbours}${m.cell.neighbours!=='isolate'?', '+m.cell.context_um+' µm context':''})`:''));
 const s=m.image.spacing_xyz_um;lines.push((s?`Voxel ${s.map(v=>+v.toPrecision(4)).join(' × ')} µm`:'Uncalibrated')+(m.view.um_per_output_pixel?`  ·  ${m.view.um_per_output_pixel} µm per image pixel`:'')+(m.image.source_sha256?'  ·  source '+m.image.source_sha256.slice(0,12):'')+'  ·  '+m.exported.slice(0,16).replace('T',' ')+' UTC  ·  FIELD');
 return lines;
}
async function renderExport({scale,caption}){
 const host=$('#main-host'),views=[...host.querySelectorAll('.viewport')];if(!views.length)throw Error('Open an image view first');
 const previousQuality=state.render.quality,restore=()=>{state.exportScale=0;state.render.quality=previousQuality;scheduleDraw()};
 try{
  if(state.mode==='volume'&&scale>1)state.render.quality='precise';
  stopTurntable();state.exportScale=scale;
  // Two passes: a redraw scheduled meanwhile would cancel the first pass's ticket mid-render.
  await Promise.all(views.map(v=>draw(v)));await new Promise(r=>requestAnimationFrame(r));await Promise.all(views.map(v=>draw(v)));
  const box=host.getBoundingClientRect(),meta=viewMetadata(scale),lines=caption?captionLines(meta):[];
  const pad=14*scale,line=17*scale,swatchRow=caption?22*scale:0,strip=caption?pad*2+swatchRow+lines.length*line:0;
  const out=document.createElement('canvas');out.width=Math.round(box.width*scale);out.height=Math.round(box.height*scale+strip);
  const ctx=out.getContext('2d');ctx.fillStyle='#020608';ctx.fillRect(0,0,out.width,out.height);
  for(const v of views){const c=v.querySelector('canvas'),r=c.getBoundingClientRect();ctx.drawImage(c,(r.left-box.left)*scale,(r.top-box.top)*scale,r.width*scale,r.height*scale)}
  if(caption){
   const y0=box.height*scale;ctx.fillStyle='#0d1013';ctx.fillRect(0,y0,out.width,strip);ctx.fillStyle='#ffffff14';ctx.fillRect(0,y0,out.width,Math.max(1,scale));
   let x=pad,y=y0+pad;ctx.font=`600 ${12*scale}px ui-sans-serif,system-ui,-apple-system`;ctx.textBaseline='top';
   for(const ch of meta.channels){ctx.fillStyle=ch.color;ctx.fillRect(x,y+2*scale,11*scale,11*scale);x+=17*scale;ctx.fillStyle='#e7eaee';ctx.fillText(ch.name,x,y);x+=ctx.measureText(ch.name).width+18*scale}
   y+=swatchRow;ctx.font=`${12*scale}px ui-sans-serif,system-ui,-apple-system`;
   lines.forEach((text,i)=>{ctx.fillStyle=i?'#9aa3ae':'#e7eaee';ctx.fillText(text,pad,y+i*line)});
  }
  return {canvas:out,meta};
 }finally{restore()}
}
// PNG text chunks (tEXt for short keys, iTXt UTF-8 for the JSON) and pHYs for physical pixel size.
const crcTable=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
function crc32(bytes){let c=0xffffffff;for(const b of bytes)c=crcTable[(c^b)&255]^(c>>>8);return (c^0xffffffff)>>>0}
function pngChunk(type,data){const out=new Uint8Array(12+data.length),view=new DataView(out.buffer);view.setUint32(0,data.length);out.set(new TextEncoder().encode(type),4);out.set(data,8);view.setUint32(8+data.length,crc32(out.subarray(4,8+data.length)));return out}
function textChunk(key,value){const k=new TextEncoder().encode(key),v=new TextEncoder().encode(value);
 if(/^[\x20-\x7e\n]*$/.test(value)){const d=new Uint8Array(k.length+1+v.length);d.set(k);d.set(v,k.length+1);return pngChunk('tEXt',d)}
 const d=new Uint8Array(k.length+5+v.length);d.set(k);d.set(v,k.length+5);return pngChunk('iTXt',d)}
async function pngWithMetadata(canvas,meta){
 const bytes=new Uint8Array(await (await new Promise(r=>canvas.toBlob(r,'image/png'))).arrayBuffer());
 const chunks=[textChunk('Title',meta.image.name),textChunk('Software',meta.software),textChunk('Creation Time',meta.exported),textChunk('Source',(meta.image.source_file||'')+(meta.image.source_sha256?' sha256:'+meta.image.source_sha256:'')),
  textChunk('Description',captionLines(meta).join('\n')),textChunk('field:view',JSON.stringify(meta))];
 if(meta.view.um_per_output_pixel){const d=new Uint8Array(9),v=new DataView(d.buffer),ppm=Math.round(1e6/meta.view.um_per_output_pixel);v.setUint32(0,ppm);v.setUint32(4,ppm);d[8]=1;chunks.unshift(pngChunk('pHYs',d))}
 const iend=bytes.length-12,parts=[bytes.subarray(0,iend),...chunks,bytes.subarray(iend)];
 return new Blob(parts,{type:'image/png'});
}
function exportName(meta,scale){return `field-${meta.image.dataset}-${state.mode}${meta.cell?'-cell'+meta.cell.id:''}-${scale}x-${meta.exported.slice(0,19).replace(/[:T]/g,'-')}.png`}
async function exportImage(action,prefs=exportPrefs){
 status(`Rendering ${prefs.scale}× image…`);
 const {canvas,meta}=await renderExport(prefs);
 if(action==='copy'){
  const blob=await new Promise(r=>canvas.toBlob(r,'image/png'));
  await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
  status(`Copied ${canvas.width} × ${canvas.height} image${prefs.caption?' with info strip':''} · paste into PowerPoint or Word`);
 }else{
  const blob=await pngWithMetadata(canvas,meta),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=exportName(meta,prefs.scale);a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
  status(`Saved ${canvas.width} × ${canvas.height} PNG with embedded view metadata`);
 }
}
function openExportDialog(){
 const d=expModal('Export image','Re-renders the current view at higher resolution. Floating controls are left out; the scale bar, grid and overlays are kept.','export-dialog');
 const scaleRow=expNode('div','export-row');scaleRow.append(expNode('span','export-label','Resolution'));
 const seg=expNode('div','segmented small export-scale');const pill=expNode('span','segment-pill');seg.append(pill);
 const host=$('#main-host').getBoundingClientRect(),size=expNode('span','export-size');
 const sync=()=>{seg.querySelectorAll('button').forEach(b=>b.classList.toggle('active',+b.dataset.scale===exportPrefs.scale));movePill(seg);size.textContent=`${Math.round(host.width*exportPrefs.scale)} × ${Math.round(host.height*exportPrefs.scale)} px`};
 for(const s of [1,2,4]){const b=expButton(s+'×','',()=>{exportPrefs.scale=s;saveExportPrefs();sync()});b.dataset.scale=s;seg.append(b)}
 scaleRow.append(seg,size);
 const cap=expNode('label','export-check');const box=document.createElement('input');box.type='checkbox';box.checked=exportPrefs.caption;box.onchange=()=>{exportPrefs.caption=box.checked;saveExportPrefs()};
 cap.append(box,document.createTextNode(' Add info strip (image, channels, view, spacing, date)'));
 const note=expNode('p','export-note','Saved PNGs also carry the full view description as embedded metadata (title, source checksum, channels and display settings, camera, run and cell; physical pixel size for 2D views). Copying to the clipboard keeps only the pixels, so use the info strip when pasting.');
 const msg=expNode('p','export-msg');msg.setAttribute('role','status');
 const actions=expNode('div','dialog-actions');
 const run=action=>async()=>{actions.querySelectorAll('button').forEach(b=>b.disabled=true);msg.textContent='Rendering…';try{await exportImage(action);d.close()}catch(error){msg.textContent=error.message||'Export failed'}finally{actions.querySelectorAll('button').forEach(b=>b.disabled=false)}};
 actions.append(expButton('Copy to clipboard','',run('copy')),expButton('Download PNG','primary',run('download')));
 d.append(scaleRow,cap,note,msg,actions);requestAnimationFrame(sync);
}
// Save view now opens the export dialog; Copy image copies with the last-used settings.
{const save=document.querySelector('.tool-rail .save-view');if(save){save.onclick=openExportDialog;save.title='Export a high-resolution PNG of the current view, with an optional info strip and embedded metadata';const label=save.querySelector('.explore-tool-label');if(label)label.textContent='Export image';save.dataset.tip='Export image'}
 copyImageButton.onclick=async()=>{try{await exportImage('copy')}catch(error){status(error.message.includes('ClipboardItem')||error.name==='NotAllowedError'?'Clipboard unavailable here · use Export image':error.message,true)}};
 copyImageButton.title=`Copy a high-resolution image (last export settings: ${exportPrefs.scale}×${exportPrefs.caption?', with info strip':''})`}

// ---- Results panel: explicit open/close from the toolbar, an edge tab, and the [ key (all workspaces) ----
function setResultsPanel(open){
 document.body.classList.toggle('sidebar-collapsed',!open);try{localStorage.setItem('field-sidebar-collapsed',open?'0':'1')}catch{}
 resultsToggle.setAttribute('aria-pressed',String(open));resultsToggle.title=(open?'Hide':'Show')+' the results panel  [';
 setTimeout(()=>{scheduleDraw();document.querySelectorAll('.segmented').forEach(movePill);if(state.tab==='Review')drawReviewCanvases()},380);
}
const resultsToggle=document.createElement('button');resultsToggle.className='results-toggle';resultsToggle.type='button';
resultsToggle.innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9 4v16"/></svg><span>Results</span><b class="results-count"></b>';
resultsToggle.setAttribute('aria-label','Toggle results panel');resultsToggle.onclick=()=>setResultsPanel(document.body.classList.contains('sidebar-collapsed'));
$('#simple-toolbar').prepend(resultsToggle);
const edgeTab=document.createElement('button');edgeTab.className='results-edge';edgeTab.type='button';edgeTab.setAttribute('aria-label','Show results panel');edgeTab.title='Show results  [';
edgeTab.innerHTML='<span>Results</span><b class="results-count"></b>';edgeTab.onclick=()=>setResultsPanel(true);$('#workspace').prepend(edgeTab);
document.querySelector('.sidebar-toggle')?.addEventListener('click',()=>setResultsPanel(false),true);
new MutationObserver(()=>document.querySelectorAll('.results-count').forEach(b=>b.textContent=$('#result-count').textContent||'')).observe($('#result-count'),{childList:true,characterData:true,subtree:true});
document.addEventListener('keydown',e=>{if(e.key==='['&&!e.metaKey&&!e.ctrlKey&&!e.target.closest('input,textarea,select,[contenteditable]')){e.preventDefault();setResultsPanel(document.body.classList.contains('sidebar-collapsed'))}});
resultsToggle.setAttribute('aria-pressed',String(!document.body.classList.contains('sidebar-collapsed')));
shortcutGroups[0][1].push(['[','Show or hide the results panel']);

// ---- Cell numbers on detected candidates (2D, 3D, single-cell neighbours and Review planes) ----
state.cellLabels=(()=>{try{return localStorage.getItem('field-cell-labels')!=='off'}catch{return true}})();
function setCellLabels(on){state.cellLabels=on;try{localStorage.setItem('field-cell-labels',on?'on':'off')}catch{}document.querySelectorAll('[data-cell-labels]').forEach(i=>i.checked=on);scheduleDraw();if(state.tab==='Review')drawReviewCanvases()}
const readyIndexes=new Map();
function readyIndex(run){
 if(!run)return null;if(readyIndexes.has(run))return readyIndexes.get(run);
 readyIndexes.set(run,null);objectIndex(run).then(d=>{readyIndexes.set(run,d);scheduleDraw();if(state.tab==='Review')drawReviewCanvases()}).catch(()=>readyIndexes.delete(run));return null;
}
// Corrections renumber or reshape objects: forget cached positions whenever runs reload.
{const labelLoadRuns=loadRuns;loadRuns=async function(){readyIndexes.clear();objectIndexCache.clear();return labelLoadRuns()}}
function labelRunFor(v){
 if(state.focusObject)return state.focusObject.run;
 const id=v.overrideRun!==undefined?v.overrideRun:state.run,r=state.runs.find(r=>r.id===id);
 return r&&!r.historical&&r.scope==='volume'&&r.method!=='preprocess'&&!v.raw&&state.overlay!=='none'?r.id:null;
}
function paintLabels(ctx,items,limit=600){
 // Greedy placement: earlier items win; overlapping labels are skipped instead of stacking.
 const placed=[];let drawn=0;ctx.save();ctx.font='600 10.5px ui-sans-serif,system-ui,-apple-system';ctx.textAlign='center';ctx.textBaseline='middle';
 for(const it of items){
  if(drawn>=limit)break;const text='#'+it.id,w=ctx.measureText(text).width+8,h=15,box=[it.x-w/2,it.y-h/2,it.x+w/2,it.y+h/2];
  if(placed.some(b=>box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1]))continue;placed.push(box);drawn++;
  ctx.fillStyle=it.dim?'#0b0f14b8':'#0b0f14d9';ctx.beginPath();ctx.roundRect(box[0],box[1],w,h,5);ctx.fill();
  ctx.strokeStyle=it.dim?'#ffffff1f':'#ffffff38';ctx.lineWidth=1;ctx.stroke();ctx.fillStyle=it.dim?'#b7c0ca':'#f1f4f7';ctx.fillText(text,it.x,it.y+.5);
 }
 ctx.restore();return drawn;
}
function drawCellLabels(v){
 if(!state.cellLabels||state.tab!=='Explore')return;const run=labelRunFor(v),index=readyIndex(run);if(!index)return;
 const c=v.querySelector('canvas'),ctx=c.getContext('2d');ctx.save();ctx.setTransform(c.width/c.clientWidth,0,0,c.height/c.clientHeight,0,0);
 let items=[];
 if(v.dataset.kind==='volume'&&v.project&&v.bounds3d){
  const [[x0,y0,z0],[x1,y1,z1]]=v.bounds3d,clip=clipFor(v.bounds3d),at=(a,t)=>v.bounds3d[0][a]+t*(v.bounds3d[1][a]-v.bounds3d[0][a]);
  const lo=clip?[at(0,clip.x[0]),at(1,clip.y[0]),at(2,clip.z[0])]:[x0,y0,z0],hi=clip?[at(0,clip.x[1]),at(1,clip.y[1]),at(2,clip.z[1])]:[x1,y1,z1];
  for(const o of index.objects){
   if(state.focusObject&&(o.id===state.focusObject.id||state.focusView.neighbors==='isolate'))continue;
   const [cx,cy,cz]=o.center;if(cx<lo[0]||cx>hi[0]||cy<lo[1]||cy>hi[1]||cz<lo[2]||cz>hi[2])continue;
   const p=v.project(cx,cy,cz);items.push({x:p[0],y:p[1],depth:p[2],id:o.id,dim:!!state.focusObject})}
  items.sort((a,b)=>b.depth-a.depth);
 }else if(v.transform){
  const t=v.transform,w=c.clientWidth,h=c.clientHeight;
  for(const o of index.objects){
   const [[,,za],[,,zb]]=o.bounds_native;if(v.dataset.kind==='slice'&&(state.z<za||state.z>=zb))continue;
   const x=t.ox+o.center[0]*t.s,y=t.oy+o.center[1]*t.s;if(x<-10||y<-10||x>w+10||y>h+10)continue;items.push({x,y,id:o.id})}
 }
 paintLabels(ctx,items);ctx.restore();
}
{const labelDraw=draw;draw=async function(v){const expected=(v.ticket||0)+1;await labelDraw(v);if(v.isConnected&&v.ticket===expected)drawCellLabels(v)}}
{const labelReview=drawReviewCanvases;drawReviewCanvases=function(){
 labelReview();if(!state.cellLabels)return;const data=reviewState.data,host=reviewState.host,index=readyIndex(state.run);if(!data||!index||!host?.isConnected)return;
 for(const frame of host.querySelectorAll('.review-plane')){
  const axis=frame.dataset.axis;if(axis!=='xy'&&axis!=='raw')continue;const c=frame.querySelector('canvas'),t=c.reviewTransform;if(!t)continue;
  const ctx=c.getContext('2d');ctx.save();ctx.setTransform(c.width/c.clientWidth,0,0,c.height/c.clientHeight,0,0);ctx.beginPath();ctx.rect(t.x,t.y,t.width*t.sx,t.height*t.sy);ctx.clip();
  const z=data.cursor[2],items=index.objects.filter(o=>z>=o.bounds_native[0][2]&&z<o.bounds_native[1][2]).map(o=>({x:t.x+(o.center[0]+.5)*t.sx,y:t.y+(o.center[1]+.5)*t.sy,id:o.id,dim:axis==='raw'}));
  paintLabels(ctx,items);ctx.restore();
 }}}
// Toggles: Display menu (main viewers) and the cell navigator (neighbours).
{const body=document.querySelector('.display-menu .dropdown-body');if(body){const field=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.cellLabels='';input.checked=state.cellLabels;input.onchange=()=>setCellLabels(input.checked);field.title='Show each detected candidate’s ID in 2D, 3D and Review';field.append(input,document.createTextNode('# Cell numbers'));body.append(field)}}
{const labelNavigator=cellNavigator;cellNavigator=function(v){const card=labelNavigator(v);const field=document.createElement('label');field.className='render-check';const input=document.createElement('input');input.type='checkbox';input.dataset.cellLabels='';input.checked=state.cellLabels;input.onchange=()=>setCellLabels(input.checked);field.append(input,document.createTextNode('Label neighbouring cells'));field.title='Show the ID of each surrounding candidate';const heading=[...card.querySelectorAll('.float-card-label')].find(el=>/Nearest/.test(el.textContent));(heading||card.querySelector('.neighbor-chips'))?.before(field);return card}}

// ---- Workspace walkthroughs: Process and Review open with a short guided flow the first time ----
function runTour(steps,key,i=0){
 document.querySelector('.tour-layer')?.remove();
 if(i>=steps.length){try{localStorage.setItem(key,'1')}catch{}return}
 const step=steps[i];step.prep?.();
 const show=()=>{
  const target=document.querySelector(step.target);if(!target||!target.offsetWidth)return runTour(steps,key,i+1);
  target.scrollIntoView({block:'nearest'});
  const r=target.getBoundingClientRect(),layer=expNode('div','tour-layer'),spot=expNode('div','tour-spot'),card=expNode('div','tour-card');
  const spotTop=Math.max(4,r.top-6),spotBottom=Math.min(innerHeight-4,r.bottom+6);
  Object.assign(spot.style,{left:r.left-6+'px',top:spotTop+'px',width:r.width+12+'px',height:Math.max(20,spotBottom-spotTop)+'px'});
  card.append(expNode('span','tour-step',`${step.section||'Guide'} · ${i+1} of ${steps.length}`),expNode('h3','',step.title),expNode('p','',step.text));
  const actions=expNode('div','tour-actions');actions.append(expButton('Skip','',()=>runTour(steps,key,steps.length)));if(i)actions.append(expButton('Back','',()=>runTour(steps,key,i-1)));actions.append(expButton(i===steps.length-1?'Done':'Next','primary-action',()=>runTour(steps,key,i+1)));card.append(actions);
  layer.append(spot,card);document.body.append(layer);
  const w=320,h=card.offsetHeight,space={below:innerHeight-r.bottom,above:r.top,right:innerWidth-r.right,left:r.left};
  let left,top;
  if(space.below>h+24){top=r.bottom+16;left=r.left+r.width/2-w/2}else if(space.above>h+24){top=r.top-16-h;left=r.left+r.width/2-w/2}
  else if(space.left>w+24){left=r.left-16-w;top=r.top+r.height/2-h/2}else{left=r.right+16;top=r.top+r.height/2-h/2}
  Object.assign(card.style,{left:Math.max(12,Math.min(innerWidth-w-12,left))+'px',top:Math.max(12,Math.min(innerHeight-h-12,top))+'px'});
  card.querySelector('.primary-action').focus();
  // Panels may still be animating open; follow the target once it settles.
  setTimeout(()=>{if(!spot.isConnected)return;const q=target.getBoundingClientRect(),t=Math.max(4,q.top-6),b=Math.min(innerHeight-4,q.bottom+6);Object.assign(spot.style,{left:q.left-6+'px',top:t+'px',width:q.width+12+'px',height:Math.max(20,b-t)+'px'});if(q.width>r.width+40&&parseFloat(card.style.left)<q.right)card.style.left=Math.min(innerWidth-332,q.right+16)+'px'},420);
  layer.addEventListener('keydown',e=>{if(e.key==='Escape')runTour(steps,key,steps.length);if(e.key==='ArrowRight')runTour(steps,key,i+1);if(e.key==='ArrowLeft'&&i)runTour(steps,key,i-1)});
 };
 step.prep?setTimeout(show,450):show();
}
startTour=(i=0)=>runTour(tourSteps.map(([target,title,text])=>target==='#result-list'?{target:'#result-sidebar',title,text,section:'Studio',prep:()=>setResultsPanel(true)}:{target,title,text,section:'Studio'}),'field-tour-done',i);
const processTour=[
 {target:'.process-steps',title:'Preview → Tune → Run',text:'For a 3D volume, try the recipe on a small region, adjust the settings, then save a full-image or selected-region run. Previews are unsaved snapshots. A 2D slice or Z projection can be run directly.'},
 {target:'#task-panel .process-input',title:'Source & region',text:'Choose the source channel, 3D volume or 2D scope, and XY resolution. For 3D, Run region chooses Full image or Selected XY / Z. Edit the region to set its XY bounds and Z range; a preview may sample a smaller part of a large region.'},
 {target:'#task-panel .exp-section.mint',title:'Preprocessing',text:'Smooth reduces fine noise, Background subtracts a broader signal, and Normalize intensity rescales contrast. A value of 0 turns either filter off. These steps prepare the signal before the labeling technique runs.'},
 {target:'#task-panel .process-algorithm',title:'Label & measure',text:'Choose a Technique: Connected regions labels bright signal, Separate touching cells uses watershed, and the five Neurites techniques measure skeleton paths and branches. Neurite results describe connected networks; crossings are not assigned to individual neurons. Compare all 5 techniques saves separate runs.'},
 {target:'#task-panel .algo-pipeline-box',title:'Applied pipeline',text:'Expand Applied pipeline to read every step and its current setting; greyed steps are off. Change the controls above to edit the recipe. Advanced… holds input, calibration, run naming and additional method settings.'},
 {target:'#task-panel .experiment-actions',title:'Preview, then save',text:'Preview this region, or Preview a sample, shows source, processed signal and outlines side by side for 3D. Refresh it after changing the recipe, or enable Auto-preview. The Run button saves the scope and region you chose; its label identifies what will run.'},
 {target:'#main-host',title:'Read the preview',text:'Check outlines against the source: look for merged cells, split cells, debris or missing neurite paths. Use the preview depth control to inspect acquired Z planes. A preview helps tune the recipe; its candidate labels do not establish biological accuracy.'},
 {target:'#result-sidebar',title:'Your runs',text:'Saved results appear here with their method, channel and region. Select one to review candidates or inspect neurite measurements and exports. Hide or show this panel with Results in the toolbar or the [ key.',prep:()=>setResultsPanel(true)}];
const reviewTour=[
 {target:'.review-switch',title:'Two views',text:'Planes shows the selected run in synchronized slices; Candidates lists every detected object with counts, filters and export. The badge shows how many still need a decision.',prep:()=>setReviewView('planes')},
 {target:'.review-plane-grid',title:'Synchronized planes',text:'Raw XY and result XY sit on top; XZ and YZ show depth (stretched for thin stacks — see View). Click any plane to move the shared crosshair; colours are candidate masks and #numbers are their IDs.'},
 {target:'#task-panel .compact-xyz',title:'Crosshair',text:'Type exact X, Y and Z (0-based voxels) or use arrow keys in a focused plane.'},
 {target:'#object-inspector',title:'The candidate under the crosshair',text:'Open in 3D shows it with its neighbours. Decide… records accept, reject or needs review. Fix mask splits, merges, deletes or adds, saving a new label revision; the original run never changes.'},
 {target:'.review-view-menu',title:'View options',text:'Intensity window, depth stretch and zoom around the crosshair.'},
 {target:'.measurement-panel',title:'Candidates & counts',text:'Here you set count rules, filter by decision or edge contact, and export CSV, counts or corrected masks. When the lab’s manual counts exist for this image they appear here for comparison.',prep:()=>setReviewView('candidates')},
 {target:'.review-switch',title:'Typical loop',text:'Candidates → click a row → Planes to inspect → Decide or Fix → next. Once every candidate has a decision under your count rules, the reviewed count is ready to export.',prep:()=>setReviewView('planes')}];
function workspaceTour(tab){return tab==='Process'?[processTour,'field-tour-process']:tab==='Review'?[reviewTour,'field-tour-review']:null}
function openWorkspaceGuide(){const t=workspaceTour(state.tab);if(t)runTour(t[0].map(s=>({...s,section:state.tab})),t[1]);else startTour()}
// A "How this works" button in the toolbar for Process and Review; auto-start once per workspace.
let guidePending=false;
const guideButton=expButton('? How this works','guide-button',openWorkspaceGuide);guideButton.title='Walk through this workspace step by step';
$('#simple-toolbar').append(guideButton);
{const guideLayout=renderLayout;renderLayout=function(){guideLayout();guideButton.hidden=!['Process','Review'].includes(state.tab);
 const t=workspaceTour(state.tab);if(!t||document.querySelector('.tour-layer'))return;let seen=true;try{seen=localStorage.getItem(t[1])==='1'}catch{}
 if(!seen&&!guidePending&&(state.tab!=='Review'||reviewEligible())){guidePending=true;const tab=state.tab;setTimeout(()=>{guidePending=false;if(state.tab===tab&&!document.querySelector('.tour-layer'))runTour(t[0].map(s=>({...s,section:tab})),t[1])},1400)}}}
