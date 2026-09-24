'use strict';
// Temporary display measurement. It never creates or edits a scientific annotation.
state.rulerEnabled=false;
state.rulerMeasurement=null;

const rulerButton=document.createElement('button');
rulerButton.className='explore-tool-button';
rulerButton.innerHTML='<span aria-hidden="true">⤡</span><span class="explore-tool-label"> Ruler</span>';
rulerButton.title='Measure between two points in 2D or 3D. Click twice or drag; 3D endpoints snap to sampled signal in the active channel.';
rulerButton.setAttribute('aria-label','Ruler tool');
rulerButton.setAttribute('aria-pressed','false');
rulerButton.onclick=()=>{state.rulerEnabled=!state.rulerEnabled;rulerButton.setAttribute('aria-pressed',String(state.rulerEnabled));rulerButton.classList.toggle('active',state.rulerEnabled);refreshRulerUI()};

const gridGuideButton=document.createElement('button');
gridGuideButton.className='explore-tool-button';
gridGuideButton.innerHTML='<span aria-hidden="true">▦</span><span class="explore-tool-label"> Grid</span>';
gridGuideButton.setAttribute('aria-label','Toggle spatial grid');
gridGuideButton.title='Show a spatial grid in 2D or on the 3D XY reference plane. Included in Save view.';
gridGuideButton.onclick=()=>setExploreGuide('showGrid',!state.showGrid);

const scaleGuideButton=document.createElement('button');
scaleGuideButton.className='explore-tool-button';
scaleGuideButton.innerHTML='<span aria-hidden="true">↔</span><span class="explore-tool-label"> Scale</span>';
scaleGuideButton.setAttribute('aria-label','Toggle scale bar');
scaleGuideButton.title='Show a micrometer scale bar when image spacing is known. Included in Save view.';
scaleGuideButton.onclick=()=>setExploreGuide('showScaleBar',!state.showScaleBar);

const rulerReadout=document.createElement('output');
rulerReadout.className='ruler-readout';
rulerReadout.setAttribute('aria-label','Ruler distance');
rulerReadout.setAttribute('aria-live','polite');
const clearRulerButton=document.createElement('button');
clearRulerButton.className='explore-tool-button ruler-clear';
clearRulerButton.textContent='×';
clearRulerButton.setAttribute('aria-label','Clear ruler');
clearRulerButton.title='Clear the current ruler measurement';
clearRulerButton.onclick=()=>{state.rulerMeasurement=null;refreshRulerUI();scheduleDraw()};
for(const control of [rulerButton,gridGuideButton,scaleGuideButton,rulerReadout,clearRulerButton])$('#simple-toolbar').insertBefore(control,regionButton);

function setExploreGuide(key,value){
 state[key]=value;
 const label=key==='showGrid'?'▦ Grid':'↔ Scale bar';
 const checkbox=document.querySelector('.display-menu input[aria-label="'+label+'"]');
 if(checkbox)checkbox.checked=value;
 syncExploreGuides();scheduleDraw();
}
function syncExploreGuides(){
 for(const [button,value] of [[gridGuideButton,state.showGrid],[scaleGuideButton,state.showScaleBar]]){
  button.classList.toggle('active',!!value);
  button.setAttribute('aria-pressed',String(!!value));
 }
 scaleGuideButton.disabled=!!state.meta&&state.meta.calibrated!==true;
 scaleGuideButton.title=scaleGuideButton.disabled?'This image has no physical spacing metadata; add calibration on import to show a µm scale.':'Show a micrometer scale bar when image spacing is known. Included in Save view.';
}
document.querySelectorAll('.display-menu input[aria-label="▦ Grid"],.display-menu input[aria-label="↔ Scale bar"]').forEach(input=>input.addEventListener('change',syncExploreGuides));

