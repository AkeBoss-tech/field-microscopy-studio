'use strict';
// Per-channel, display-only settings. Source voxels and algorithm inputs are unchanged.
state.channelDisplay='color';
const channelPalette=['#00ff70','#4080ff','#ff405c','#ef50ff','#00e5ff','#ffcc40'];
const zenPalette=['#ef50ff','#ff6049','#47db76','#5887ff'];
const channelStyles=new Map(),tintedImages=new Map(),histogramCache=new Map();
function channelSettings(){
 const key=state.dataset;
 if(!channelStyles.has(key)){
  let saved;try{saved=JSON.parse(localStorage.getItem('field-colors:'+key)||'null')}catch{}
  const palette=state.meta?.channels.length===4?zenPalette:channelPalette;
  channelStyles.set(key,(state.meta?.channels||[]).map((name,i)=>({color:saved?.[i]?.color||palette[i%palette.length],visible:saved?.[i]?.visible!==false,brightness:saved?.[i]?.brightness??100,contrast:saved?.[i]?.contrast??100,background:saved?.[i]?.background||'off',blackPoint:saved?.[i]?.blackPoint??0,whitePoint:saved?.[i]?.whitePoint??255})));
 }
 return channelStyles.get(key);
}
function channelRGB(index){const color=state.channelDisplay==='gray'?'#ffffff':channelSettings()[index]?.color||'#ffffff';return [1,3,5].map(i=>parseInt(color.slice(i,i+2),16))}
function displayChannels(){return state.channelDisplay==='composite'?channelSettings().flatMap((c,i)=>c.visible||i===state.channel?[i]:[]):[state.channel]}
function colorDescription(){return state.channelDisplay==='composite'?'channel composite · active C'+(state.channel+1):state.channelDisplay==='gray'?'grayscale':'channel color'}
async function channelBitmap(url,index){
 const setting=channelSettings()[index],rgb=channelRGB(index);
 const key=url+':'+rgb.join(',')+':'+[setting.brightness,setting.contrast,setting.blackPoint,setting.whitePoint].join(':');
 if(tintedImages.has(key))return tintedImages.get(key);
 const im=await bitmap(url),canvas=document.createElement('canvas');canvas.width=im.width;canvas.height=im.height;
 const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(im,0,0);
 const pixels=ctx.getImageData(0,0,canvas.width,canvas.height),data=pixels.data;
 const low=setting.blackPoint,high=Math.max(low+1,setting.whitePoint),lut=new Uint8Array(256);
 for(let i=0;i<256;i++)lut[i]=Math.round(Math.max(0,Math.min(255,((Math.max(0,Math.min(255,(i-low)/(high-low)*255))*setting.brightness/100)-127.5)*setting.contrast/100+127.5)));
 for(let i=0;i<data.length;i+=4){const value=lut[data[i]];data[i]=value*rgb[0]/255;data[i+1]=value*rgb[1]/255;data[i+2]=value*rgb[2]/255;data[i+3]=255}
 ctx.putImageData(pixels,0,0);tintedImages.set(key,canvas);if(tintedImages.size>20)tintedImages.delete(tintedImages.keys().next().value);return canvas;
}
async function channelPoints(run,overlay){
 const active=state.channel,focus=state.focusObject,channels=focus?[active]:displayChannels();
 const rows=await Promise.all(channels.map(async channel=>{const setting=channelSettings()[channel];const key=query({dataset:state.dataset,channel,run:channel===active?run:'',kind:state.image==='ridge-response'?'ridge-response':'processed',overlay:channel===active?(focus?.run||overlay):'',object:channel===active?focus?.id:'',bounds:focus?'':state.region3d?.join(','),background:setting.background});if(!pointCache.has(key)){if(pointCache.size>=10)pointCache.delete(pointCache.keys().next().value);pointCache.set(key,api('/api/points?'+key))}return {channel,data:await pointCache.get(key),rgb:channelRGB(channel),setting}}));
 const selected=rows.find(row=>row.channel===active);return {...selected.data,activePoints:selected.data.points,points:rows.flatMap(row=>row.data.points.map(p=>[...p,row.rgb,row.channel]))};
}
function saveChannels(){try{localStorage.setItem('field-colors:'+state.dataset,JSON.stringify(channelSettings()))}catch{}scheduleDraw()}
function histogramUrl(index){
 const kind=state.mode==='slice'?'slice':'projection',run=state.image!=='raw'&&index===state.channel&&canShow(runMeta(),kind)?state.run:'';
 return '/api/image?'+query({dataset:state.dataset,channel:index,z:kind==='slice'?state.z:0,view:kind,run,kind:state.image==='ridge-response'?'ridge-response':'processed',projection:state.projection,background:channelSettings()[index].background});
}
async function displayHistogram(index,canvas,update){
 const url=histogramUrl(index);try{
  if(!histogramCache.has(url)){
   if(histogramCache.size>=18)histogramCache.delete(histogramCache.keys().next().value);
   histogramCache.set(url,(async()=>{const image=await bitmap(url),scratch=document.createElement('canvas');scratch.width=image.width;scratch.height=image.height;const context=scratch.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0);const data=context.getImageData(0,0,image.width,image.height).data,bins=new Uint32Array(64);for(let i=0;i<data.length;i+=16)bins[data[i]>>2]++;return bins})());
  }
  const bins=await histogramCache.get(url);if(!canvas.isConnected)return;
  const draw=()=>{const context=canvas.getContext('2d'),width=canvas.width,height=canvas.height,setting=channelSettings()[index],max=Math.max(...bins.map(n=>Math.log1p(n)));context.clearRect(0,0,width,height);context.fillStyle='#0a1821';context.fillRect(0,0,width,height);
   context.fillStyle=setting.color;for(let b=0;b<64;b++){const bar=Math.log1p(bins[b])/Math.max(1,max)*(height-8);context.fillRect(b*width/64,height-bar,width/64+.3,bar)}
   context.fillStyle='#081018b8';context.fillRect(0,0,setting.blackPoint/255*width,height);context.fillRect(setting.whitePoint/255*width,0,width-setting.whitePoint/255*width,height);
   context.strokeStyle='#ffffff';context.lineWidth=2;for(const x of [setting.blackPoint,setting.whitePoint]){context.beginPath();context.moveTo(x/255*width,0);context.lineTo(x/255*width,height);context.stroke()}}
  update.draw=draw;draw();
 }catch(error){if(canvas.isConnected)canvas.setAttribute('aria-label','Histogram unavailable: '+error.message)}
}
const channelMenu=fieldMenu('Channels','channels-menu',[], $('#simple-toolbar')),channelBody=channelMenu.querySelector('.dropdown-body');
function refreshChannelMenu(){
 if(!state.meta||!channelMenu.open)return;
 if(channelBody.dataset.dataset===state.dataset)return;
 channelBody.dataset.dataset=state.dataset;channelBody.replaceChildren();
 const label=document.createElement('label');label.textContent='Display mode';const select=document.createElement('select');select.setAttribute('aria-label','Channel display mode');for(const [value,text] of [['color','Selected channel · color'],['composite','Combined channels'],['gray','Selected channel · gray']])select.add(new Option(text,value));select.value=state.channelDisplay;select.onchange=()=>{state.channelDisplay=select.value;scheduleDraw()};label.append(select);channelBody.append(label);
 channelSettings().forEach((setting,i)=>{
  const row=document.createElement('div');row.className='channel-color-row';const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=setting.visible||i===state.channel;toggle.disabled=i===state.channel;toggle.setAttribute('aria-label','Show channel '+(i+1)+' in composite');
  const name=document.createElement('span');name.textContent='C'+(i+1)+' · '+state.meta.channels[i]+(i===state.channel?' (active)':'');
  const color=document.createElement('input');color.type='color';color.value=setting.color;color.setAttribute('aria-label','Channel '+(i+1)+' color');toggle.onchange=()=>{setting.visible=toggle.checked;saveChannels()};color.oninput=()=>{setting.color=color.value;saveChannels()};row.append(toggle,name,color);channelBody.append(row);
  const details=document.createElement('div');details.className='channel-adjust';
  for(const [key,labelText] of [['brightness','☀ Brightness'],['contrast','◐ Contrast']]){const field=document.createElement('label');field.textContent=labelText;field.title='Display only; source values and algorithms are unchanged';const slider=document.createElement('input');slider.type='range';slider.min=key==='brightness'?20:50;slider.max=key==='brightness'?250:300;slider.value=setting[key];slider.setAttribute('aria-label',`Channel ${i+1} ${key}`);const output=document.createElement('output');output.textContent=setting[key]+'%';slider.oninput=()=>{setting[key]=+slider.value;output.textContent=slider.value+'%';saveChannels()};field.append(slider,output);details.append(field)}
  const histogram=document.createElement('canvas');histogram.className='channel-histogram';histogram.width=250;histogram.height=72;histogram.setAttribute('role','img');histogram.setAttribute('aria-label',`Channel ${i+1} display histogram with black and white window markers`);histogram.title='Auto-scaled display histogram. Drag the black or white marker to adjust the display window.';details.append(histogram);
  const update={draw:()=>{}};for(const [key,text,min,max] of [['blackPoint','Black',0,254],['whitePoint','White',1,255]]){const field=document.createElement('label');field.textContent=text;const slider=document.createElement('input');slider.type='range';slider.min=min;slider.max=max;slider.value=setting[key];slider.setAttribute('aria-label',`Channel ${i+1} ${text.toLowerCase()} point`);const output=document.createElement('output');output.textContent=setting[key];slider.oninput=()=>{setting[key]=Math.max(key==='blackPoint'?0:setting.blackPoint+1,Math.min(key==='blackPoint'?setting.whitePoint-1:255,+slider.value));slider.value=setting[key];output.textContent=setting[key];update.draw();saveChannels()};field.append(slider,output);details.append(field)}
  let dragging=null;histogram.onpointerdown=e=>{const x=(e.clientX-histogram.getBoundingClientRect().left)/histogram.clientWidth*255;dragging=Math.abs(x-setting.blackPoint)<Math.abs(x-setting.whitePoint)?'blackPoint':'whitePoint';histogram.setPointerCapture(e.pointerId);histogram.onpointermove=move=>{if(!dragging)return;const value=Math.round((move.clientX-histogram.getBoundingClientRect().left)/histogram.clientWidth*255);setting[dragging]=Math.max(dragging==='blackPoint'?0:setting.blackPoint+1,Math.min(dragging==='blackPoint'?setting.whitePoint-1:255,value));const slider=details.querySelector(`[aria-label="Channel ${i+1} ${dragging==='blackPoint'?'black':'white'} point"]`);slider.value=setting[dragging];slider.nextSibling.textContent=setting[dragging];update.draw();saveChannels()}};histogram.onpointerup=()=>dragging=null;histogram.onpointercancel=()=>dragging=null;
  const bg=document.createElement('label');bg.textContent='Background';bg.title='Subtract a smooth local background from the view only';const bgSelect=document.createElement('select');bgSelect.setAttribute('aria-label',`Channel ${i+1} background`);bgSelect.add(new Option('Off','off'));bgSelect.add(new Option('Local subtraction','local'));bgSelect.value=setting.background;bgSelect.onchange=()=>{setting.background=bgSelect.value;saveChannels();displayHistogram(i,histogram,update)};bg.append(bgSelect);details.append(bg);channelBody.append(details);displayHistogram(i,histogram,update);
 });
 const note=document.createElement('p');note.className='muted';note.textContent='Histogram shows auto-scaled display values; controls change display only. Original pixels, processing and masks remain unchanged.';channelBody.append(note);
}
channelMenu.addEventListener('toggle',()=>{if(channelMenu.open){channelBody.dataset.dataset='';refreshChannelMenu()}});
const channelDraw=scheduleDraw;scheduleDraw=function(){if(state.meta)refreshChannelMenu();channelDraw()};
