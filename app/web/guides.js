'use strict';
state.showGrid=false;state.showScaleBar=true;
document.querySelector('[data-mode="volume"]').title='Smooth 3D overview from acquired planes. Use native 2D slices to judge exact cell boundaries.';
const displayGuideBody=document.querySelector('.display-menu .dropdown-body');
for(const [key,label,help] of [['showGrid','▦ Grid','Show a spatial grid in 2D or on the 3D XY reference plane. Guides are included in Save view.'],['showScaleBar','↔ Scale bar','Show a calibrated micrometer scale when the source spacing is known. Guides are included in Save view.']]){
 const field=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=state[key];input.setAttribute('aria-label',label);input.onchange=()=>{state[key]=input.checked;scheduleDraw()};field.title=help;field.append(input,document.createTextNode(label));displayGuideBody.append(field);
}
function niceDistance(limit){if(limit<=0)return 1;const power=10**Math.floor(Math.log10(limit));return [5,2,1].map(n=>n*power).find(n=>n<=limit)||power}
function drawScale(ctx,w,h,pixelsPerUnit,unit){
 if(!state.showScaleBar||pixelsPerUnit<=0)return;
 const value=niceDistance(125/pixelsPerUnit),length=value*pixelsPerUnit,x=w-length-23,y=h-39;
 if(x<10)return;
 ctx.save();ctx.lineWidth=3;ctx.strokeStyle='#08151d';ctx.fillStyle='#08151d';ctx.fillRect(x-8,y-26,length+16,36);
 ctx.strokeStyle='#f3fafb';ctx.fillStyle='#f3fafb';ctx.font='12px system-ui';ctx.textAlign='center';ctx.fillText(value+' '+unit,x+length/2,y-9);
 ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+length,y);ctx.moveTo(x,y-5);ctx.lineTo(x,y+5);ctx.moveTo(x+length,y-5);ctx.lineTo(x+length,y+5);ctx.stroke();ctx.restore();
}
function drawGuides2D(ctx,w,h,s,ox,oy,iw,ih){
 const calibrated=state.meta?.calibrated===true,[sx,sy]=state.meta.spacing;
 if(state.showGrid){
  const unitX=calibrated?sx:1,unitY=calibrated?sy:1,step=niceDistance(95*unitX/s),xStep=step/unitX,yStep=step/unitY;
  ctx.save();ctx.beginPath();ctx.rect(ox,oy,iw*s,ih*s);ctx.clip();ctx.strokeStyle='#e8f8ff48';ctx.lineWidth=1;
  for(let x=0;x<iw;x+=xStep){const xx=ox+x*s;ctx.beginPath();ctx.moveTo(xx,oy);ctx.lineTo(xx,oy+ih*s);ctx.stroke()}
  for(let y=0;y<ih;y+=yStep){const yy=oy+y*s;ctx.beginPath();ctx.moveTo(ox,yy);ctx.lineTo(ox+iw*s,yy);ctx.stroke()}
  ctx.restore();
 }
 if(calibrated)drawScale(ctx,w,h,s/sx,'µm');
}
// Calibrated axes box, as in ZEN's 3D view: grid walls on the three far faces (drawn before the
// volume so signal covers them), then box edges, µm tick labels and colored axes in front.
function axesBox(project,bounds){
 const [[x0,y0,z0],[x1,y1,z1]]=bounds,calibrated=state.meta?.calibrated===true,spacing=calibrated?state.meta.spacing:[1,1,1];
 const lo=[x0,y0,z0],hi=[x1,y1,z1],corner=i=>[i&1?x1:x0,i&2?y1:y0,i&4?z1:z0];
 const screen=[...Array(8).keys()].map(i=>project(...corner(i)));
 const center=screen.reduce((a,p)=>[a[0]+p[0]/8,a[1]+p[1]/8],[0,0]);
 // A face is "back" when its centre lies farther from the viewer than the opposite face.
 const back=[0,1,2].map(axis=>{const depth=side=>[...Array(8).keys()].filter(i=>(i>>axis&1)===side).reduce((d,i)=>d+screen[i][2],0);return depth(0)<depth(1)?0:1});
 const edges=[];for(let i=0;i<8;i++)for(let axis=0;axis<3;axis++)if(!(i>>axis&1))edges.push({a:i,b:i|1<<axis,axis});
 for(const e of edges){const others=[0,1,2].filter(k=>k!==e.axis);e.back=others.some(k=>(e.a>>k&1)===back[k])}
 return {lo,hi,spacing,unit:calibrated?'µm':'px',corner,screen,center,back,edges};
}
function drawBackGuides3D(ctx,project,bounds){
 if(!renderSettings().axes&&!state.showGrid)return;
 const box=axesBox(project,bounds);ctx.save();ctx.lineWidth=1;
 if(state.showGrid){
  ctx.strokeStyle='#cfe3f52e';
  for(let axis=0;axis<3;axis++){
   const fixed=box.back[axis]?box.hi[axis]:box.lo[axis];
   for(const along of [0,1,2].filter(k=>k!==axis)){
    const across=[0,1,2].find(k=>k!==axis&&k!==along),step=niceDistance((box.hi[along]-box.lo[along])*box.spacing[along]/6)/box.spacing[along];
    for(let t=Math.ceil(box.lo[along]/step+1e-6)*step,n=0;t<box.hi[along]-1e-6&&n<60;t+=step,n++){
     const a=[0,0,0],b=[0,0,0];a[axis]=b[axis]=fixed;a[along]=b[along]=t;a[across]=box.lo[across];b[across]=box.hi[across];
     const pa=project(...a),pb=project(...b);ctx.beginPath();ctx.moveTo(pa[0],pa[1]);ctx.lineTo(pb[0],pb[1]);ctx.stroke()}
   }
  }
 }
 if(renderSettings().axes){ctx.strokeStyle='#d6e6f461';for(const e of box.edges.filter(e=>e.back)){ctx.beginPath();ctx.moveTo(box.screen[e.a][0],box.screen[e.a][1]);ctx.lineTo(box.screen[e.b][0],box.screen[e.b][1]);ctx.stroke()}}
 ctx.restore();
}
function drawGuides3D(ctx,w,h,project,bounds,scale){
 if(renderSettings().axes){
  const box=axesBox(project,bounds),colors=['#ff6b6b','#5fe08a','#6aa8ff'],names=['X','Y','Z'];
  ctx.save();ctx.lineWidth=1;ctx.strokeStyle='#d6e6f424';
  for(const e of box.edges.filter(e=>!e.back)){ctx.beginPath();ctx.moveTo(box.screen[e.a][0],box.screen[e.a][1]);ctx.lineTo(box.screen[e.b][0],box.screen[e.b][1]);ctx.stroke()}
  ctx.font='11px ui-sans-serif,system-ui';ctx.textBaseline='middle';
  for(let axis=0;axis<3;axis++){
   // Label the outermost silhouette edge for this axis, preferring the lower side of the box.
   let best=null;
   for(const e of box.edges.filter(e=>e.axis===axis)){
    const a=box.screen[e.a],b=box.screen[e.b],length=Math.hypot(b[0]-a[0],b[1]-a[1]),mid=[(a[0]+b[0])/2,(a[1]+b[1])/2];
    const score=Math.hypot(mid[0]-box.center[0],mid[1]-box.center[1])+.35*(mid[1]-box.center[1]);
    if(length>36&&(!best||score>best.score))best={e,a,b,mid,score,length};
   }
   if(!best)continue;
   const out=[best.mid[0]-box.center[0],best.mid[1]-box.center[1]],norm=Math.hypot(...out)||1,ox=out[0]/norm,oy=out[1]/norm;
   ctx.strokeStyle=colors[axis];ctx.globalAlpha=.9;ctx.lineWidth=1.6;ctx.beginPath();ctx.moveTo(best.a[0],best.a[1]);ctx.lineTo(best.b[0],best.b[1]);ctx.stroke();ctx.globalAlpha=1;ctx.lineWidth=1;
   const start=box.corner(best.e.a),span=box.hi[axis]-box.lo[axis],physical=span*box.spacing[axis];
   const step=niceDistance(physical/Math.max(2,Math.min(7,best.length/58)));
   ctx.textAlign=ox<-.35?'right':ox>.35?'left':'center';ctx.fillStyle='#d9e7f2';ctx.strokeStyle='#d9e7f2aa';
   for(let u=Math.ceil(box.lo[axis]*box.spacing[axis]/step-1e-6)*step,n=0;u<=box.hi[axis]*box.spacing[axis]+1e-6&&n<40;u+=step,n++){
    const point=[...start];point[axis]=u/box.spacing[axis];const p=project(...point);
    ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(p[0]+ox*5,p[1]+oy*5);ctx.stroke();
    ctx.fillText(String(Math.round(u*100)/100),p[0]+ox*13,p[1]+oy*13);
   }
   const end=best.b,title=names[axis]+' ('+box.unit+')';ctx.fillStyle=colors[axis];ctx.font='600 11px ui-sans-serif,system-ui';
   ctx.fillText(title,end[0]+ox*30+(best.b[0]-best.a[0])/best.length*12,end[1]+oy*30+(best.b[1]-best.a[1])/best.length*12);ctx.font='11px ui-sans-serif,system-ui';
  }
  ctx.restore();
 }
 if(state.meta?.calibrated===true)drawScale(ctx,w,h,scale,'µm');
}
