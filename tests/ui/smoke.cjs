// Browser smoke test for the main studio flows. Requires Playwright (npm i playwright) and a running server:
//   STUDIO_ROOT=$PWD STUDIO_STORE=/tmp/field-ui-store .venv/bin/python app/server.py --port 8777
//   node tests/ui/smoke.cjs [http://localhost:8777] [output-dir]
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path');
const base=process.argv[2]||'http://localhost:8777',out=process.argv[3]||fs.mkdtempSync('/tmp/field-ui-');
const checks=[];const check=(name,ok,detail='')=>{checks.push({name,ok,detail});console.log((ok?'PASS ':'FAIL ')+name+(detail?' · '+detail:''))};
(async()=>{
 const browser=await chromium.launch({args:['--ignore-gpu-blocklist','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{try{for(const k of ['field-tour-done','field-tour-process','field-tour-review'])localStorage.setItem(k,'1')}catch{}});
 await page.goto(base);await page.waitForFunction(()=>typeof state!=='undefined'&&state.meta,null,{timeout:60000});
 const js=(f,a)=>page.evaluate(f,a),wait=ms=>page.waitForTimeout(ms);
 await js(()=>{const s=document.querySelector('#dataset');s.value='hair-control';s.dispatchEvent(new Event('change'))});await wait(3000);
 check('channel names from lab workbook',(await js(()=>state.meta.channels.join(',')))==='Myo7a,tdTomato,Phalloidin,DAPI');
 // Example loads (idempotent) and the reference card compares counts.
 const loaded=await js(()=>!!state.runs.find(r=>/Example · OHC/.test(r.title)));
 if(!loaded){await page.click('.example-card .primary-action');await page.waitForFunction(()=>state.tab==='Review',null,{timeout:120000})}
 const runs=await js(()=>state.runs.filter(r=>/Example/.test(r.title)).map(r=>r.objects).sort((a,b)=>a-b).join(','));check('example runs 21 IHC / 69 OHC',runs==='21,69',runs);
 await js(()=>{const r=state.runs.find(r=>/Example · OHC/.test(r.title));chooseResult(r.id);state.tab='Review';renderLayout()});await wait(2000);
 await js(()=>setReviewView('candidates'));await page.waitForSelector('.reference-card',{timeout:20000}).catch(()=>{});
 const ref=await js(()=>document.querySelector('.reference-card')?.innerText||'');check('manual reference card',/71/.test(ref)&&/69 candidates/.test(ref));
 // 3D render modes and single-cell view.
 await js(()=>{state.tab='Explore';state.mode='volume';renderLayout()});await wait(6000);
 for(const mode of ['volume','maximum','surface','mixed']){await js(m=>document.querySelector(`[data-render-mode="${m}"]`).click(),mode);await wait(1500)}
 check('render dock present',await js(()=>document.querySelector('.render-modes')?.querySelectorAll('button').length===4));
 await js(()=>document.querySelector('.results-toggle').click());await wait(600);check('results panel collapses',await js(()=>document.body.classList.contains('sidebar-collapsed')&&document.querySelector('#result-sidebar').getBoundingClientRect().width<4));
 await js(()=>document.querySelector('.results-edge').click());await wait(600);check('results panel reopens',await js(()=>!document.body.classList.contains('sidebar-collapsed')));
 await js(()=>openIsolatedCell({id:34}));await wait(6000);
 check('cell navigator',/Cell #34/.test(await js(()=>document.querySelector('.cell-navigator')?.innerText||'')));
 check('neighbour labels toggle',await js(()=>!!document.querySelector('.cell-navigator [data-cell-labels]')));
 // High-resolution export with metadata.
 await js(()=>{exportPrefs.scale=2;exportPrefs.caption=true});
 await page.click('.tool-rail .save-view');await page.waitForSelector('.export-dialog');
 const [download]=await Promise.all([page.waitForEvent('download',{timeout:60000}),page.click('.export-dialog .dialog-actions .primary')]);
 const file=path.join(out,download.suggestedFilename());await download.saveAs(file);
 const png=fs.readFileSync(file),hasMeta=png.includes(Buffer.from('field:view')),w=png.readUInt32BE(16),h=png.readUInt32BE(20);
 check('export PNG with metadata',hasMeta&&w>=2000,`${w}×${h} ${file}`);
 // Share link round-trip.
 const link=await js(()=>location.origin+location.pathname+'#view='+encodeView());
 const page2=await context.newPage();await page2.goto(link);await page2.waitForFunction(()=>typeof state!=='undefined'&&state.focusObject?.id===34,null,{timeout:60000}).then(()=>check('share link reopens cell #34',true)).catch(()=>check('share link reopens cell #34',false));
 await js(()=>{state.focusObject=null;state.tab='Review';renderLayout()});await wait(2500);
 await js(()=>openWorkspaceGuide());await wait(1200);check('review walkthrough',/Review · 1 of/i.test(await js(()=>document.querySelector('.tour-step')?.textContent||'')));
 await js(()=>document.querySelector('.tour-layer')?.remove());
 check('no page errors',!errors.length,errors.join(' | '));
 await browser.close();
 fs.writeFileSync(path.join(out,'smoke.json'),JSON.stringify(checks,null,1));
 process.exit(checks.every(c=>c.ok)?0:1);
})();
