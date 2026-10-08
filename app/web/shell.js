'use strict';
// Layout and motion pass. Moves existing controls (keeping their handlers) so the image gets the space:
// workspace tabs join the header, view tools float beside the image, the context line moves to the footer.
{
 const header=$('header'),nav=$('nav'),brand=header.querySelector('strong');
 brand.after(nav);nav.classList.add('segmented','workspace-tabs');
 const navPill=document.createElement('span');navPill.className='segment-pill';navPill.setAttribute('aria-hidden','true');nav.prepend(navPill);
 const modes=$('#simple-toolbar .mode-buttons');modes.classList.add('segmented');
 const modePill=document.createElement('span');modePill.className='segment-pill';modePill.setAttribute('aria-hidden','true');modes.prepend(modePill);

 // View tools become a floating rail at the right edge of the image area.
 const desk=$('#desk'),rail=document.querySelector('.view-tools');
 if(rail){rail.classList.add('tool-rail');rail.setAttribute('aria-orientation','vertical');desk.append(rail);
  rail.querySelectorAll('.explore-tool-button').forEach(b=>{const label=b.querySelector('.explore-tool-label');if(label)b.dataset.tip=label.textContent});
  const chip=document.createElement('div');chip.className='ruler-chip';desk.append(chip);
  const readout=document.querySelector('.ruler-readout'),clear=document.querySelector('.ruler-clear');if(readout)chip.append(readout);if(clear)chip.append(clear);
  new MutationObserver(()=>chip.classList.toggle('visible',!!readout&&!readout.hidden&&!!readout.textContent)).observe(readout,{attributes:true,childList:true,characterData:true,subtree:true})}
 // Z navigation leaves the footer for a vertical depth rail on the image's left edge.
 // It is shown only where a single acquired plane is on screen (2D slices, and the slice-based workspaces).
 const depth=document.createElement('div');depth.className='depth-rail';depth.setAttribute('role','group');depth.setAttribute('aria-label','Z plane');
 const zInput=$('#z'),zLabel=$('#zlabel'),zField=zInput.closest('label');
 const zTitle=document.createElement('span');zTitle.className='depth-title';zTitle.textContent='Z';
 // experiments.js hides the slider through its wrapping label, so the label moves with it.
 [...zField.childNodes].forEach(node=>{if(node!==zInput)node.remove()});zField.className='depth-slider';
 depth.append(zTitle,$('#previous-z'),zField,$('#next-z'),zLabel,$('#play-z'));desk.append(depth);
 $('#previous-z').innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>';
 $('#next-z').innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
 const context=$('#analysis-context'),row=document.querySelector('.context-row');
 if(context){$('#status').before(context);context.classList.add('footer-context')}
 row?.remove();

 // Collapsible results sidebar; the preference is a per-browser convenience.
 const sidebar=$('#result-sidebar'),heading=sidebar.querySelector('.sidebar-heading');
 const collapse=document.createElement('button');collapse.className='sidebar-toggle';collapse.setAttribute('aria-label','Hide results panel');collapse.title='Hide results panel';collapse.innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>';
 heading.append(collapse);
 const reopen=document.createElement('button');reopen.className='sidebar-reopen';reopen.setAttribute('aria-label','Show results panel');reopen.title='Show algorithm results';reopen.innerHTML='<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg><span>Results</span><b class="reopen-count"></b>';
 desk.append(reopen);
 const setCollapsed=value=>{document.body.classList.toggle('sidebar-collapsed',value);try{localStorage.setItem('field-sidebar-collapsed',value?'1':'0')}catch{}
  // The canvas size changes with the sidebar; redraw after the width transition settles.
  setTimeout(()=>{scheduleDraw();syncPills()},360)};
 collapse.onclick=()=>setCollapsed(true);reopen.onclick=()=>setCollapsed(false);
 let stored=null;try{stored=localStorage.getItem('field-sidebar-collapsed')}catch{}
 document.body.classList.toggle('sidebar-collapsed',stored==='1'||(stored===null&&innerWidth<=1150));
 new MutationObserver(()=>reopen.querySelector('.reopen-count').textContent=$('#result-count').textContent||'').observe($('#result-count'),{childList:true,characterData:true,subtree:true});

 function syncPills(){movePill(nav);movePill(modes);document.querySelectorAll('.render-modes,.render-dock .segmented').forEach(movePill)}
 addEventListener('resize',()=>requestAnimationFrame(syncPills));
 if(document.fonts?.ready)document.fonts.ready.then(syncPills);

 // Entrance motion only when the workspace, view mode or image actually changes,
 // so routine redraws (channel tweaks, run selection) never flash.
 let signature='';
 const shellLayout=renderLayout;
 renderLayout=function(){
  shellLayout();
  const next=[state.tab,state.mode,state.dataset,state.focusObject?.id||'',(state.region3d||[]).join(',')].join('|');
  const host=$('#main-host');
  if(next!==signature&&signature){host.classList.remove('view-enter');void host.offsetWidth;host.classList.add('view-enter');clearTimeout(host.enterTimer);host.enterTimer=setTimeout(()=>host.classList.remove('view-enter'),700)}
  signature=next;
  document.body.dataset.mode=state.mode;
  // Review has its own crosshair Z; projection and 3D views do not use a single plane.
  const cropPreview=state.tab==='Process'&&expParams().scope==='volume'&&experiment.previews.has(expKey());depth.classList.toggle('visible',(state.tab==='Explore'&&state.mode==='slice')||(state.tab==='Process'&&!cropPreview)||state.tab==='Annotate');
  requestAnimationFrame(syncPills);
 };

 // Status messages fade in when they change.
 const statusLine=$('#status');
 new MutationObserver(()=>{statusLine.classList.remove('status-flash');void statusLine.offsetWidth;statusLine.classList.add('status-flash')}).observe(statusLine,{childList:true,characterData:true,subtree:true});
 requestAnimationFrame(syncPills);
}

