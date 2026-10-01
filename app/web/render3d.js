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
