const $ = s => document.querySelector(s);
const esc = s => (s ?? '').toString().replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function safeSnippet(s){ return esc(s).replaceAll('&lt;mark&gt;','<mark>').replaceAll('&lt;/mark&gt;','</mark>'); }

async function jfetch(url, options={}) { const r = await fetch(url, options); if(!r.ok) throw new Error(await r.text()); return r.json(); }

async function loadStats(){ const s=await jfetch('/api/stats'); $('#stats').innerHTML=`<div class="stat"><b>${s.documents}</b><span>Documents</span></div><div class="stat"><b>${s.domains}</b><span>Domains</span></div><div class="stat"><b>${Number(s.characters).toLocaleString()}</b><span>Characters</span></div><div class="stat"><b>${s.jobs}</b><span>Search Jobs</span></div>`; }

async function loadJobs(){ const jobs=await jfetch('/api/jobs'); $('#jobs').innerHTML=jobs.length?jobs.map(x=>{const denom=Math.max(1,x.found||x.requested_results);const pct=Math.min(100,Math.round((x.crawled||0)*100/denom));return `<div class="job"><div class="row"><div><b>${esc(x.query)}</b><div class="muted">found ${x.found||0} · crawled ${x.crawled||0} · failed ${x.failed||0}</div></div><span class="status">${esc(x.status)}</span></div><div class="progress"><i style="width:${pct}%"></i></div>${x.error?`<p class="hint">${esc(x.error)}</p>`:''}</div>`}).join(''):'<p class="muted">No jobs yet.</p>'; }

async function startSearch(){ const query=$('#web-query').value.trim(); if(!query)return; $('#start-search').disabled=true; try{await jfetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,max_results:Number($('#max-results').value||100)})}); await loadJobs();}catch(e){alert(e.message)}finally{$('#start-search').disabled=false;} }

async function loadLibrary(){ const q=$('#library-query').value.trim(); const docs=await jfetch('/api/library?q='+encodeURIComponent(q)); $('#library-results').innerHTML=docs.length?docs.map(d=>`<article class="doc"><div class="domain">${esc(d.domain)}</div><h3>${esc(d.title||'Untitled')}</h3><p>${safeSnippet(d.snippet || d.description || '')}</p><div class="row"><span class="muted">${Number(d.characters||0).toLocaleString()} chars</span><button onclick="openDoc(${d.id})">Read</button></div></article>`).join(''):'<p class="muted">No documents found.</p>'; }

async function openDoc(id){const d=await jfetch('/api/library/'+id);$('#doc-title').textContent=d.title||'Untitled';$('#doc-meta').textContent=`${d.domain||''} · ${d.final_url||d.url||''}`;$('#doc-content').textContent=d.markdown||'';$('#doc-dialog').showModal();}
window.openDoc=openDoc;

async function loadArchives(){const a=await jfetch('/api/archives');$('#archives').innerHTML=a.length?a.map(x=>`<div class="archive row"><div><b>${esc(x.name)}</b><div class="muted">${(x.size/1024/1024).toFixed(2)} MB</div></div><div><a href="/api/archives/${encodeURIComponent(x.name)}/download"><button>ZIP</button></a> <button onclick="buildCorpus('${encodeURIComponent(x.name)}')">Build corpus</button></div></div>`).join(''):'<p class="muted">No archives yet.</p>';}
async function buildCorpus(name){try{const r=await jfetch('/api/archives/'+name+'/build-corpus',{method:'POST'});alert(`Corpus created: ${r.documents_saved} documents, ${Number(r.characters).toLocaleString()} chars`);await loadCorpora();}catch(e){alert(e.message)}}window.buildCorpus=buildCorpus;
async function loadCorpora(){const c=await jfetch('/api/corpora');$('#corpora').innerHTML=c.length?c.map(x=>`<div class="corpus row"><div><b>${esc(x.name)}</b><div class="muted">${(x.size/1024/1024).toFixed(2)} MB</div></div><a href="/api/corpora/${encodeURIComponent(x.name)}/download"><button>Download .md</button></a></div>`).join(''):'<p class="muted">No corpora yet.</p>';}

document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('#tab-'+b.dataset.tab).classList.add('active');if(b.dataset.tab==='library')loadLibrary();if(b.dataset.tab==='archives'){loadArchives();loadCorpora();}}));
$('#start-search').onclick=startSearch;$('#refresh-jobs').onclick=loadJobs;$('#library-search').onclick=loadLibrary;$('#library-query').addEventListener('keydown',e=>{if(e.key==='Enter')loadLibrary()});$('#doc-close').onclick=()=>$('#doc-dialog').close();
loadStats();loadJobs();setInterval(()=>{loadJobs();loadStats()},4000);