// ---- Review: two focused views (Planes / Candidates), one view menu, and a compact inspector ----
reviewState.view='planes';reviewState.depthAuto=true;
function setReviewView(view){
 reviewState.view=view;const host=$('#main-host');host.dataset.reviewView=view;
 host.querySelectorAll('.review-switch button').forEach(b=>{const on=b.dataset.view===view;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on))});
 movePill(host.querySelector('.review-switch'));
 if(view==='planes')requestAnimationFrame(()=>drawReviewCanvases());
}
const shellReviewWorkspace=renderReviewWorkspace;
renderReviewWorkspace=function(){
 shellReviewWorkspace();
 const host=$('#main-host'),controls=host.querySelector('.review-controls');if(!controls)return;
 // Auto depth expansion keeps XZ/YZ readable when the stack is thin relative to its width.
 const depthSelect=controls.querySelector('[aria-label="Depth display"]');
 if(depthSelect&&state.meta){
  const [nz,,,nx]=state.meta.shape,[sx,,sz]=state.meta.calibrated?state.meta.spacing:[1,1,1],auto=Math.max(1,Math.min(12,Math.ceil(.25*nx*sx/(nz*sz))));
  depthSelect.insertBefore(new Option('Auto · Z ×'+auto+' (display only)','auto:'+auto),depthSelect.firstChild);
  if(reviewState.depthAuto){reviewState.depthScale=auto;depthSelect.value='auto:'+auto}
  depthSelect.addEventListener('change',()=>{reviewState.depthAuto=depthSelect.value.startsWith('auto');if(reviewState.depthAuto){reviewState.depthScale=auto;drawReviewCanvases()}},true);
  // The original handler reads +value; give it a number for the auto option.
  const original=depthSelect.onchange;depthSelect.onchange=e=>{if(depthSelect.value.startsWith('auto'))return;original?.(e)};
 }
 const bar=document.createElement('div');bar.className='review-topbar';
 const tabs=document.createElement('div');tabs.className='review-switch segmented';tabs.setAttribute('role','tablist');
 const pill=document.createElement('span');pill.className='segment-pill';pill.setAttribute('aria-hidden','true');tabs.append(pill);
 for(const [view,label] of [['planes','Planes'],['candidates','Candidates']]){const b=document.createElement('button');b.type='button';b.dataset.view=view;b.setAttribute('role','tab');b.innerHTML='<span>'+label+'</span>'+(view==='candidates'?'<b class="review-count"></b>':'');b.onclick=()=>setReviewView(view);tabs.append(b)}
 const viewMenu=document.createElement('details');viewMenu.className='ui-dropdown review-view-menu';const summary=document.createElement('summary');summary.textContent='View';const body=document.createElement('div');body.className='dropdown-body';
 [...controls.children].filter(el=>el.tagName==='LABEL').forEach(label=>body.append(label));
 const help=host.querySelector('.review-canvas-help');if(help){const p=help.querySelector('p');if(p){p.className='muted review-help';body.append(p)}help.remove()}
 viewMenu.append(summary,body);viewMenu.addEventListener('toggle',()=>{if(viewMenu.open)document.querySelectorAll('.ui-dropdown').forEach(o=>{if(o!==viewMenu)o.open=false})});
 const spacer=document.createElement('span');spacer.className='review-topbar-spacer';
 bar.append(tabs,spacer,viewMenu);controls.replaceWith(bar);
 const panel=host.querySelector('.measurement-panel');
 if(!panel){tabs.hidden=true;reviewState.view='planes'}
 setReviewView(panel?reviewState.view:'planes');
 // Crosshair coordinates become one compact row.
 const positions=$('#task-panel .review-position-controls');
 if(positions){positions.classList.add('compact-xyz');positions.querySelectorAll('label').forEach(l=>{const input=l.querySelector('input');l.firstChild.textContent=input.id.slice(-1).toUpperCase()+' '})}
 const heading=$('#task-panel h2');if(heading)heading.textContent='Crosshair';
 const notes=document.createElement('details');notes.className='inspector-notes';const notesSummary=document.createElement('summary');notesSummary.textContent='Display & limits';notes.append(notesSummary);
 for(const el of [$('#review-window-info'),$('#task-panel .review-caveat')])if(el)notes.append(el);$('#task-panel').append(notes);
};
// Candidate count on the tab; locating a candidate returns to the planes.
{const updateCount=()=>{const data=measurementState.data,b=document.querySelector('.review-count');if(b&&data)b.textContent=data.count.ready?'✓ '+data.count.reviewed_count:data.count.unresolved.toLocaleString()+' to review'};
 const shellLoadMeasurements=loadMeasurements;loadMeasurements=async function(){await shellLoadMeasurements();updateCount()};
 const shellLocate=locateMeasurement;locateMeasurement=function(id){setReviewView('planes');return shellLocate(id)}}
