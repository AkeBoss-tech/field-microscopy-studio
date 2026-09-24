'use strict';
// Review corrections create new label revisions; source pixels and original runs stay immutable.
const reviewState={dataset:null,x:0,y:0,contrast:'auto',depthScale:1,zoom:1,data:null,images:null,host:null,timer:null,busy:false,pending:null,serial:0,signature:null};
const intensityKinds=[['raw','Raw source'],['processed','Processed intensity'],['ridge-response','Ridge response']];
const layerLabel=document.createElement('label');layerLabel.className='intensity-control';layerLabel.append(document.createTextNode('Image layer '));
const layerSelect=document.createElement('select');layerSelect.id='intensity-layer';layerSelect.setAttribute('aria-label','Image layer');layerLabel.append(layerSelect);
$('#simple-toolbar').insertBefore(layerLabel,$('#compare-raw').closest('label'));
const maskLabel=$('#overlay').closest('label');maskLabel.classList.add('mask-control');$('#simple-toolbar').insertBefore(maskLabel,layerLabel.nextSibling);
const opacityLabel=document.createElement('label');opacityLabel.className='mask-opacity';opacityLabel.textContent='Mask opacity ';const maskOpacity=document.createElement('input');maskOpacity.type='range';maskOpacity.min=0;maskOpacity.max=100;maskOpacity.value=state.opacity*100;maskOpacity.setAttribute('aria-label','Mask opacity');opacityLabel.append(maskOpacity);maskLabel.after(opacityLabel);
const contextLine=document.createElement('div');contextLine.id='analysis-context';$('#workspace').before(contextLine);

function refreshLayerControls(){
 if(!state.meta)return;
 const r=runMeta(),current=state.image;
 const available=intensityKinds.filter(([key])=>key==='raw'||(r&&!r.historical&&(key!=='ridge-response'||r.ridge_response)));
 const signature=available.map(([key])=>key).join(',');
 if(layerSelect.dataset.options!==signature){layerSelect.replaceChildren(...available.map(([key,title])=>new Option(title,key)));layerSelect.dataset.options=signature}
 if(!available.some(([key])=>key===current))state.image='raw';layerSelect.value=state.image;
 $('#show-processed').checked=state.image==='processed';$('#processed-label').hidden=true;
 const hasMask=!!r&&r.method!=='preprocess'&&(!r.geometry||r.mask_path);
 maskLabel.hidden=!hasMask;opacityLabel.hidden=!hasMask;$('#overlay').value=state.overlay;maskOpacity.value=state.opacity*100;
 const review=state.tab==='Review',annotation=state.tab==='Annotate';document.body.classList.toggle('volume-review',review);
 for(const menu of document.querySelectorAll('.display-menu,.channels-menu')){menu.hidden=review;if(review)menu.open=false}
 document.querySelector('.mode-buttons').hidden=review||annotation;
 for(const el of [$('#compare-raw').closest('label'),$('#comparison'),$('#compare-grid')])el.hidden=review||annotation;
 document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===state.tab);b.setAttribute('aria-pressed',String(b.dataset.tab===state.tab))});
 const layer=intensityKinds.find(([key])=>key===state.image)?.[1]||'Raw source';
 contextLine.textContent=state.meta.name+' · C'+(state.channel+1)+' '+state.meta.channels[state.channel]+' · '+(r?(r.title||r.method)+' / '+r.id.slice(0,8)+' · '+(r.scope==='volume'?'all '+state.meta.shape[0]+' Z · '+r.factor+'× XY':r.scope==='slice'?'plane '+(r.z+1):'2D projection'):'original source')+' · '+layer+(hasMask&&state.overlay!=='none'?' + candidate labels':'');
 if(state.tab==='Process')contextLine.textContent+=' · Form at right: next run draft';
}
layerSelect.onchange=()=>{state.image=layerSelect.value;$('#image').value=state.image==='raw'?'raw':'processed';refreshLayerControls();scheduleDraw()};
maskOpacity.oninput=()=>{state.opacity=+maskOpacity.value/100;scheduleDraw()};
// Keep the legacy display controls synchronized for optional floating windows.
$('#show-processed').onchange=e=>{state.image=e.target.checked?'processed':'raw';refreshLayerControls();scheduleDraw()};
$('#image').onchange=e=>{state.image=e.target.value;refreshLayerControls();scheduleDraw()};
$('#overlay').onchange=e=>{state.overlay=e.target.value;refreshLayerControls();scheduleDraw()};

