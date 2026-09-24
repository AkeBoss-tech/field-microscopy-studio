'use strict';
state.showGrid=false;state.showScaleBar=true;
document.querySelector('[data-mode="volume"]').title='Smooth 3D overview from acquired planes. Use native 2D slices to judge exact cell boundaries.';
const displayGuideBody=document.querySelector('.display-menu .dropdown-body');
for(const [key,label,help] of [['showGrid','▦ Grid','Show a spatial grid in 2D or a bounding frame in 3D. Guides are included in Save view.'],['showScaleBar','↔ Scale bar','Show a calibrated micrometer scale when the source spacing is known. Guides are included in Save view.']]){
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
 const calibrated=state.meta?.calibrated!==false,[sx,sy]=state.meta.spacing;
 if(state.showGrid){
  const unitX=calibrated?sx:1,unitY=calibrated?sy:1,step=niceDistance(95*unitX/s),xStep=step/unitX,yStep=step/unitY;
  ctx.save();ctx.beginPath();ctx.rect(ox,oy,iw*s,ih*s);ctx.clip();ctx.strokeStyle='#e8f8ff48';ctx.lineWidth=1;
  for(let x=0;x<iw;x+=xStep){const xx=ox+x*s;ctx.beginPath();ctx.moveTo(xx,oy);ctx.lineTo(xx,oy+ih*s);ctx.stroke()}
  for(let y=0;y<ih;y+=yStep){const yy=oy+y*s;ctx.beginPath();ctx.moveTo(ox,yy);ctx.lineTo(ox+iw*s,yy);ctx.stroke()}
  ctx.restore();
 }
 if(calibrated)drawScale(ctx,w,h,s/sx,'µm');
}
function drawGuides3D(ctx,w,h,project,bounds,scale){
 const [[x0,y0,z0],[x1,y1,z1]]=bounds,calibrated=state.meta?.calibrated!==false;
 if(state.showGrid){
  const vertices=[[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]].map(p=>project(...p));
  ctx.save();ctx.lineWidth=1;ctx.strokeStyle='#d0e8fb72';ctx.fillStyle='#dcecf9';ctx.font='11px system-ui';
  for(const [a,b] of [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]){ctx.beginPath();ctx.moveTo(...vertices[a].slice(0,2));ctx.lineTo(...vertices[b].slice(0,2));ctx.stroke()}
  const unit=calibrated?'µm':'px';ctx.fillText('X '+((x1-x0)*(calibrated?state.meta.spacing[0]:1)).toFixed(0)+' '+unit,vertices[1][0]+5,vertices[1][1]);ctx.fillText('Y',vertices[3][0]+5,vertices[3][1]);ctx.fillText('Z',vertices[4][0]+5,vertices[4][1]);ctx.restore();
 }
 if(calibrated)drawScale(ctx,w,h,scale,'µm');
}