// Inspector: title, actions in one row, two key facts, everything else under "More details".
const shellInspector=showObjectInspector;
showObjectInspector=function(data){
 shellInspector(data);
 const box=$('#object-inspector');if(!box)return;
 const actions=document.createElement('div');actions.className='inspector-actions';
 for(const b of box.querySelectorAll(':scope>button')){actions.append(b)}
 const open=[...actions.children].find(b=>/Open cell in 3D/.test(b.textContent));if(open){open.textContent='Open in 3D';open.classList.add('primary-action');actions.prepend(open)}
 const decide=[...actions.children].find(b=>/^Review candidate/.test(b.textContent));if(decide){decide.textContent='Decide…';decide.title='Accept, reject or flag this candidate'}
 const fix=[...actions.children].find(b=>/Fix this mask/.test(b.textContent));if(fix)fix.textContent='✎ Fix mask';
 box.querySelector('h3')?.after(actions);
 // The inspector owns its visible morphology tiles and expandable details.
 // Keep this wrapper limited to arranging the shared review/3D actions.
 if(!actions.children.length)actions.remove();
};

// The static demo's runtime adds a banner before <nav> and a backup button to the header on
// DOMContentLoaded. Nav now lives in the header, so move them to a banner row and the Workspace menu.
addEventListener('DOMContentLoaded',()=>{
 const header=$('header'),banner=document.querySelector('.shared-banner');if(banner)header.after(banner);
 const backup=[...header.querySelectorAll(':scope>button')].find(b=>b.textContent==='Back up workspace'),menu=document.querySelector('.workspace-menu .dropdown-body');
 if(backup&&menu)menu.append(backup);
 requestAnimationFrame(()=>movePill($('nav.workspace-tabs')));
});

