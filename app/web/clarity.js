'use strict';
// Guided preparation and deterministic explanations from saved run evidence.
function clarityDownload(text, filename){const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function clarityCopy(text,dialog){try{await navigator.clipboard.writeText(text);expNotice('Explanation copied.')}catch{const field=document.createElement('textarea');field.value=text;field.setAttribute('aria-label','Text to copy');dialog.append(field);field.focus();field.select();expNotice('Select and copy the text below.')}}
function clarityGuide(){
 const host=$('#main-host');if(!host||state.tab!=='Process')return;
 const hair=state.recipe.analysis_goal==='hair-cells';
 const guide=expNode('section','clarity-guide');guide.setAttribute('aria-label','Processing guide');
 guide.append(expNode('h3','',hair?'Hair-cell counting workflow':'What happens to this image'));
 const steps=expNode('ol','clarity-steps');
 for(const [title,help] of [
  ['Choose signal',hair?'Confirm Myo7a as the hair-cell channel. Other channels provide context.':'Choose the channel containing your target and the region to examine.'],
  ['Clean signal','Reduce noise or broad background only when it helps preserve real structures.'],
  ['Find candidates','A threshold marks bright signal. Touching cells may form one region.'],
  ['Separate neighbors','Watershed can split touching regions; inspect both merges and extra splits.'],
  ['Review','Follow candidates through acquired Z planes; accept, reject or correct them.'],
  ['Report','Explain the saved settings, candidate output, review progress and validation limits.']]){
  const li=expNode('li');li.append(expNode('strong','',title),expNode('span','',help));steps.append(li);
 }
 guide.append(steps);
 if(hair)guide.append(expNode('p','clarity-note','Include dim, touching and ectopic-row examples. This workflow does not impose normal row counts or automatically assign IHC/OHC identity.'));
 const detail=expNode('details');detail.append(expNode('summary','','How to judge a cleanup option'),expNode('p','','Compare the original and prepared signal at the same Z and contrast. Check whether dim cells survive, neighbors stay distinct and background detections decrease. Freeze the recipe before testing separate specimens. Better appearance alone does not establish better counting.'));
 guide.append(detail);host.prepend(guide);
}
async function clarityCleanup(){
 const params=expValidate(),key=state.dataset,channel=state.channel,signature=expSignature(),region=structuredClone(expPreviewRegion()),physical=params.units==='physical';
 const d=expModal('Compare image cleanup','Four unsaved previews of the same acquired region. Select widths to test; these are starting values, not validated settings.','clarity-dialog');
 const controls=expNode('div','clarity-controls');const make=(name,value,max)=>{const label=expNode('label','exp-field',name),el=document.createElement('input');el.type='number';el.min=.001;el.max=max;el.step='any';el.value=Number(Number(value).toPrecision(5));el.setAttribute('aria-label',name);label.append(el);controls.append(label);return el};
 const skey=physical?'sigma_um':'sigma',bkey=physical?'background_um':'background',unit=physical?'µm':'working pixels',base=physical?state.meta.spacing[0]*params.factor:1;
 const smooth=make('Smoothing width ('+unit+')',Number(params[skey])||base,physical?100:5),background=make('Background width ('+unit+')',Number(params[bkey])||base*12,physical?500:64);
 d.append(controls,expNode('p','clarity-note','Background width must exceed smoothing width. Normalization is off in all four previews. This isolates smoothing and background removal.'));
 const status=expNode('p','clarity-status','Ready to compare.');status.role='status';d.append(status);
 const output=expNode('div');d.append(output);let serial=0;
 const run=expButton('Compare four options','primary',safe(async()=>{
  if(!smooth.reportValidity()||!background.reportValidity())return;
  const ticket=++serial;run.disabled=true;output.replaceChildren();status.textContent='Preparing four crop previews…';
  try{
   const data=await api('/api/cleanup-compare',{dataset:key,channel,parameters:params,...region,smooth:Number(smooth.value),background:Number(background.value)});
   if(!d.isConnected||ticket!==serial)return;
   status.textContent=data.note;
   const zlabel=expNode('label','exp-field','Comparison Z plane'),z=document.createElement('input');z.type='range';z.min=0;z.max=data.variants[0].planes.length-1;z.value=Math.floor(data.variants[0].planes.length/2);z.setAttribute('aria-label','Cleanup comparison Z');const zout=expNode('output');zlabel.append(z,zout);output.append(zlabel);
   const layerLabel=expNode('label','exp-field','Show'),layer=document.createElement('select');layer.setAttribute('aria-label','Cleanup comparison layer');layer.add(new Option('Prepared intensity','result'));layer.add(new Option('Candidate outlines on original','labels'));layerLabel.append(layer);output.append(layerLabel);
   const grid=expNode('div','clarity-comparison');output.append(grid);const images=[];
   for(const variant of data.variants){
    const card=expNode('section','clarity-option'),img=document.createElement('img');img.alt=variant.title+' cleanup comparison';images.push([img,variant]);
    card.append(expNode('h3','',variant.title),img,expNode('p','',params.method==='preprocess'?'Intensity only':variant.candidates+' candidate regions intersect this crop'),expNode('small','',`Smoothing ${Number(variant.parameters[skey].toPrecision(5))} ${unit} · background ${Number(variant.parameters[bkey].toPrecision(5))} ${unit}`));
    card.append(expButton('Use '+variant.title.toLowerCase(),'secondary',()=>{
     if(state.dataset!==key||state.channel!==channel||expSignature()!==signature){status.textContent='The processing draft changed. Close this comparison and compare the current settings before applying.';return}
     state.recipe={...state.recipe,[skey]:variant.parameters[skey],[bkey]:variant.parameters[bkey],normalize:false};
     d.close();renderLayout();expNotice(variant.title+' applied to the draft. Preview or save a run to use it.');
    }));grid.append(card);
   }
   const paint=()=>{zout.textContent='Acquired Z '+(data.variants[0].planes[Number(z.value)].z+1);for(const [img,variant]of images)img.src='data:image/png;base64,'+variant.planes[Number(z.value)][layer.value]};z.oninput=paint;layer.onchange=paint;paint();
  }catch(error){status.textContent=error.message}finally{run.disabled=false}
 }));controls.append(run);d.addEventListener('close',()=>serial++);
}
async function clarityExplain(){
 const dataset=state.dataset,runs=state.runs.filter(r=>r.channel===state.channel&&!r.historical);
 const d=expModal('Explain this result','Generated from saved settings and current review records. Changes to the processing draft do not change this explanation.','clarity-dialog');
 if(!runs.length){d.append(expNode('p','','Save a processing run first. Crop previews are unsaved experiments.'));return}
 const label=expNode('label','exp-field','Saved result'),select=document.createElement('select');select.setAttribute('aria-label','Result to explain');for(const r of runs)select.add(new Option(expRunLabel(r)+' · '+r.id.slice(0,8),r.id));select.value=runs.some(r=>r.id===state.run)?state.run:runs.at(-1).id;label.append(select);d.append(label);
 const body=expNode('div','clarity-report');d.append(body);let token=0;
 async function update(){const ticket=++token;body.replaceChildren(expNode('p','','Reading saved evidence…'));try{const result=await api('/api/run-explanation?'+query({dataset,run:select.value}));if(ticket!==token||!d.isConnected)return;body.replaceChildren();
  for(const [title,text]of Object.entries(result.sections)){const section=expNode('section');section.append(expNode('h3','',title),expNode('p','',text));body.append(section)}
  const actions=expNode('div','clarity-controls');actions.append(expButton('Copy result explanation','secondary',()=>clarityCopy(result.text,d)),expButton('Copy methods paragraph','primary',()=>clarityCopy(result.methods,d)),expButton('Download report','secondary',()=>clarityDownload(result.text+'\n\nMethods paragraph\n'+result.methods+'\n\nProvenance\n'+JSON.stringify(result.provenance,null,2),'field-result-'+result.run+'.txt')));body.append(actions);
  const details=expNode('details');details.append(expNode('summary','','Recorded settings and limitations'),expNode('p','',result.caveats.join(' ')),expNode('pre','',JSON.stringify(result.provenance,null,2)));body.append(details);
 }catch(error){body.replaceChildren(expNode('p','inline-error',error.message))}}
 select.onchange=update;d.addEventListener('close',()=>token++);await update();
}
const clarityProcess=decorateProcess;decorateProcess=function(){clarityProcess();const prep=$('#task-panel .preparation-fields');if(prep){const button=expButton('Compare cleanup options…','secondary clarity-compare-launch',safe(clarityCleanup)),p=expParams();button.disabled=experiment.busy||p.scope!=='volume'||!!p.parent||!['preprocess','otsu','watershed','adaptive_regions','prominence_watershed'].includes(p.method);button.title=button.disabled?'Choose original source, 3D scope and intensity, connected regions or watershed.':'Compare original, smoothing, background subtraction and both at a shared display window';prep.parentElement.append(button)}clarityGuide()};
const clarityResultButton=expButton('Explain this result','secondary',safe(clarityExplain));clarityResultButton.id='explain-result';$('#simple-toolbar').append(clarityResultButton);
const clarityLayout=renderLayout;renderLayout=function(){clarityLayout();clarityResultButton.hidden=state.tab==='Annotate';clarityResultButton.disabled=!state.runs?.some(r=>!r.historical&&r.channel===state.channel)};
const clarityCatalog=resultCatalog;resultCatalog=function(){clarityCatalog();clarityResultButton.disabled=!state.runs?.some(r=>!r.historical&&r.channel===state.channel)};