function rulerContext(v){
 const kind=v.dataset.kind;
 return [state.dataset,state.channel,kind,kind==='slice'?state.z:'',kind==='volume'?(state.region3d||[]).join(','):'',kind==='volume'?(state.focusObject?.run||'')+':'+(state.focusObject?.id||''):''].join('|');
}
function rulerDistance(points,kind){
 const calibrated=state.meta?.calibrated===true,spacing=calibrated?(state.meta?.spacing||[1,1,1]):[1,1,1];
 const [a,b]=points,dx=(b[0]-a[0])*spacing[0],dy=(b[1]-a[1])*spacing[1],dz=kind==='volume'?(b[2]-a[2])*spacing[2]:0;
 return {length:Math.hypot(dx,dy,dz),xy:Math.hypot(dx,dy),z:Math.abs(dz),unit:calibrated?'µm':kind==='volume'?'voxel units':'px'};
}
function rulerDescription(measurement){
 const {length,xy,z,unit}=rulerDistance(measurement.points,measurement.kind);
 const prefix=measurement.kind==='projection'?'Projected XY':measurement.kind==='slice'?'Slice XY':'3D sampled points';
 return `${prefix}: ${length.toFixed(2)} ${unit}`+(measurement.kind==='volume'?` · XY ${xy.toFixed(2)}, ΔZ ${z.toFixed(2)} ${unit} · planes ${Math.round(measurement.points[0][2])+1}→${Math.round(measurement.points[1][2])+1}`:'');
}
function refreshRulerUI(){
 const v=$('#main-host .viewport'),measurement=state.rulerMeasurement,valid=v&&measurement?.key===rulerContext(v);
 rulerReadout.textContent=valid?(measurement.points.length===2?rulerDescription(measurement):'First point set · choose the second point'):state.rulerEnabled?'Click two points or drag on the image':'';
 rulerReadout.title=rulerReadout.textContent;
 rulerReadout.hidden=!rulerReadout.textContent;
 clearRulerButton.hidden=!valid;
 syncExploreGuides();
 for(const c of document.querySelectorAll('#main-host .viewport canvas'))c.style.cursor=state.rulerEnabled&&state.tab==='Explore'?'crosshair':'grab';
}
function rulerPick(v,event){
 return v.dataset.kind==='volume'?volumePoint(v,event):nativePoint(v,event);
}
function placeRulerPoint(v,point,first=null){
 if(!point){status(v.dataset.kind==='volume'?'Choose visible signal in the active channel; rotate to check its depth.':'Choose a point inside the image.',true);return}
 const key=rulerContext(v),current=state.rulerMeasurement;
 if(first){state.rulerMeasurement={key,kind:v.dataset.kind,points:[first,point]}}
 else if(!current||current.key!==key||current.points.length===2)state.rulerMeasurement={key,kind:v.dataset.kind,points:[point]};
 else current.points.push(point);
 refreshRulerUI();scheduleDraw();
 if(state.rulerMeasurement.points.length===2)status(rulerDescription(state.rulerMeasurement)+(v.dataset.kind==='volume'?' · inspect both Z anchors in 2D before relying on depth':''));
}
const rulerBindCanvas=bindCanvas;
bindCanvas=function(v){
 rulerBindCanvas(v);
 const c=v.querySelector('canvas'),down=c.onpointerdown,move=c.onpointermove,up=c.onpointerup,cancel=c.onpointercancel;
 let start=null;
 const measuring=()=>state.tab==='Explore'&&state.rulerEnabled;
 c.onpointerdown=e=>{
  if(!measuring()||e.button!==0||e.shiftKey){down(e);return}
  start={x:e.clientX,y:e.clientY,point:rulerPick(v,e)};
  c.focus({preventScroll:true});c.setPointerCapture(e.pointerId);
 };
 c.onpointermove=e=>{if(start){if(Math.hypot(e.clientX-start.x,e.clientY-start.y)>4){start.moved=true;start.lastPoint=rulerPick(v,e)}return}move(e)};
 c.onpointerup=e=>{
  if(!start){up(e);return}
  const anchor=start;start=null;
  const dragged=anchor.moved||Math.hypot(e.clientX-anchor.x,e.clientY-anchor.y)>4;
  placeRulerPoint(v,anchor.lastPoint||rulerPick(v,e),dragged?anchor.point:null);
 };
 c.onpointercancel=e=>{start=null;cancel?.(e)};
};

function drawRulerOverlay(v){
 const m=state.rulerMeasurement,c=v.querySelector('canvas');
 if(state.tab!=='Explore'||!m||m.key!==rulerContext(v)||!c.width)return;
 const positions=m.points.map(p=>v.dataset.kind==='volume'?v.project?.(p[0],p[1],p[2]):v.transform?[v.transform.ox+p[0]*v.transform.s,v.transform.oy+p[1]*v.transform.s]:null);
 if(positions.some(p=>!p))return;
 const ctx=c.getContext('2d');ctx.save();ctx.setTransform(c.width/c.clientWidth,0,0,c.height/c.clientHeight,0,0);
 if(positions.length===2){
  const [a,b]=positions;ctx.lineCap='round';ctx.strokeStyle='#071318';ctx.lineWidth=6;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();ctx.strokeStyle='#ffd36e';ctx.lineWidth=3;ctx.stroke();
  const label=rulerDistance(m.points,m.kind),text=label.length.toFixed(2)+' '+label.unit,middle=[(a[0]+b[0])/2,(a[1]+b[1])/2];
  ctx.font='bold 12px system-ui';const width=ctx.measureText(text).width+16,x=Math.max(5,Math.min(c.clientWidth-width-5,middle[0]-width/2)),y=Math.max(25,Math.min(c.clientHeight-8,middle[1]-10));
  ctx.fillStyle='#102128';ctx.fillRect(x,y-19,width,24);ctx.fillStyle='#ffe29b';ctx.textAlign='center';ctx.fillText(text,x+width/2,y-3);
 }
 for(const [x,y] of positions){ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fillStyle='#ffd36e';ctx.fill();ctx.strokeStyle='#071318';ctx.lineWidth=2;ctx.stroke()}
 ctx.restore();
}
const rulerDraw=draw;
draw=async function(v){const expected=(v.ticket||0)+1;await rulerDraw(v);if(v.isConnected&&v.ticket===expected)drawRulerOverlay(v)};
const rulerLayout=renderLayout;
renderLayout=function(){rulerLayout();const visible=state.tab==='Explore';for(const control of [rulerButton,gridGuideButton,scaleGuideButton,rulerReadout,clearRulerButton])control.hidden=!visible;refreshRulerUI()};
refreshRulerUI();
