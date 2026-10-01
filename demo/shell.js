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
 document.body.classList.toggle('sidebar-collapsed',stored==='1');
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
  depth.classList.toggle('visible',(state.tab==='Explore'&&state.mode==='slice')||state.tab==='Process'||state.tab==='Annotate');
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
 const more=document.createElement('details');more.className='inspector-more';const summary=document.createElement('summary');summary.textContent='More details';more.append(summary);
 const keep=/^(Volume:|Review status:)/;
 for(const el of [...box.children]){if(el===actions||el.tagName==='H3')continue;if(el.tagName==='P'&&keep.test(el.querySelector('strong')?.textContent||''))continue;more.append(el)}
 if(more.children.length>1)box.append(more);
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