function resetReviewSelection(){reviewState.signature=null;reviewState.data=null;reviewState.serial++}
function reviewEligible(){const r=runMeta();return !r||(r.scope==='volume'&&!r.historical)}
function reviewRequest(){return {dataset:state.dataset,channel:state.channel,run:state.run,layer:state.image,x:reviewState.x,y:reviewState.y,z:state.z,overlay:state.overlay,opacity:state.opacity,contrast:reviewState.contrast}}
function renderReviewWorkspace(){
 if(reviewState.dataset!==state.dataset){reviewState.dataset=state.dataset;reviewState.x=Math.floor(state.meta.shape[3]/2);reviewState.y=Math.floor(state.meta.shape[2]/2);resetReviewSelection()}
 document.body.classList.remove('student');document.querySelectorAll('.floating-tools,.canvas-hint,.annotation-view-choice,.draft-actions').forEach(el=>el.remove());
 const host=$('#main-host');host.className='volume-review-host';host.replaceChildren();$('#windows').replaceChildren();
 const panel=$('#task-panel');panel.hidden=false;panel.replaceChildren();reviewState.host=host;reviewState.signature=null;reviewState.serial++;
 resultCatalog();refreshLayerControls();
 if(!reviewEligible()){
  const card=document.createElement('section');card.className='review-empty';const h=document.createElement('h2');h.textContent='This result does not contain a registered 3-D label volume';const p=document.createElement('p');p.textContent='Review volume uses acquired XY, XZ and YZ planes. Projection, single-plane and historical geometry results stay in Explore; their apparent depth must not be treated as a volume.';const b=document.createElement('button');b.textContent='Open this result in Explore';b.onclick=()=>{state.tab='Explore';const r=runMeta();state.mode=r?.scope==='slice'?'slice':'projection';renderLayout()};card.append(h,p,b);host.append(card);panel.hidden=true;return;
 }
 const controls=document.createElement('div');controls.className='review-controls';
 const contrast=document.createElement('label');contrast.textContent='Intensity window ';const select=document.createElement('select');select.setAttribute('aria-label','Review intensity window');select.add(new Option('Auto per intensity layer','auto'));select.add(new Option('Use raw window for both','raw'));select.value=reviewState.contrast;select.onchange=()=>{reviewState.contrast=select.value;scheduleReview()};contrast.append(select);
 const depth=document.createElement('label');depth.textContent='Depth display ';const depthSelect=document.createElement('select');depthSelect.setAttribute('aria-label','Depth display');for(const [value,label] of [[1,'Physical proportions'],[6,'Expand Z ×6 (display only)'],[12,'Expand Z ×12 (display only)']])depthSelect.add(new Option(label,value));depthSelect.value=reviewState.depthScale;depthSelect.onchange=()=>{reviewState.depthScale=+depthSelect.value;drawReviewCanvases()};depth.append(depthSelect);
 const zoomLabel=document.createElement('label');zoomLabel.textContent='Zoom ';const zoom=document.createElement('select');zoom.setAttribute('aria-label','Review zoom');for(const n of [1,2,4,8])zoom.add(new Option(n===1?'Fit':n+'× around crosshair',n));zoom.value=reviewState.zoom;zoom.onchange=()=>{reviewState.zoom=+zoom.value;drawReviewCanvases()};zoomLabel.append(zoom);controls.append(contrast,depth,zoomLabel);host.append(controls);
 const grid=document.createElement('div');grid.className='review-plane-grid';
 for(const [axis,title] of [['raw','Raw source · XY'],['xy','Result · XY'],['xz','Result · XZ'],['yz','Result · YZ']]){
  const frame=document.createElement('section');frame.className='review-plane';frame.dataset.axis=axis;
  const caption=document.createElement('div');caption.className='review-plane-title';caption.textContent=title;
  const canvas=document.createElement('canvas');canvas.tabIndex=0;canvas.setAttribute('aria-label',title+' inspection view');frame.append(caption,canvas);grid.append(frame);
  canvas.onclick=e=>moveReviewCursor(canvas,axis,e);canvas.onkeydown=e=>{
   const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(!delta)return;e.preventDefault();
   if(axis==='raw'||axis==='xy'){reviewState.x+=delta[0];reviewState.y+=delta[1]}else{if(axis==='xz')reviewState.x+=delta[0];else reviewState.y+=delta[0];state.z+=delta[1]}clampReviewCursor();scheduleReview();
  };
 }
 host.append(grid);const note=document.createElement('details');note.className='review-canvas-help';const summary=document.createElement('summary');summary.textContent='How to inspect these planes';const help=document.createElement('p');help.textContent='Click a voxel to synchronize XY, XZ and YZ. Arrow keys move the focused crosshair. A candidate row locates its label. Correct mask opens a preview and saves a new label revision; Annotate draws independent points and traces.';note.append(summary,help);host.append(note);
 const heading=document.createElement('h2');heading.textContent='Inspect this volume';panel.append(heading);
 const positions=document.createElement('div');positions.className='review-position-controls';
 for(const [axis,max] of [['x',state.meta.shape[3]-1],['y',state.meta.shape[2]-1],['z',state.meta.shape[0]-1]]){
  const label=document.createElement('label');label.textContent=axis.toUpperCase()+' voxel (0-based) ';const input=document.createElement('input');input.type='number';input.min=0;input.max=max;input.step=1;input.value=axis==='z'?state.z:reviewState[axis];input.id='review-'+axis;input.setAttribute('aria-label','Review '+axis.toUpperCase()+' voxel');input.oninput=()=>{if(!input.checkValidity()||input.value==='')return;if(axis==='z')state.z=+input.value;else reviewState[axis]=+input.value;clampReviewCursor();scheduleReview()};label.append(input);positions.append(label);
 }
 panel.append(positions);const loading=document.createElement('p');loading.id='review-status';loading.role='status';loading.textContent='Loading acquired planes…';panel.append(loading);
 const info=document.createElement('section');info.id='object-inspector';info.className='object-inspector';panel.append(info);
 const limits=document.createElement('p');limits.id='review-window-info';limits.className='muted';panel.append(limits);
 const caveat=document.createElement('p');caveat.className='review-caveat';caveat.textContent='Labels are algorithm candidates. Boundary contact is a review flag, not proof of an incomplete cell. The reviewed count needs explicit count rules and decisions on every included object.';panel.append(caveat);
 scheduleReview();
}
function clampReviewCursor(){const [nz,,ny,nx]=state.meta.shape;reviewState.x=Math.max(0,Math.min(nx-1,Math.floor(reviewState.x)));reviewState.y=Math.max(0,Math.min(ny-1,Math.floor(reviewState.y)));state.z=Math.max(0,Math.min(nz-1,Math.floor(state.z)));$('#z').value=state.z;$('#zlabel').textContent=(state.z+1)+' / '+nz;for(const a of ['x','y','z']){const input=$('#review-'+a);if(input)input.value=a==='z'?state.z:reviewState[a]}}
function moveReviewCursor(canvas,axis,event){
 const t=canvas.reviewTransform;if(!t||!reviewState.data||canvas.closest('.review-loading'))return;
 const b=canvas.getBoundingClientRect(),x=(event.clientX-b.left-t.x)/t.sx,y=(event.clientY-b.top-t.y)/t.sy;
 if(x<0||y<0||x>=t.width||y>=t.height)return;
 if(axis==='raw'||axis==='xy'){reviewState.x=Math.floor(x);reviewState.y=Math.floor(y)}else{if(axis==='xz')reviewState.x=Math.floor(x);else reviewState.y=Math.floor(x);state.z=Math.floor(y)}clampReviewCursor();scheduleReview();
}
function scheduleReview(){
 if(state.tab!=='Review'||!state.meta||!reviewState.host?.isConnected||!reviewEligible())return;
 clampReviewCursor();const request=reviewRequest(),signature=JSON.stringify(request);
 if(signature===reviewState.signature){drawReviewCanvases();return}
 reviewState.signature=signature;const token=++reviewState.serial;reviewState.pending={request,signature,token,host:reviewState.host,generation:state.generation};
 reviewState.host.classList.add('review-loading');const message=$('#review-status');if(message)message.textContent='Updating planes…';
 clearTimeout(reviewState.timer);reviewState.timer=setTimeout(flushReview,70);
}
async function flushReview(){
 if(reviewState.busy||!reviewState.pending)return;
 const work=reviewState.pending;reviewState.pending=null;reviewState.busy=true;
 const current=()=>work.token===reviewState.serial&&state.tab==='Review'&&work.host.isConnected&&work.host===reviewState.host&&work.generation===state.generation;
 try{
  const data=await api('/api/review?'+query(work.request));if(!current())return;
  const images={};await Promise.all(Object.entries(data.planes).map(async([axis,p])=>{const image=new Image();image.src='data:image/png;base64,'+p.png;await image.decode();images[axis]=image}));if(!current())return;
  reviewState.data=data;reviewState.images=images;work.host.classList.remove('review-loading');drawReviewCanvases();showObjectInspector(data);$('#review-status').textContent='Planes synchronized · X '+data.cursor[0]+' · Y '+data.cursor[1]+' · Z '+data.cursor[2]+' (0-based)';
 }catch(e){if(current()){work.host.classList.remove('review-loading');reviewState.data=null;reviewState.images=null;$('#review-status').textContent=e.message;$('#object-inspector').replaceChildren();for(const c of work.host.querySelectorAll('canvas'))c.getContext('2d').clearRect(0,0,c.width,c.height);reviewState.signature=null}}
 finally{reviewState.busy=false;if(reviewState.pending)flushReview()}
}
function showObjectInspector(data){
 const box=$('#object-inspector');if(!box)return;box.replaceChildren();const r=runMeta(),obj=data.object;
 const title=document.createElement('h3');title.textContent=obj?'Candidate #'+obj.id:r&&r.method!=='preprocess'?'No label at this voxel':'Intensity inspection';box.append(title);
 function row(name,value){const p=document.createElement('p'),b=document.createElement('strong');b.textContent=name+' ';p.append(b,document.createTextNode(value));box.append(p)}
 row('Source value:',String(data.source_intensity));if(data.layer!=='raw')row('Layer value:',Number(data.result_value).toPrecision(5));
 if(obj){row('Size:',obj.voxels.toLocaleString()+' processing-grid voxels · '+data.factor+'× XY');row('Volume:',obj.volume_um3===null?'Uncalibrated; physical volume unavailable':obj.volume_um3.toLocaleString(undefined,{maximumFractionDigits:2})+' µm³');row('Native bounds:',obj.bounds_native[0].join(', ')+' → '+obj.bounds_native[1].join(', ')+' (end exclusive)');row('Processed-volume edges:',obj.boundary_faces.length?obj.boundary_faces.join(', '):'None');row('Review status:',obj.status.replaceAll('_',' '))}
 else if(r&&r.method!=='preprocess'){const p=document.createElement('p');p.textContent='Click a labeled voxel in any plane. Gold highlights the selected object across all views.';box.append(p)}
 if(r){row('Run:',(r.title||r.method)+' · '+r.id.slice(0,8));row('Output:',r.method==='preprocess'?'Processed intensity · no segmentation':data.objects+' '+(r.method==='sato'?'connected networks':'candidate regions'));box.append(link('runs/'+r.id+'/run.json','Recipe & provenance'));if(r.method!=='preprocess')box.append(link('runs/'+r.id+'/objects.csv','Original algorithm CSV'))}
 const label=data.calibrated?'µm':'voxel units';$('#review-window-info').textContent='Source spacing XYZ: '+data.spacing.map(v=>Number(v).toPrecision(4)).join(' × ')+' '+label+'. Display windows: raw ['+data.source_window.map(v=>v.toPrecision(4)).join(', ')+']; result ['+data.result_window.map(v=>v.toPrecision(4)).join(', ')+']. Display settings do not alter pixels.';
}
function drawReviewCanvases(){
 const data=reviewState.data,images=reviewState.images,host=reviewState.host;if(!data||!images||!host?.isConnected||state.tab!=='Review')return;
 const [sx,sy,sz]=data.calibrated?data.spacing:[1,1,1];
 for(const frame of host.querySelectorAll('.review-plane')){
  const axis=frame.dataset.axis,c=frame.querySelector('canvas'),rect=c.getBoundingClientRect(),w=rect.width,h=rect.height;if(!w||!h)continue;
  const dpr=Math.min(devicePixelRatio||1,2);c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);const ctx=c.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#040a0e';ctx.fillRect(0,0,w,h);
  const [iw,ih]=data.planes[axis].size,px=axis==='yz'?sy:sx,py=(axis==='raw'||axis==='xy')?sy:sz*reviewState.depthScale;
  const [x,y,z]=data.cursor,cx=axis==='yz'?y:x,cy=(axis==='raw'||axis==='xy')?y:z;const scale=Math.min((w-24)/(iw*px),(h-44)/(ih*py))*reviewState.zoom,dw=iw*px*scale,dh=ih*py*scale,ox=reviewState.zoom===1?(w-dw)/2:w/2-(cx+.5)*dw/iw,oy=reviewState.zoom===1?(h-dh)/2:h/2-(cy+.5)*dh/ih;
  ctx.imageSmoothingEnabled=false;ctx.drawImage(images[axis],ox,oy,dw,dh);c.reviewTransform={x:ox,y:oy,sx:dw/iw,sy:dh/ih,width:iw,height:ih};
  ctx.strokeStyle='#6bf0dd';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(ox+(cx+.5)*dw/iw,oy);ctx.lineTo(ox+(cx+.5)*dw/iw,oy+dh);ctx.moveTo(ox,oy+(cy+.5)*dh/ih);ctx.lineTo(ox+dw,oy+(cy+.5)*dh/ih);ctx.stroke();
  const target=Math.min(iw*px,w/scale)/4,power=10**Math.floor(Math.log10(target)),bar=[1,2,5,10].map(v=>v*power).filter(v=>v<=target).at(-1)||power;ctx.strokeStyle='#f0f6f8';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(14,h-17);ctx.lineTo(14+bar*scale,h-17);ctx.stroke();ctx.fillStyle='#f0f6f8';ctx.font='11px system-ui';ctx.fillText(Number(bar.toPrecision(3))+' '+(data.calibrated?'µm':'px'),14,h-24);
  const depth=axis==='xz'||axis==='yz',title=axis==='raw'?'Raw source · XY':(axis==='xy'?'Result · XY':axis.toUpperCase()+' · '+(axis==='xz'?'Y '+y:'X '+x));frame.querySelector('.review-plane-title').textContent=title+(depth?' · '+(reviewState.depthScale===1?'physical proportions':'Z expanded ×'+reviewState.depthScale):' · Z '+(z+1)+' / '+data.shape[0]);
 }
}
new ResizeObserver(()=>{if(state.tab==='Review')drawReviewCanvases()}).observe($('#desk'));
