'use strict';
// Imported outputs use the same immutable run and review contract as local methods.
$('#import-labels-open').onclick=()=>{
 if(!state.meta){status('Choose a source image first',true);return}
 const dataset=state.dataset,channel=state.channel;
 const dialog=expModal('Import 3D instance masks','Use a TIFF produced by any external algorithm. Keep its exact source image and channel selected before importing.','external-import-dialog');
 const form=expNode('div','external-import-form');
 const source=expNode('p','external-import-source',`${state.meta.name} · C${channel+1} ${state.meta.channels[channel]} · ${state.meta.shape[0]} Z × ${state.meta.shape[2]} Y × ${state.meta.shape[3]} X`);
 const fileLabel=expNode('label','exp-field','Instance TIFF'),file=document.createElement('input');file.type='file';file.accept='.tif,.tiff';file.setAttribute('aria-label','External instance TIFF');fileLabel.append(file);
 const axesLabel=expNode('label','exp-field','Mask axes'),axes=document.createElement('select');axes.add(new Option('Read TIFF metadata',''));axes.add(new Option('ZYX · full stack','ZYX'));axes.add(new Option('YX · one-plane image','YX'));axesLabel.append(axes);
 const algorithmLabel=expNode('label','exp-field','Algorithm name'),algorithm=document.createElement('input');algorithm.maxLength=100;algorithm.placeholder='e.g. My lab model v2';algorithmLabel.append(algorithm);
 const targetLabel=expNode('label','exp-field','Objects represented'),target=document.createElement('input');target.maxLength=100;target.placeholder='e.g. nuclei, hair-cell bodies';targetLabel.append(target);
 const confirmLabel=expNode('label','external-confirm'),confirm=document.createElement('input');confirm.type='checkbox';confirmLabel.append(confirm,document.createTextNode('I checked that this mask belongs to the selected source and channel. Same shape alone does not prove alignment.'));
 const detail=expNode('p','external-import-detail','Each positive integer must identify one 3D object across Z; zero is background. Full Z and native, 2×, or 4× XY are supported. Original IDs are saved in the run.');
 const message=expNode('p','decision-message');message.role='status';file.onchange=()=>{message.textContent=file.files[0]?`${file.files[0].name} · ${(file.files[0].size/1048576).toFixed(1)} MB`:''};
 form.append(source,fileLabel,axesLabel,algorithmLabel,targetLabel,confirmLabel,detail,message);dialog.append(form);
 const actions=expNode('footer','decision-actions'),save=expButton('Import and review','exp-run',async()=>{
  if(!file.files[0]||!algorithm.value.trim()||!target.value.trim()||!confirm.checked){message.textContent='Choose a TIFF, name its algorithm and target, and confirm source alignment.';return}
  if(state.dataset!==dataset){message.textContent='The selected image changed. Reopen import for the current source.';return}
  save.disabled=true;message.textContent='Checking mask grid, IDs and source link…';
  try{
   const path='/api/import-labels?'+query({dataset,channel,name:file.files[0].name,axes:axes.value,algorithm:algorithm.value,target:target.value,alignment_confirmed:'yes'});
   const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Studio-Request':'1'},body:file.files[0]});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Import failed');
   dialog.close();await loadRuns();chooseResult(result.id);state.tab='Review';renderLayout();status(`Imported ${result.objects} objects · review the 3D boxes and masks`);
  }catch(error){message.textContent=error.message;save.disabled=false}
 });
 actions.append(expButton('Cancel','',()=>dialog.close()),save);dialog.append(actions);
};

const externalAnnotationList=fillAnnotationList;
fillAnnotationList=function(host){
 externalAnnotationList(host);
 [...host.children].forEach((row,index)=>{
  const item=state.items[index];if(item?.type!=='polyline'||item.domain!=='volume')return;
  const link=expButton(item.owner?`Neuron #${item.owner.object_id} · ${item.owner.assessment==='tentative'?'tentative':'reviewer assessed'}`:'Tag neuron','trace-owner-button',()=>openTraceOwner(item));
  link.title='Link this 3D trace to a candidate body or nucleus in any channel';row.append(link);
 });
};

