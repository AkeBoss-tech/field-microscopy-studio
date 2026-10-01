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
