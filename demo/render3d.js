'use strict';
// 3D rendering controls in the style of ZEN's 3D view. Every setting here changes the display only:
// source voxels, processing inputs, masks and measurements are untouched.
const renderModes=[
 ['volume','Volume','Translucent signal accumulated along each viewing ray.'],
 ['maximum','Maximum','Brightest value along each ray. Depth order is lost, so overlapping objects can look joined.'],
 ['surface','Surface','Shaded surface where signal crosses the threshold. A threshold boundary is not a verified cell membrane.'],
 ['mixed','Surface + transparency','Translucent shaded surfaces over faint volume signal, so inner structure stays visible.']
];
const renderDefaults={mode:'volume',threshold:.16,ramp:.4,maxOpacity:.85,quality:'fast',axes:true};
state.render=(()=>{try{return {...renderDefaults,...JSON.parse(localStorage.getItem('field-render-3d')||'{}')}}catch{return {...renderDefaults}}})();
if(!renderModes.some(([key])=>key===state.render.mode))state.render.mode='volume';
function renderSettings(){return state.render}
function saveRenderSettings(){try{localStorage.setItem('field-render-3d',JSON.stringify(state.render))}catch{}}
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');

// Camera presets ease to their target instead of jumping, rendering at preview quality while moving.
function animateCamera(v,yaw,pitch,duration=560){
 const cam=v.camera;stopTurntable();
 if(reducedMotion.matches){cam.yaw=yaw;cam.pitch=pitch;v.syncTilt?.();scheduleDraw();return}
 const fromYaw=cam.yaw,fromPitch=cam.pitch,deltaYaw=((yaw-fromYaw)%360+540)%360-180,started=performance.now();
 cancelAnimationFrame(cam.tween);
 const step=now=>{
  const t=Math.min(1,(now-started)/duration),e=t<.5?4*t*t*t:1-(-2*t+2)**3/2;
  cam.yaw=fromYaw+deltaYaw*e;cam.pitch=fromPitch+(pitch-fromPitch)*e;v.syncTilt?.();
  if(t<1){cam.movingUntil=performance.now()+120;scheduleDraw();cam.tween=requestAnimationFrame(step)}
  else{cam.yaw=yaw;cam.movingUntil=0;scheduleDraw()}
 };
 cam.tween=requestAnimationFrame(step);
}
let turntable=null;
function stopTurntable(){if(!turntable)return;cancelAnimationFrame(turntable.frame);turntable=null;document.querySelectorAll('.turntable-button').forEach(b=>{b.classList.remove('active');b.setAttribute('aria-pressed','false')})}
function startTurntable(){
 stopTurntable();turntable={last:performance.now()};
 document.querySelectorAll('.turntable-button').forEach(b=>{b.classList.add('active');b.setAttribute('aria-pressed','true')});
 const spin=now=>{
  const views=[...document.querySelectorAll('#main-host .viewport[data-kind="volume"]')];
  if(!turntable||!views.length){stopTurntable();return}
  const dt=Math.min(64,now-turntable.last);turntable.last=now;
  for(const cam of new Set(views.map(v=>v.camera)))cam.yaw=(cam.yaw+dt*.02)%360;
  scheduleDraw();turntable.frame=requestAnimationFrame(spin);
 };
 turntable.frame=requestAnimationFrame(spin);
}