// ---- Process: show the selected algorithm, its full pipeline, and what is running now ----
const algorithmNames={adaptive_regions:'Local Gaussian threshold + signal floor',prominence_watershed:'H-maxima distance watershed',otsu:'Otsu threshold',watershed:'Distance watershed',sato:'Sato ridge filter',preprocess:'Intensity preparation',neurite_otsu:'Otsu + skeleton',neurite_adaptive:'Adaptive + skeleton',neurite_sato:'Sato + skeleton',neurite_frangi:'Frangi + skeleton',neurite_meijering:'Meijering + skeleton'};
const methodGlyphs={adaptive_regions:'◉',prominence_watershed:'◈',otsu:'◉',watershed:'◈',sato:'⌁',preprocess:'◒',neurite_otsu:'⌁',neurite_adaptive:'⌁',neurite_sato:'⌁',neurite_frangi:'⌁',neurite_meijering:'⌁'};
function recipeField(prefix){return [...document.querySelectorAll('.experiment-settings [name],.experiment-advanced [name]')].find(el=>el.name===prefix||el.name.startsWith(prefix+'_')&&!el.closest('label')?.hidden)}
function recipeValue(prefix){const el=recipeField(prefix);if(!el)return null;return el.type==='checkbox'?el.checked:el.value}
function recipeUnit(prefix){const el=recipeField(prefix),label=el?.closest('label')?.firstChild?.textContent||'';return (label.match(/\(([^)]+)\)/)||[])[1]||''}
function pipelineSteps(){
 const p=expParams(),method=p.method,on=v=>v!==null&&v!==''&&Number(v)>0;
 const parent=document.querySelector('.experiment-settings [name=parent],.experiment-advanced [name=parent]'),input=parent?.selectedOptions[0]?.textContent||'Original source';
 const scope=p.scope==='volume'?(p.run_region==='selected'?'selected XY / Z region':'all '+state.meta.shape[0]+' Z planes'):p.scope==='slice'?'plane '+(state.z+1):'maximum Z projection';
 const steps=[['Input',input+' · C'+(state.channel+1)+' · '+p.factor+'× XY · '+scope,true]];
 const sigma=recipeValue('sigma'),background=recipeValue('background'),normalize=recipeValue('normalize');
 steps.push(['Smooth',on(sigma)?'Gaussian σ '+sigma+' '+recipeUnit('sigma'):'Off',on(sigma)]);
 steps.push(['Background',on(background)?'Subtract σ '+background+' '+recipeUnit('background'):'Off',on(background)]);
 steps.push(['Normalize',normalize?'Rescale intensity':'Off',!!normalize]);
 if(method==='preprocess'){steps.push(['Output','Prepared intensity · no labels',true]);return steps}
 if(method==='sato'||['neurite_sato','neurite_frangi','neurite_meijering'].includes(method))steps.push(['Enhance',algorithmNames[method]+' · '+(method==='sato'?(p.sato_mode==='slice'?'per XY plane':'3D grid'):(p.neurite_mode==='volume'?'3D filter':'per XY plane')),true]);
 const threshold=recipeValue('threshold');steps.push(['Threshold',method==='adaptive_regions'?'Local window '+(recipeValue('local_window')||31)+' working px + Otsu floor × '+(recipeValue('local_floor')??.5):method==='neurite_adaptive'?'Local window '+(recipeValue('adaptive_block_size')||31)+' grid px':'Otsu'+(threshold&&Number(threshold)!==1?' × '+threshold:''),true]);
 const minFg=recipeValue('min_size');steps.push(['Drop specks',on(minFg)?'< '+minFg+' '+recipeUnit('min_size'):'Off',on(minFg)]);
 if(method==='prominence_watershed')steps.push(['Split touching','Peak prominence '+(recipeValue('peak_prominence')||.5)+' '+(expParams().units==='physical'?'µm':'working px'),true]);
 if(method==='watershed'){const d=recipeValue('seed_distance')??recipeValue('distance');steps.push(['Split touching','Seeds ≥ '+(d??'?')+' '+((recipeUnit('seed_distance')||recipeUnit('distance'))||'px')+' apart',true])}
 if(expIsNeurite(method)){
  const exclude=recipeValue('neurite_soma_radius'),prune=recipeValue('neurite_min_branch_length');
  if(on(exclude))steps.push(['Wide signal','Exclude radius ≥ '+exclude+' '+recipeUnit('neurite_soma_radius'),true]);
  steps.push(['Skeleton','Thin each connected foreground network',true]);
  if(on(prune))steps.push(['Measure','Ignore terminal paths < '+prune+' '+recipeUnit('neurite_min_branch_length'),true]);
 }
 const minFinal=recipeValue('min_final');if(minFinal!==null)steps.push(['Final filter',on(minFinal)?'Objects < '+minFinal+' '+recipeUnit('min_final')+' removed':'Off',on(minFinal)]);
 steps.push(['Output',expIsNeurite(method)?'Network lengths & branch measurements':method==='sato'?'Connected ridge regions':'Candidate labels'+(p.scope==='volume'?' in 3D':''),true]);
 return steps;
}
function renderAlgorithmOverview(){
 const panel=$('#task-panel'),settings=panel?.querySelector('.experiment-settings');if(state.tab!=='Process'||!settings||panel.hidden||!state.meta)return;
 let box=panel.querySelector('.algo-overview');
 if(!box){box=expNode('section','algo-overview');box.setAttribute('aria-label','Running processing jobs');const running=expNode('div','algo-running');running.hidden=true;box.append(running);settings.prepend(box)}
 let pipeline=panel.querySelector('.algo-pipeline-box');
 if(!pipeline){pipeline=expNode('details','algo-pipeline-box');pipeline.setAttribute('aria-label','Applied processing pipeline');pipeline.open=!!experiment.showPipeline;pipeline.ontoggle=()=>experiment.showPipeline=pipeline.open;const jobs=settings.querySelector('.process-jobs');if(jobs)jobs.before(pipeline);else settings.append(pipeline)}
 pipeline.replaceChildren(expNode('summary','','Applied pipeline'));
 const list=expNode('ol','algo-pipeline');pipelineSteps().forEach(([name,value,active],i)=>{const li=expNode('li',active?'':'off');li.append(expNode('span','step-dot',String(i+1)),expNode('span','step-name',name),expNode('span','step-value',value));list.append(li)});pipeline.append(list);refreshRunning();
}
let runningTimer=null;
async function refreshRunning(){
 clearTimeout(runningTimer);const box=document.querySelector('.algo-running');if(!box||state.tab!=='Process')return;
 try{const jobs=(await api('/api/jobs')).filter(j=>['queued','running'].includes(j.status)&&j.dataset===state.dataset);
  box.replaceChildren();box.hidden=!jobs.length;
  for(const j of jobs){const row=expNode('div','running-job');const info=methodInfo[j.method]||[j.method||'Processing'];const seconds=Math.max(0,Math.round(Date.now()/1000-j.created));
   row.append(expNode('span','running-pulse'),expNode('strong','',(j.status==='queued'?'Queued · ':'Running · ')+info[0]),expNode('span','running-meta',(algorithmNames[j.method]||'')+' · C'+(Number(j.channel)+1)+(j.factor?' · '+j.factor+'× XY':'')+' · '+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0')),expNode('span','running-message',j.message||'Waiting for the worker…'),expNode('span','running-bar'));box.append(row)}
  if(jobs.length)runningTimer=setTimeout(refreshRunning,1500);
 }catch{}
}
{const processLayout=renderLayout;renderLayout=function(){processLayout();if(state.tab==='Process')requestAnimationFrame(renderAlgorithmOverview)};
 // Process re-renders its panel asynchronously; re-attach the overview whenever it disappears.
 new MutationObserver(()=>{if(state.tab==='Process'&&!$('#task-panel').hidden&&!$('#task-panel .algo-overview')&&$('#task-panel .experiment-form'))renderAlgorithmOverview()}).observe($('#task-panel'),{childList:true,subtree:true});
 document.addEventListener('change',e=>{if(e.target.closest?.('.experiment-settings'))requestAnimationFrame(renderAlgorithmOverview)});
 document.addEventListener('input',e=>{if(e.target.closest?.('.experiment-settings'))requestAnimationFrame(renderAlgorithmOverview)});
 // A run submitted from Process shows up in "Running now" right away.
 document.addEventListener('click',e=>{if(/Run (full|selected|current|Z projection|all 5)/.test(e.target.closest?.('button')?.textContent||''))setTimeout(refreshRunning,400)},true)}
// Results list: friendly algorithm names and the same glyph/colour as the Process cards.
{const shellCatalog=resultCatalog;resultCatalog=function(){shellCatalog();
 for(const b of document.querySelectorAll('#result-list .result-button[data-result]')){const r=state.runs.find(run=>run.id===b.dataset.result),info=r&&methodInfo[r.method];if(!info)continue;
  const title=b.firstElementChild;if(title&&(!r.title||r.title===r.method))title.textContent=info[0];
  const glyph=expNode('span','result-glyph '+info[2],methodGlyphs[r.method]);b.prepend(glyph);b.classList.add('has-glyph');b.title=info[0]+' · '+algorithmNames[r.method]}}}

// ---- Bundled example: assistant-curated IHC/OHC masks and points for the Control Mid-1 starter ----
const hairExample={dataset:'hair-control',base:'examples/hair-control-ihc-ohc/',runs:[
 {file:'ihc-labels.tif',algorithm:'Example · IHC (assistant-curated)',target:'Inner hair cells · Myo7a bodies'},
 {file:'ohc-labels.tif',algorithm:'Example · OHC (assistant-curated)',target:'Outer hair cells · Myo7a bodies'}]};
function exampleRuns(){return hairExample.runs.map(spec=>state.runs.find(r=>r.title===spec.algorithm)).filter(Boolean)}
async function loadHairExample(button){
 if(state.dirty&&!confirm('Save or discard your unsaved annotations first. Continue without them?'))return;
 button.disabled=true;const note=button.parentElement.querySelector('.example-progress');
 try{
  const loaded=exampleRuns().map(r=>r.title);
  for(const spec of hairExample.runs){
   if(loaded.includes(spec.algorithm))continue;
   note.textContent='Importing '+spec.target.split(' · ')[0].toLowerCase()+'…';
   const blob=await (await fetch(hairExample.base+spec.file)).blob();
   const response=await fetch('/api/import-labels?'+query({dataset:hairExample.dataset,channel:0,name:spec.file,axes:'ZYX',algorithm:spec.algorithm,target:spec.target,alignment_confirmed:'yes'}),{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Studio-Request':'1'},body:blob});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Import failed');
  }
  note.textContent='Adding labelled points…';
  const example=await (await fetch(hairExample.base+'annotations.json')).json(),current=await api('/api/annotations?'+query({dataset:hairExample.dataset}));
  const existing=new Set(current.items.map(it=>it.label));
  const items=[...current.items,...example.items.filter(it=>!existing.has(it.label))];
  if(items.length>current.items.length)await api('/api/annotations',{dataset:hairExample.dataset,base_revision:current.revision,author:'Example (assistant-curated)',items});
  await loadAnnotations();await loadRuns();
  const ohc=exampleRuns().find(r=>/OHC/.test(r.title));if(ohc)chooseResult(ohc.id);
  state.tab='Review';renderLayout();
  status(`Loaded example: ${example.ihc} IHC + ${example.ohc} OHC masks and points · assistant-curated, not expert-validated`);
 }catch(error){note.textContent=error.message;button.disabled=false}
}
{const exampleCatalog=resultCatalog;resultCatalog=function(){exampleCatalog();
 if(state.dataset!==hairExample.dataset)return;
 const card=document.createElement('section');card.className='example-card';
 const loaded=exampleRuns();
 card.innerHTML='<p class="example-kicker">Example</p><h4>IHC &amp; OHC segmentation</h4><p>21 inner and 69 outer hair cells outlined in 3D, with labelled points. Shows what a correct run should look like.</p>';
 const fine=document.createElement('p');fine.className='example-fine';fine.textContent='Assistant-curated from Myo7a (C1). Not expert-validated.';
 const progress=document.createElement('p');progress.className='example-progress';progress.setAttribute('role','status');
 if(loaded.length===hairExample.runs.length){const row=document.createElement('div');row.className='example-actions';for(const r of loaded){const b=expButton(/IHC/.test(r.title)?'Open IHC':'Open OHC','',()=>{chooseResult(r.id);state.tab='Review';renderLayout()});row.append(b)}card.append(row)}
 else{const b=expButton('Load example','primary-action',()=>loadHairExample(b));card.append(b)}
 const docs=document.createElement('a');docs.href=hairExample.base+'overview.png';docs.target='_blank';docs.rel='noopener';docs.textContent='Overview image';
 card.append(fine,progress,docs);$('#result-list').append(card)}}
