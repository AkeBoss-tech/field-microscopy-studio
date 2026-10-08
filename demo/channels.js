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
  channelStyles.set(key,(state.meta?.channels||[]).map((name,i)=>({color:saved?.[i]?.color||palette[i%palette.length],visible:saved?.[i]?.visible!==false,included:saved?.[i]?.included!==false,alias:saved?.[i]?.alias||'',role:saved?.[i]?.role||'',brightness:saved?.[i]?.brightness??100,contrast:saved?.[i]?.contrast??100,background:saved?.[i]?.background||'off',blackPoint:saved?.[i]?.blackPoint??0,whitePoint:saved?.[i]?.whitePoint??255})));
 }
 return channelStyles.get(key);
}
function channelRGB(index){const color=state.channelDisplay==='gray'?'#ffffff':channelSettings()[index]?.color||'#ffffff';return [1,3,5].map(i=>parseInt(color.slice(i,i+2),16))}
function displayChannels(){return state.channelDisplay==='composite'?channelSettings().flatMap((c,i)=>c.visible&&c.included||i===state.channel?[i]:[]):[state.channel]}
function channelLabel(index){return channelSettings()[index]?.alias||state.meta?.channels[index]||'Channel '+(index+1)}
function refreshChannelPicker(){if(!state.meta)return;const select=$('#channel'),settings=channelSettings();settings[state.channel].included=true;const rows=settings.flatMap((setting,i)=>setting.included?[new Option((i+1)+' · '+channelLabel(i),i)]:[]);if([...select.options].map(o=>o.value+o.text).join('|')!==rows.map(o=>o.value+o.text).join('|'))select.replaceChildren(...rows);select.value=state.channel}
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
 const rows=await Promise.all(channels.map(async channel=>{const setting=channelSettings()[channel];const key=query({dataset:state.dataset,channel,run:channel===active?run:'',kind:intensityKind(),overlay:channel===active?(focus?.run||overlay):'',object:channel===active?focus?.id:'',context:channel===active&&focus?focusContext().context:'',neighbors:channel===active&&focus?focusContext().neighbors:'',bounds:focus?'':state.region3d?.join(','),background:setting.background});if(!pointCache.has(key)){if(pointCache.size>=10)pointCache.delete(pointCache.keys().next().value);pointCache.set(key,api('/api/points?'+key))}return {channel,data:await pointCache.get(key),rgb:channelRGB(channel),setting}}));
 const selected=rows.find(row=>row.channel===active);return {...selected.data,activePoints:selected.data.points,points:rows.flatMap(row=>row.data.points.map(p=>[...p,row.rgb,row.channel]))};
}
function saveChannels(){try{localStorage.setItem('field-colors:'+state.dataset,JSON.stringify(channelSettings()))}catch{}refreshChannelPicker();scheduleDraw()}
function histogramUrl(index){
 const kind=state.mode==='slice'?'slice':'projection',run=state.image!=='raw'&&index===state.channel&&canShow(runMeta(),kind)?state.run:'';
 return '/api/image?'+query({dataset:state.dataset,channel:index,z:kind==='slice'?state.z:0,view:kind,run,kind:intensityKind(),projection:state.projection,background:channelSettings()[index].background});
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
 const title=document.createElement('h3');title.textContent='Channels';channelBody.append(title);
 const label=document.createElement('label');label.textContent='View';const select=document.createElement('select');select.setAttribute('aria-label','Channel display mode');for(const [value,text] of [['color','One channel · color'],['composite','Combine visible channels'],['gray','One channel · gray']])select.add(new Option(text,value));select.value=state.channelDisplay;select.onchange=()=>{state.channelDisplay=select.value;saveChannels()};label.append(select);channelBody.append(label);
 const shortcuts=document.createElement('div');shortcuts.className='channel-shortcuts';for(const [text,action] of [['Show all',()=>{channelSettings().forEach(c=>{c.visible=true;c.included=true});state.channelDisplay='composite'}],['Only active',()=>{channelSettings().forEach((c,i)=>c.visible=i===state.channel);state.channelDisplay='composite'}]]){const button=document.createElement('button');button.textContent=text;button.onclick=()=>{action();saveChannels();channelBody.dataset.dataset='';refreshChannelMenu()};shortcuts.append(button)}channelBody.append(shortcuts);
 channelSettings().forEach((setting,i)=>{
  const card=document.createElement('section');card.className='channel-card'+(i===state.channel?' active':'');channelBody.append(card);
  const row=document.createElement('div');row.className='channel-color-row';const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=setting.visible&&setting.included||i===state.channel;toggle.setAttribute('aria-label','Show channel '+(i+1)+' in composite');
  const name=document.createElement('button');name.className='channel-name';name.textContent='C'+(i+1)+' · '+channelLabel(i);name.title='Use this channel for analysis';name.onclick=async()=>{setting.included=true;setting.visible=true;refreshChannelPicker();$('#channel').value=i;await $('#channel').onchange({target:$('#channel')});saveChannels();channelBody.dataset.dataset='';refreshChannelMenu()};
  const color=document.createElement('input');color.type='color';color.value=setting.color;color.setAttribute('aria-label','Channel '+(i+1)+' color');toggle.onchange=async()=>{if(i===state.channel&&!toggle.checked){const next=channelSettings().findIndex((c,j)=>j!==i&&c.included&&c.visible);if(next<0){toggle.checked=true;status('Keep one channel visible, or show another channel first.',true);return}if(!(await resolveDrawing())){toggle.checked=true;return}$('#channel').value=next;await $('#channel').onchange({target:$('#channel')})}setting.visible=toggle.checked;if(setting.visible)setting.included=true;state.channelDisplay='composite';saveChannels();channelBody.dataset.dataset='';refreshChannelMenu()};color.oninput=()=>{setting.color=color.value;saveChannels()};row.append(toggle,name,color);card.append(row);
  const meta=document.createElement('small');meta.className='channel-purpose';meta.textContent=i===state.channel?'Active analysis channel':setting.role||'Display channel';card.append(meta);
  const fold=document.createElement('details');fold.className='channel-adjust-fold';const summary=document.createElement('summary');summary.textContent='Name & display adjustments';fold.append(summary);card.append(fold);const details=document.createElement('div');details.className='channel-adjust';fold.append(details);
  const aliasLabel=document.createElement('label');aliasLabel.textContent='Display name';const alias=document.createElement('input');alias.type='text';alias.maxLength=60;alias.value=setting.alias;alias.placeholder=state.meta.channels[i];alias.setAttribute('aria-label','Channel '+(i+1)+' display name');alias.onchange=()=>{setting.alias=alias.value.trim();name.textContent='C'+(i+1)+' · '+channelLabel(i);saveChannels()};aliasLabel.append(alias);details.append(aliasLabel);
  const roleLabel=document.createElement('label');roleLabel.textContent='What I use it for';const role=document.createElement('input');role.type='text';role.maxLength=80;role.value=setting.role;role.placeholder='e.g. nuclei, neurites, marker';role.setAttribute('aria-label','Channel '+(i+1)+' purpose');role.onchange=()=>{setting.role=role.value.trim();meta.textContent=i===state.channel?'Active analysis channel':setting.role||'Display channel';saveChannels()};roleLabel.append(role);details.append(roleLabel);
  const includedLabel=document.createElement('label');includedLabel.className='channel-include';const included=document.createElement('input');included.type='checkbox';included.checked=setting.included;included.disabled=i===state.channel;included.setAttribute('aria-label','Include channel '+(i+1)+' in picker');included.onchange=()=>{setting.included=included.checked;if(!included.checked)setting.visible=false;toggle.checked=setting.visible;saveChannels()};includedLabel.append(included,document.createTextNode('Keep in my channel picker'));details.append(includedLabel);
  for(const [key,labelText] of [['brightness','☀ Brightness'],['contrast','◐ Contrast']]){const field=document.createElement('label');field.textContent=labelText;field.title='Display only; source values and algorithms are unchanged';const slider=document.createElement('input');slider.type='range';slider.min=key==='brightness'?20:50;slider.max=key==='brightness'?250:300;slider.value=setting[key];slider.setAttribute('aria-label',`Channel ${i+1} ${key}`);const output=document.createElement('output');output.textContent=setting[key]+'%';slider.oninput=()=>{setting[key]=+slider.value;output.textContent=slider.value+'%';saveChannels()};field.append(slider,output);details.append(field)}
  const histogram=document.createElement('canvas');histogram.className='channel-histogram';histogram.width=250;histogram.height=72;histogram.setAttribute('role','img');histogram.setAttribute('aria-label',`Channel ${i+1} display histogram with black and white window markers`);histogram.title='Auto-scaled display histogram. Drag the black or white marker to adjust the display window.';details.append(histogram);
  const update={draw:()=>{}};for(const [key,text,min,max] of [['blackPoint','Black',0,254],['whitePoint','White',1,255]]){const field=document.createElement('label');field.textContent=text;const slider=document.createElement('input');slider.type='range';slider.min=min;slider.max=max;slider.value=setting[key];slider.setAttribute('aria-label',`Channel ${i+1} ${text.toLowerCase()} point`);const output=document.createElement('output');output.textContent=setting[key];slider.oninput=()=>{setting[key]=Math.max(key==='blackPoint'?0:setting.blackPoint+1,Math.min(key==='blackPoint'?setting.whitePoint-1:255,+slider.value));slider.value=setting[key];output.textContent=setting[key];update.draw();saveChannels()};field.append(slider,output);details.append(field)}
  let dragging=null;histogram.onpointerdown=e=>{const x=(e.clientX-histogram.getBoundingClientRect().left)/histogram.clientWidth*255;dragging=Math.abs(x-setting.blackPoint)<Math.abs(x-setting.whitePoint)?'blackPoint':'whitePoint';histogram.setPointerCapture(e.pointerId);histogram.onpointermove=move=>{if(!dragging)return;const value=Math.round((move.clientX-histogram.getBoundingClientRect().left)/histogram.clientWidth*255);setting[dragging]=Math.max(dragging==='blackPoint'?0:setting.blackPoint+1,Math.min(dragging==='blackPoint'?setting.whitePoint-1:255,value));const slider=details.querySelector(`[aria-label="Channel ${i+1} ${dragging==='blackPoint'?'black':'white'} point"]`);slider.value=setting[dragging];slider.nextSibling.textContent=setting[dragging];update.draw();saveChannels()}};histogram.onpointerup=()=>dragging=null;histogram.onpointercancel=()=>dragging=null;
  const bg=document.createElement('label');bg.textContent='Background';bg.title='Subtract a smooth local background from the view only';const bgSelect=document.createElement('select');bgSelect.setAttribute('aria-label',`Channel ${i+1} background`);bgSelect.add(new Option('Off','off'));bgSelect.add(new Option('Local subtraction','local'));bgSelect.value=setting.background;bgSelect.onchange=()=>{setting.background=bgSelect.value;saveChannels();displayHistogram(i,histogram,update)};bg.append(bgSelect);details.append(bg);const reset=document.createElement('button');reset.textContent='Reset display';reset.onclick=()=>{Object.assign(setting,{brightness:100,contrast:100,background:'off',blackPoint:0,whitePoint:255});saveChannels();channelBody.dataset.dataset='';refreshChannelMenu()};details.append(reset);fold.addEventListener('toggle',()=>{if(fold.open)displayHistogram(i,histogram,update)});
 });
 const note=document.createElement('p');note.className='muted';note.textContent='Names and visibility are saved for this image on this device. The active channel is used for processing; display adjustments only change the view.';channelBody.append(note);
}
channelMenu.addEventListener('toggle',()=>{if(channelMenu.open){channelBody.dataset.dataset='';refreshChannelMenu()}});
const channelDraw=scheduleDraw;scheduleDraw=function(){if(state.meta){refreshChannelPicker();refreshChannelMenu()}channelDraw()};
const channelLayout=renderLayout;renderLayout=function(){channelLayout();if(state.meta){refreshChannelPicker();channelBody.dataset.dataset='';refreshChannelMenu()}};