function openTraceOwner(item){
 if(state.pending.length){status('Finish or discard the drawing before linking a trace',true);return}
 const runs=state.runs.filter(r=>!r.historical&&r.scope==='volume'&&['otsu','watershed','external'].includes(r.method));
 if(!runs.length){status('Run or import a 3D body/nucleus mask before linking a trace',true);return}
 const dialog=expModal('Tag a 3D neurite','Choose a candidate from a body or nucleus channel. Endpoint proximity helps navigation; it does not establish ownership.','external-import-dialog');
 const form=expNode('div','external-import-form');
 const runLabel=expNode('label','exp-field','Candidate mask'),runSelect=document.createElement('select');for(const run of runs)runSelect.add(new Option(`${run.title||run.method} · C${run.channel+1} · ${run.objects} candidates`,run.id));runSelect.value=runs.some(r=>r.id===item.owner?.run_id)?item.owner.run_id:runs.some(r=>r.id===state.run)?state.run:runs[0].id;runLabel.append(runSelect);
 const idLabel=expNode('label','exp-field','Candidate ID'),objectId=document.createElement('input');objectId.type='number';objectId.min=1;objectId.step=1;objectId.value=item.owner?.object_id||'';idLabel.append(objectId);
 const assessmentLabel=expNode('label','exp-field','Ownership assessment'),assessment=document.createElement('select');assessment.add(new Option('Tentative · inspect crossings','tentative'));assessment.add(new Option('Reviewer assessed','reviewer_assessed'));assessment.value=item.owner?.assessment||'tentative';assessmentLabel.append(assessment);
 const suggestions=expNode('div','external-owner-suggestions');const message=expNode('p','decision-message');message.role='status';form.append(runLabel,idLabel,assessmentLabel,suggestions,message);dialog.append(form);
 let labelRevision=null,candidatesLoaded=false,requestSerial=0;
 async function loadCandidates(){const runId=runSelect.value,serial=++requestSerial;labelRevision=null;candidatesLoaded=false;suggestions.textContent='Finding nearby candidates…';const a=item.points[0],b=item.points.at(-1);
  try{const result=await api('/api/owner-candidates?'+query({dataset:state.dataset,run:runId,x:a[0],y:a[1],z:a[2],x2:b[0],y2:b[1],z2:b[2]}));if(serial!==requestSerial||!dialog.isConnected)return;labelRevision=result.label_revision;candidatesLoaded=true;suggestions.replaceChildren(expNode('strong','','Near either trace endpoint'));for(const candidate of result.candidates){const button=expButton(`#${candidate.object_id} · ${candidate.distance} ${result.distance_unit}`,'',()=>{objectId.value=candidate.object_id});button.title='Distance to candidate bounding box; inspect all three planes before linking';suggestions.append(button)}suggestions.append(expNode('small','',result.caveat));if(!result.candidates.length)message.textContent='No candidates in this mask. Choose another result.'}
  catch(error){if(serial===requestSerial)message.textContent=error.message}
 }
 runSelect.onchange=()=>{objectId.value='';loadCandidates()};loadCandidates();
 const actions=expNode('footer','decision-actions');actions.append(expButton('Remove link','',()=>{snapshot();delete item.owner;updateAnnotationPanels();dialog.close();status('Trace owner link removed · saving revision')}),expButton('Cancel','',()=>dialog.close()),expButton('Save link','exp-run',()=>{if(!candidatesLoaded||!Number.isInteger(Number(objectId.value))||Number(objectId.value)<1){message.textContent='Choose a candidate ID from the current mask.';return}snapshot();item.owner={run_id:runSelect.value,object_id:Number(objectId.value),label_revision:labelRevision,assessment:assessment.value};updateAnnotationPanels();dialog.close();status('Trace link staged as '+assessment.options[assessment.selectedIndex].text+'; saving annotation revision')}));dialog.append(actions);
}
