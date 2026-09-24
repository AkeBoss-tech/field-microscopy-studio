'use strict';
// Move existing controls, preserving their event handlers and accessible labels.
function fieldMenu(label,className,nodes,parent){
 const menu=document.createElement('details');menu.className='ui-dropdown '+className;
 const summary=document.createElement('summary');summary.textContent=label;
 const body=document.createElement('div');body.className='dropdown-body';
 nodes.filter(Boolean).forEach(node=>body.append(node));menu.append(summary,body);parent.append(menu);
 menu.addEventListener('toggle',()=>{if(menu.open)document.querySelectorAll('.ui-dropdown').forEach(other=>{if(other!==menu)other.open=false})});return menu;
}
fieldMenu('Display','display-menu',[$('#link-views').closest('label'),$('#overlay').closest('label'),$('#processed-label'),$('#more-tools')],$('#simple-toolbar'));
fieldMenu('Workspace','workspace-menu',[$('#fullscreen'),$('#focus')],$('header'));
$('#more-tools').textContent='Additional windows…';
// Phones: the data toolbar scrolls sideways, so its menus open as fixed sheets just below the toolbar.
{const bar=$('#simple-toolbar'),phone=matchMedia('(max-width:650px)'),compact=matchMedia('(max-width:900px)');
 const edge=()=>{if(phone.matches&&bar.scrollLeft+bar.clientWidth<bar.scrollWidth-2)bar.dataset.moreRight='';else delete bar.dataset.moreRight};
 bar.addEventListener('toggle',event=>{const menu=event.target;if(!menu.open||!compact.matches)return;const root=document.documentElement.style,summary=menu.querySelector('summary').getBoundingClientRect(),body=menu.querySelector('.dropdown-body');root.setProperty('--toolbar-menu-top',Math.round(bar.getBoundingClientRect().bottom+6)+'px');root.setProperty('--toolbar-menu-left',Math.round(Math.max(8,Math.min(summary.left,innerWidth-body.offsetWidth-8)))+'px')},true);
 bar.addEventListener('scroll',()=>{edge();if(phone.matches)bar.querySelectorAll('.ui-dropdown[open]').forEach(menu=>menu.open=false)},{passive:true});
 document.addEventListener('scroll',event=>{if(compact.matches&&event.target!==bar&&!event.target.closest?.('.dropdown-body'))bar.querySelectorAll('.ui-dropdown[open]').forEach(menu=>menu.open=false)},{capture:true,passive:true});
 addEventListener('resize',edge);new ResizeObserver(edge).observe(bar);new MutationObserver(edge).observe(bar,{subtree:true,attributes:true,attributeFilter:['hidden']})}
document.addEventListener('click',event=>{document.querySelectorAll('.ui-dropdown[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false})});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){const menu=document.querySelector('.ui-dropdown[open]');if(menu){menu.open=false;menu.querySelector('summary').focus()}}});