function renderDock(v){
 const dock=document.createElement('div');dock.className='render-dock';
 const modes=document.createElement('div');modes.className='render-modes segmented';modes.setAttribute('role','radiogroup');modes.setAttribute('aria-label','3D rendering mode');
 const pill=document.createElement('span');pill.className='segment-pill';pill.setAttribute('aria-hidden','true');modes.append(pill);
 const note=document.createElement('p');note.className='render-note';
 const buttons=renderModes.map(([key,label,help])=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.title=help;b.dataset.renderMode=key;b.setAttribute('role','radio');
  b.onclick=()=>{state.render.mode=key;saveRenderSettings();syncDocks();scheduleDraw()};modes.append(b);return b});
 const toggle=document.createElement('button');toggle.type='button';toggle.className='render-adjust-toggle';toggle.innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg><span>Adjust</span>';
 toggle.setAttribute('aria-expanded','false');toggle.title='Threshold, ramp, opacity, quality and axes';
 const panel=document.createElement('div');panel.className='render-panel';panel.inert=true;
 toggle.onclick=()=>{const open=!dock.classList.contains('open');dock.classList.toggle('open',open);panel.inert=!open;toggle.setAttribute('aria-expanded',String(open))};
 const slider=(key,label,help,min,max,step,format)=>{
  const field=document.createElement('label');field.className='render-slider';field.title=help;
  const name=document.createElement('span');name.textContent=label;const input=document.createElement('input');input.type='range';input.min=min;input.max=max;input.step=step;input.dataset.renderKey=key;input.setAttribute('aria-label',label);
  const out=document.createElement('output');input.oninput=()=>{state.render[key]=+input.value;out.textContent=format(+input.value);scheduleDraw()};input.onchange=saveRenderSettings;
  field.append(name,input,out);panel.append(field);return {input,out,format,key};
 };
 const sliders=[
  slider('threshold','Threshold','Display values below this stay transparent. Surface modes draw their surface at this level.',0,.95,.01,v=>Math.round(v*100)+'%'),
  slider('ramp','Ramp','How quickly signal goes from transparent to opaque above the threshold.',.01,1,.01,v=>Math.round(v*100)+'%'),
  slider('maxOpacity','Max opacity','Opacity reached by the brightest signal.',.05,1,.01,v=>Math.round(v*100)+'%')
 ];
 const qualityRow=document.createElement('div');qualityRow.className='render-row';const qualityLabel=document.createElement('span');qualityLabel.textContent='Quality';
 const quality=document.createElement('div');quality.className='segmented small';quality.setAttribute('role','radiogroup');quality.setAttribute('aria-label','3D render quality');
 const qpill=document.createElement('span');qpill.className='segment-pill';qpill.setAttribute('aria-hidden','true');quality.append(qpill);
 const qualityButtons=[['fast','Fast','Up to 256 sampled XY positions per plane; quick to load and rotate.'],['precise','Precise','Up to 512 sampled XY positions per plane and twice the samples per ray. Slower to load.']].map(([key,label,help])=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.title=help;b.dataset.quality=key;b.setAttribute('role','radio');b.onclick=()=>{if(state.render.quality===key)return;state.render.quality=key;saveRenderSettings();syncDocks();status(key==='precise'?'Precise 3D: up to 512 sampled XY positions per plane':'Fast 3D: up to 256 sampled XY positions per plane');scheduleDraw()};quality.append(b);return b});
 qualityRow.append(qualityLabel,quality);panel.append(qualityRow);
 const axesRow=document.createElement('label');axesRow.className='render-check';const axes=document.createElement('input');axes.type='checkbox';axes.onchange=()=>{state.render.axes=axes.checked;saveRenderSettings();scheduleDraw()};axesRow.append(axes,document.createTextNode('Axes box with µm ticks'));panel.append(axesRow);
 const footer=document.createElement('div');footer.className='render-row';
 const reset=document.createElement('button');reset.type='button';reset.className='render-reset';reset.textContent='Reset';reset.title='Restore default render settings for this mode';reset.onclick=()=>{Object.assign(state.render,{threshold:renderDefaults.threshold,ramp:renderDefaults.ramp,maxOpacity:renderDefaults.maxOpacity});saveRenderSettings();syncDocks();scheduleDraw()};
 const honesty=document.createElement('span');honesty.className='render-fine';honesty.textContent='Display only · source data unchanged';footer.append(honesty,reset);panel.append(note,footer);
 dock.append(modes,toggle,panel);
 dock.sync=()=>{
  for(const b of buttons){const on=b.dataset.renderMode===state.render.mode;b.classList.toggle('active',on);b.setAttribute('aria-checked',String(on))}
  for(const b of qualityButtons){const on=b.dataset.quality===state.render.quality;b.classList.toggle('active',on);b.setAttribute('aria-checked',String(on))}
  for(const s of sliders){s.input.value=state.render[s.key];s.out.textContent=s.format(state.render[s.key])}
  axes.checked=!!state.render.axes;
  note.textContent=renderModes.find(([key])=>key===state.render.mode)[2];
  sliders[1].input.closest('label').classList.toggle('dimmed',state.render.mode==='surface');
  requestAnimationFrame(()=>{movePill(modes);movePill(quality)});
 };
 dock.addEventListener('pointerdown',e=>e.stopPropagation());dock.addEventListener('wheel',e=>e.stopPropagation(),{passive:true});
 v.append(dock);dock.sync();new ResizeObserver(()=>{movePill(modes);movePill(quality)}).observe(modes);
}
function syncDocks(){document.querySelectorAll('.render-dock').forEach(d=>d.sync())}
// Shared sliding highlight for segmented controls.
function movePill(group){
 const pill=group?.querySelector(':scope>.segment-pill'),active=group?.querySelector(':scope>button.active');
 if(!pill)return;if(!active||!active.offsetWidth){pill.style.opacity=0;return}
 pill.style.opacity=1;pill.style.width=active.offsetWidth+'px';pill.style.height=active.offsetHeight+'px';pill.style.transform=`translate(${active.offsetLeft}px,${active.offsetTop}px)`;
}

