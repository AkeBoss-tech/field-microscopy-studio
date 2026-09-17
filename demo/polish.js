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
document.addEventListener('click',event=>{document.querySelectorAll('.ui-dropdown[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false})});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){const menu=document.querySelector('.ui-dropdown[open]');if(menu){menu.open=false;menu.querySelector('summary').focus()}}});
