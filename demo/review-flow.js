'use strict';
// A guided queue on top of the revision-checked review and correction APIs.
let reviewQueueSerial=0;
async function nextUnresolved(){
 const q=measurementContext(),serial=++reviewQueueSerial,after=reviewState.data?.object?.id||0;
 const message=$('#review-queue-message');if(message)message.textContent='Finding next candidate…';
 try{const data=await api('/api/measurements?'+query({...q,status:'unresolved',after,limit:1}));
  if(serial!==reviewQueueSerial||!measurementSame(q))return;
  if(data.next_candidate!=null){await locateMeasurement(data.next_candidate);if(message?.isConnected)message.textContent='Candidate #'+data.next_candidate+' · inspect source and depth before deciding.'}
  else if(message?.isConnected)message.textContent='No unreviewed or flagged candidates remain. Check count rules and export your review.';
 }catch(e){if(message?.isConnected&&serial===reviewQueueSerial)message.textContent=e.message}
}
const guidedReviewLayout=renderReviewWorkspace;
renderReviewWorkspace=function(){guidedReviewLayout();reviewQueueSerial++;if(!measurementEligible())return;
 const host=$('#main-host'),guide=expNode('section','review-guide');guide.setAttribute('aria-label','Review workflow');
 const title=expNode('div');title.append(expNode('h2','','Review the evidence'),expNode('p','','1 Inspect source & depth   →   2 Decide or fix the mask   →   3 Set rules & export'));
 const actions=expNode('div','review-guide-actions');actions.append(expButton('Next unresolved','exp-run',nextUnresolved),expButton('View candidate table','',()=>{setReviewView('candidates');measurementState.host.scrollIntoView({block:'start'})}));guide.append(title,actions);
 const progress=expNode('div','review-progress');progress.id='review-progress';progress.setAttribute('aria-live','polite');guide.append(progress);
 const message=expNode('p','','Unresolved includes unreviewed and flagged candidates, including edge contacts.');message.id='review-queue-message';message.role='status';guide.append(message);host.prepend(guide);
 const positions=$('#task-panel .review-position-controls'),windowInfo=$('#review-window-info');
 if(positions){const detail=expNode('details','review-coordinate-details');detail.append(expNode('summary','','Exact coordinates & intensity window'));positions.before(detail);detail.append(positions);if(windowInfo)detail.append(windowInfo)}
 const controls=host.querySelector('.review-controls');if(controls){const detail=expNode('details','review-display-details');detail.append(expNode('summary','','Image display settings'));controls.before(detail);detail.append(controls)}
 const focus=expButton('Enlarge XY views','',()=>{const active=host.classList.toggle('review-xy-focus');focus.textContent=active?'Show all depth views':'Enlarge XY views';focus.setAttribute('aria-pressed',String(active));requestAnimationFrame(drawReviewCanvases)});focus.setAttribute('aria-pressed','false');actions.append(focus);
};
const guidedCountCard=renderCountCard;
renderCountCard=function(card,data){guidedCountCard(card,data);const progress=$('#review-progress');if(!progress)return;
 progress.replaceChildren();for(const [key,label] of [['unreviewed','Unreviewed'],['needs_review','Flagged'],['accepted','Accepted'],['rejected','Rejected']]){const button=expButton(data.counts[key]+' '+label,'review-progress-item '+key,()=>{measurementState.filters.status=key;measurementState.filters.search='';measurementState.offset=0;const select=measurementState.host.querySelector('[aria-label="Decision"]');if(select)select.value=key;const search=measurementState.host.querySelector('[aria-label="Find candidate ID"]');if(search)search.value='';loadMeasurements();setReviewView('candidates');measurementState.host.scrollIntoView({block:'start'})});progress.append(button)}
 const done=data.counts.accepted+data.counts.rejected,meter=document.createElement('progress');meter.max=Math.max(1,data.total);meter.value=done;meter.setAttribute('aria-label',done+' of '+data.total+' candidates decided');progress.append(meter,expNode('span','',done+' / '+data.total+' decided'));
};
const guidedInspector=showObjectInspector;
showObjectInspector=function(data){guidedInspector(data);if(!measurementEligible()||!data.object)return;const box=$('#object-inspector'),obj=data.object,q=measurementContext();
 const old=box.querySelector('.review-decision-button');if(old)old.textContent='Edit decision / note';
 const actions=expNode('section','review-quick-actions');actions.append(expNode('p','','After checking XY, XZ and YZ:'));
 const status=expNode('p','review-quick-status');status.role='status';
 for(const [value,label] of [['accepted','Accept & next'],['rejected','Reject & next'],['needs_review','Flag & next']])actions.append(expButton(label,'quick-decision '+value,async()=>{
  if(!measurementSame(q))return;if(reviewState.host?.classList.contains('review-loading')){status.textContent='Wait for the inspection planes to finish updating before deciding.';return}actions.querySelectorAll('button').forEach(b=>b.disabled=true);status.textContent='Saving…';
  try{await api('/api/object-decision',{...q,object:obj.id,status:value,note:obj.note||'',expected_revision:obj.review_revision,expected_label_revision:obj.label_revision});if(!measurementSame(q))return;status.textContent=decisionNames[value]+' saved';await loadMeasurements();reviewState.signature=null;await nextUnresolved();scheduleReview()}
  catch(e){if(status.isConnected)status.textContent=e.message+' Re-select this candidate to load its latest revision.'}
 }));actions.append(status);box.querySelector('h3').after(actions);
};