const render3dNavigation=navigation;
navigation=function(v,key){
 render3dNavigation(v,key);
 if(v.dataset.kind!=='volume')return;
 const controls=v.querySelector('.view-navigation'),spin=document.createElement('button');
 spin.className='turntable-button'+(turntable?' active':'');spin.textContent='⟳ Turntable';spin.title='Rotate the volume continuously. Drag or press again to stop.';spin.setAttribute('aria-pressed',String(!!turntable));
 spin.onclick=()=>turntable?stopTurntable():startTurntable();
 controls.querySelector('label')?.before(spin);
 v.querySelector('canvas').addEventListener('pointerdown',stopTurntable);
 renderDock(v);
};
const render3dLayout=renderLayout;
renderLayout=function(){const before=state.tab+':'+state.mode;render3dLayout();if(turntable&&(state.tab!=='Explore'||state.mode!=='volume'||before!==state.tab+':'+state.mode))stopTurntable()};

// ---- Single-cell view: neighbours and cell-to-cell navigation ----
state.focusView=(()=>{try{return {neighbors:'dim',context:8,...JSON.parse(localStorage.getItem('field-focus-view')||'{}')}}catch{return {neighbors:'dim',context:8}}})();
function focusContext(){const f=state.focusView;return {neighbors:f.neighbors,context:f.neighbors==='isolate'?0:f.context}}
function saveFocusView(){try{localStorage.setItem('field-focus-view',JSON.stringify(state.focusView))}catch{}}
const objectIndexCache=new Map();
function objectIndex(run){if(!objectIndexCache.has(run))objectIndexCache.set(run,api('/api/object-index?'+query({run})).catch(error=>{objectIndexCache.delete(run);throw error}));return objectIndexCache.get(run)}
function focusCell(id){if(!state.focusObject)return;state.focusObject={run:state.focusObject.run,id};state.clip=null;renderLayout();status('Showing candidate #'+id+' · '+{isolate:'neighbours hidden',dim:'neighbours dimmed',full:'raw context shown'}[state.focusView.neighbors])}
function cellNavigator(v){
 const card=document.createElement('section');card.className='float-card cell-navigator';card.setAttribute('aria-label','Selected cell');
 const head=document.createElement('div');head.className='float-card-head';const title=document.createElement('h3');title.textContent='Cell #'+state.focusObject.id;const position=document.createElement('span');position.className='float-card-meta';head.append(title,position);
 const steps=document.createElement('div');steps.className='cell-steps';
 const prev=document.createElement('button');prev.type='button';prev.textContent='‹ Previous';prev.title='Previous candidate ID';
 const next=document.createElement('button');next.type='button';next.textContent='Next ›';next.title='Next candidate ID';
 const go=document.createElement('form');go.className='cell-go';const idInput=document.createElement('input');idInput.type='number';idInput.min=1;idInput.placeholder='ID';idInput.setAttribute('aria-label','Go to candidate ID');const goButton=document.createElement('button');goButton.textContent='Go';go.append(idInput,goButton);
 steps.append(prev,next,go);
 const nearLabel=document.createElement('p');nearLabel.className='float-card-label';nearLabel.textContent='Nearest neighbours';
 const near=document.createElement('div');near.className='neighbor-chips';near.textContent='Loading…';
 const modeLabel=document.createElement('p');modeLabel.className='float-card-label';modeLabel.textContent='Show neighbours';
 const modes=document.createElement('div');modes.className='segmented small';modes.setAttribute('role','radiogroup');modes.setAttribute('aria-label','Neighbour display');
 const pill=document.createElement('span');pill.className='segment-pill';pill.setAttribute('aria-hidden','true');modes.append(pill);
 const modeButtons=[['isolate','Hidden','Only this candidate’s mask'],['dim','Dimmed','Surrounding signal stays faint so this cell stands out'],['full','Shown','Raw signal around the cell at full brightness']].map(([key,label,help])=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.title=help;b.setAttribute('role','radio');const on=state.focusView.neighbors===key;b.classList.toggle('active',on);b.setAttribute('aria-checked',String(on));b.onclick=()=>{state.focusView.neighbors=key;saveFocusView();state.clip=null;renderLayout()};modes.append(b);return b});
 const contextField=document.createElement('label');contextField.className='render-slider';contextField.title='Distance around the cell to include';const contextName=document.createElement('span');contextName.textContent='Context';const contextInput=document.createElement('input');contextInput.type='range';contextInput.min=2;contextInput.max=40;contextInput.step=1;contextInput.value=state.focusView.context;contextInput.setAttribute('aria-label','Context around the cell in micrometres');const contextOut=document.createElement('output');contextOut.textContent=state.focusView.context+' µm';
 contextInput.oninput=()=>contextOut.textContent=contextInput.value+' µm';contextInput.onchange=()=>{state.focusView.context=+contextInput.value;saveFocusView();state.clip=null;renderLayout()};contextField.append(contextName,contextInput,contextOut);contextField.hidden=state.focusView.neighbors==='isolate';
 const actions=document.createElement('div');actions.className='cell-actions';
 const planes=document.createElement('button');planes.type='button';planes.textContent='Inspect in planes';planes.title='Open this candidate in Review: XY, XZ and YZ';
 const back=document.createElement('button');back.type='button';back.textContent='Full field';back.title='Leave the single-cell view';back.onclick=()=>{state.focusObject=null;state.clip=null;renderLayout()};
 actions.append(planes,back);
 card.append(head,steps,modeLabel,modes,contextField,nearLabel,near,actions);
 card.addEventListener('pointerdown',e=>e.stopPropagation());card.addEventListener('wheel',e=>e.stopPropagation(),{passive:true});
 requestAnimationFrame(()=>movePill(modes));
 objectIndex(state.focusObject.run).then(index=>{
  if(!card.isConnected)return;const ids=index.objects.map(o=>o.id),current=index.objects.find(o=>o.id===state.focusObject.id),at=ids.indexOf(state.focusObject.id);
  if(current&&state.focusObject){state.focusObject.bounds=current.bounds_native;scheduleDraw()}
  position.textContent=at>=0?(at+1).toLocaleString()+' of '+ids.length.toLocaleString():ids.length.toLocaleString()+' candidates';
  prev.disabled=at<=0;next.disabled=at<0||at>=ids.length-1;prev.onclick=()=>focusCell(ids[at-1]);next.onclick=()=>focusCell(ids[at+1]);
  go.onsubmit=e=>{e.preventDefault();const id=+idInput.value;if(ids.includes(id))focusCell(id);else status('Candidate #'+idInput.value+' is not in the current mask revision',true)};
  const spacing=state.meta.calibrated?state.meta.spacing:[1,1,1],unit=state.meta.calibrated?'µm':'px';
  near.replaceChildren();
  if(current){const ranked=index.objects.filter(o=>o.id!==current.id).map(o=>[o,Math.hypot(...o.center.map((c,i)=>(c-current.center[i])*spacing[i]))]).sort((a,b)=>a[1]-b[1]).slice(0,6);
   for(const [o,distance] of ranked){const chip=document.createElement('button');chip.type='button';chip.className='neighbor-chip';chip.innerHTML='<b>#'+o.id+'</b><span>'+distance.toFixed(1)+' '+unit+'</span>';chip.title='Centre-to-centre distance between bounding boxes';chip.onclick=()=>focusCell(o.id);near.append(chip)}}
  if(!near.children.length)near.textContent='No other candidates';
  planes.onclick=()=>{if(!current)return;state.run=state.focusObject.run;reviewState.x=Math.round(current.center[0]);reviewState.y=Math.round(current.center[1]);state.z=Math.min(state.meta.shape[0]-1,Math.floor(current.center[2]));state.focusObject=null;state.tab='Review';renderLayout()};
 }).catch(error=>{if(card.isConnected){near.textContent=error.message;position.textContent=''}});
 return card;
}

// ---- Region sliders: live clipping, then optionally reload the region at full detail ----
function clipFor(bounds){const key=bounds.flat().join(',');return state.clip&&state.clip.key===key&&['x','y','z'].some(a=>state.clip[a][0]>0||state.clip[a][1]<1)?state.clip:null}
state.cropOpen=false;
function rangeSlider(label,values,onInput){
 const row=document.createElement('div');row.className='range-row';const name=document.createElement('span');name.className='range-name';name.textContent=label;
 const track=document.createElement('div');track.className='dual-range';const fill=document.createElement('span');fill.className='dual-fill';
 const low=document.createElement('input'),high=document.createElement('input');
 for(const [input,value,which] of [[low,values[0],'start'],[high,values[1],'end']]){input.type='range';input.min=0;input.max=1000;input.step=1;input.value=Math.round(value*1000);input.setAttribute('aria-label',label+' '+which)}
 const out=document.createElement('output');out.className='range-out';
 const paint=()=>{fill.style.left=low.value/10+'%';fill.style.right=(100-high.value/10)+'%'};
 const changed=e=>{if(+low.value>+high.value-10){if(e.target===low)low.value=+high.value-10;else high.value=+low.value+10}paint();onInput([low.value/1000,high.value/1000])};
 low.oninput=changed;high.oninput=changed;track.append(fill,low,high);row.append(name,track,out);paint();
 row.set=(a,b,text)=>{low.value=Math.round(a*1000);high.value=Math.round(b*1000);paint();out.textContent=text};row.out=out;return row;
}
function cropPanel(v){
 const card=document.createElement('section');card.className='float-card crop-panel';card.setAttribute('aria-label','3D region');
 const head=document.createElement('div');head.className='float-card-head';const title=document.createElement('h3');title.textContent='3D region';const close=document.createElement('button');close.type='button';close.className='float-card-close';close.textContent='×';close.setAttribute('aria-label','Close region panel');close.onclick=()=>{state.cropOpen=false;card.classList.remove('open');syncRegionButton()};head.append(title,close);
 const hint=document.createElement('p');hint.className='float-card-label';hint.textContent='Drag the handles to crop live. The dashed box marks the region.';
 const spacing=()=>state.meta.calibrated?state.meta.spacing:[1,1,1],unit=()=>state.meta.calibrated?'µm':'px';
 const current=()=>{const b=v.bounds3d;if(!b)return null;const key=b.flat().join(',');if(!state.clip||state.clip.key!==key)state.clip={key,x:[0,1],y:[0,1],z:[0,1]};return b};
 const rows={};
 for(const [axis,label] of [['x','X'],['y','Y'],['z','Z']]){
  rows[axis]=rangeSlider(label,[0,1],values=>{if(!current())return;state.clip[axis]=values;describe();scheduleDraw()});
 }
 const describe=()=>{const b=v.bounds3d;if(!b)return;const s=spacing();['x','y','z'].forEach((axis,i)=>{const lo=b[0][i]+state.clip[axis][0]*(b[1][i]-b[0][i]),hi=b[0][i]+state.clip[axis][1]*(b[1][i]-b[0][i]);rows[axis].set(state.clip[axis][0],state.clip[axis][1],axis==='z'?'planes '+(Math.round(lo)+1)+'–'+Math.round(hi):Math.round(lo*s[i])+'–'+Math.round(hi*s[i])+' '+unit())})};
 card.sync=()=>{if(current())describe()};
 const actions=document.createElement('div');actions.className='cell-actions';
 const reset=document.createElement('button');reset.type='button';reset.textContent='Reset';reset.onclick=()=>{state.clip=null;card.sync();scheduleDraw()};
 const detail=document.createElement('button');detail.type='button';detail.className='primary-action';detail.textContent='Load region in detail';detail.title='Reload only this region so its texture uses all available resolution';
 detail.onclick=()=>{const b=current();if(!b)return;const c=state.clip,pick=(axis,i)=>[Math.floor(b[0][i]+c[axis][0]*(b[1][i]-b[0][i])),Math.ceil(b[0][i]+c[axis][1]*(b[1][i]-b[0][i]))];const [x,y,z]=[pick('x',0),pick('y',1),pick('z',2)];
  if(x[1]-x[0]<2||y[1]-y[0]<2||z[1]<=z[0])return status('Choose a larger region',true);state.region3d=[x[0],y[0],z[0],x[1],y[1],z[1]];state.clip=null;renderLayout();status('Loaded region X '+x.join('–')+', Y '+y.join('–')+', planes '+(z[0]+1)+'–'+z[1])};
 detail.hidden=!!state.focusObject;
 const full=document.createElement('button');full.type='button';full.textContent='Full field';full.hidden=!state.region3d;full.onclick=()=>{state.region3d=null;state.clip=null;renderLayout()};
 actions.append(reset,full,detail);
 card.append(head,hint,rows.x,rows.y,rows.z,actions);
 card.addEventListener('pointerdown',e=>e.stopPropagation());card.addEventListener('wheel',e=>e.stopPropagation(),{passive:true});
 card.classList.toggle('open',state.cropOpen);
 // Bounds are known after the first draw.
 const wait=()=>{if(!card.isConnected)return;if(v.bounds3d)card.sync();else requestAnimationFrame(wait)};wait();
 return card;
}
function syncRegionButton(){const b=document.querySelector('.tool-rail [aria-label="Choose 3D region"]');if(b){b.classList.toggle('active',state.cropOpen&&state.mode==='volume');b.setAttribute('aria-pressed',String(state.cropOpen&&state.mode==='volume'))}}
// The rail's 3D region button opens the slider panel. From 2D, it starts from the visible XY area.
if(typeof regionButton!=='undefined')regionButton.onclick=()=>{
 if(!state.meta)return;
 if(state.mode==='volume'){state.cropOpen=!state.cropOpen;document.querySelectorAll('.crop-panel').forEach(c=>{c.classList.toggle('open',state.cropOpen);if(state.cropOpen)c.sync()});syncRegionButton();return}
 const [nz,,ny,nx]=state.meta.shape,v=$('#main-host .viewport[data-kind="projection"],#main-host .viewport[data-kind="slice"]');
 state.region3d=null;state.focusObject=null;state.clip=null;
 if(v?.transform){const t=v.transform,c=v.querySelector('canvas'),x0=Math.max(0,-t.ox/t.s),y0=Math.max(0,-t.oy/t.s),x1=Math.min(nx,(c.clientWidth-t.ox)/t.s),y1=Math.min(ny,(c.clientHeight-t.oy)/t.s);
  if(x1-x0<nx-1||y1-y0<ny-1)state.clip={key:[0,0,0,nx,ny,nz].join(','),x:[x0/nx,x1/nx],y:[y0/ny,y1/ny],z:[0,1]}}
 state.cropOpen=true;state.mode='volume';renderLayout();
};
const render3dRegionNavigation=navigation;
navigation=function(v,key){
 render3dRegionNavigation(v,key);
 if(v.dataset.kind!=='volume')return;
 const stack=document.createElement('div');stack.className='left-stack';
 if(state.focusObject)stack.append(cellNavigator(v));
 stack.append(cropPanel(v));v.append(stack);
 requestAnimationFrame(syncRegionButton);
};
const render3dDraw=draw;
draw=async function(v){await render3dDraw(v);if(v.dataset.kind==='volume')v.querySelector('.crop-panel')?.sync?.()};
