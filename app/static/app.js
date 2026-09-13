const $ = s => document.querySelector(s);
const esc = s => (s ?? '').toString().replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtBytes = n => n < 1024 ? `${n} B` : n < 1024*1024 ? `${(n/1024).toFixed(1)} KB` : `${(n/1024/1024).toFixed(2)} MB`;

function safeSnippet(s){ return esc(s).replaceAll('&lt;mark&gt;','<mark>').replaceAll('&lt;/mark&gt;','</mark>'); }
async function jfetch(url, options={}) { const r = await fetch(url, options); if(!r.ok) throw new Error(await r.text()); const t=await r.text(); return t?JSON.parse(t):{}; }
function askDelete(label){ return confirm(`Delete ${label}? This cannot be undone.`); }

async function loadStats(){
  const s=await jfetch('/api/stats');
  $('#stats').innerHTML=`
    <div class="stat"><b>${Number(s.documents).toLocaleString()}</b><span>Documents</span></div>
    <div class="stat"><b>${Number(s.domains).toLocaleString()}</b><span>Domains</span></div>
    <div class="stat"><b>${Number(s.characters).toLocaleString()}</b><span>Characters</span></div>
    <div class="stat"><b>${Number(s.jobs).toLocaleString()}</b><span>Search Jobs</span></div>`;
}

async function loadJobs(){
  const jobs=await jfetch('/api/jobs');
  $('#jobs').innerHTML=jobs.length?jobs.map(x=>{
    const denom=Math.max(1,x.found||x.requested_results);
    const pct=Math.min(100,Math.round((x.crawled||0)*100/denom));
    return `<div class="job">
      <div class="row top-row">
        <div><b>${esc(x.query)}</b><div class="muted">requested ${Number(x.requested_results||0).toLocaleString()} · found ${Number(x.found||0).toLocaleString()} · crawled ${Number(x.crawled||0).toLocaleString()} · failed ${Number(x.failed||0).toLocaleString()}</div></div>
        <div class="actions"><span class="status">${esc(x.status)}</span><button class="danger" onclick="deleteJob('${x.id}')">Delete</button></div>
      </div>
      <div class="progress"><i style="width:${pct}%"></i></div>
      ${x.error?`<p class="hint error-text">${esc(x.error)}</p>`:''}
    </div>`
  }).join(''):'<p class="muted">No jobs yet.</p>';
}

async function deleteJob(id){
  if(!askDelete('this search job from history')) return;
  try{ await jfetch('/api/jobs/'+encodeURIComponent(id),{method:'DELETE'}); await Promise.all([loadJobs(),loadStats()]); }
  catch(e){ alert(e.message); }
}
window.deleteJob=deleteJob;

async function startSearch(){
  const query=$('#web-query').value.trim();
  if(!query)return;
  const maxResults=Number($('#max-results').value||100);
  if(maxResults<1 || maxResults>10000){ alert('Result count must be between 1 and 10,000.'); return; }
  $('#start-search').disabled=true;
  try{
    await jfetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,max_results:maxResults})});
    await loadJobs();
  }catch(e){alert(e.message)}finally{$('#start-search').disabled=false;}
}

async function loadLibrary(){
  const q=$('#library-query').value.trim();
  const docs=await jfetch('/api/library?q='+encodeURIComponent(q)+'&limit=200');
  $('#library-results').innerHTML=docs.length?docs.map(d=>`<article class="doc">
    <div class="domain">${esc(d.domain)}</div>
    <h3>${esc(d.title||'Untitled')}</h3>
    <p>${safeSnippet(d.snippet || d.description || '')}</p>
    <div class="row"><span class="muted">${Number(d.characters||0).toLocaleString()} chars</span><div class="actions"><button onclick="openDoc(${d.id})">Read</button><button class="danger" onclick="deleteDoc(${d.id})">Delete</button></div></div>
  </article>`).join(''):'<p class="muted">No documents found.</p>';
}

async function openDoc(id){
  const d=await jfetch('/api/library/'+id);
  $('#doc-title').textContent=d.title||'Untitled';
  $('#doc-meta').textContent=`${d.domain||''} · ${d.final_url||d.url||''}`;
  $('#doc-content').textContent=d.markdown||'';
  $('#doc-dialog').showModal();
}
window.openDoc=openDoc;

async function deleteDoc(id){
  if(!askDelete('this document from the local library')) return;
  try{ await jfetch('/api/library/'+id,{method:'DELETE'}); await Promise.all([loadLibrary(),loadStats()]); }
  catch(e){ alert(e.message); }
}
window.deleteDoc=deleteDoc;

function downloadButtons(kind, stem, files){
  const order=kind==='archives'?['zip','json','csv','md']:['md','json','csv'];
  return order.filter(fmt=>files && files[fmt]).map(fmt=>
    `<a href="/api/${kind}/${encodeURIComponent(stem)}/${fmt}/download"><button class="format-btn ${fmt}">${fmt.toUpperCase()}</button></a>`
  ).join(' ');
}

async function loadArchives(){
  const rows=await jfetch('/api/archives');
  $('#archives').innerHTML=rows.length?rows.map(x=>`<div class="archive item-block">
    <div class="item-title"><div><b>${esc(x.stem)}</b><div class="muted">${fmtBytes(x.total_size||0)}</div></div><button class="danger" onclick="deleteArchive('${encodeURIComponent(x.stem)}')">Delete</button></div>
    <div class="export-row">${downloadButtons('archives',x.stem,x.files)} <button class="primary small" onclick="buildCorpus('${encodeURIComponent(x.stem)}')">Build clean corpus</button></div>
  </div>`).join(''):'<p class="muted">No archives yet.</p>';
}

async function buildCorpus(stem){
  try{
    const r=await jfetch('/api/archives/'+stem+'/build-corpus',{method:'POST'});
    alert(`Clean corpus created\n${Number(r.documents_saved).toLocaleString()} documents\n${Number(r.characters).toLocaleString()} characters\nFormats: MD, JSON, CSV`);
    await loadCorpora();
  }catch(e){alert(e.message)}
}
window.buildCorpus=buildCorpus;

async function deleteArchive(stem){
  const decoded=decodeURIComponent(stem);
  if(!askDelete(`archive "${decoded}" and all of its ZIP/JSON/CSV/MD exports`)) return;
  try{ await jfetch('/api/archives/'+encodeURIComponent(decoded),{method:'DELETE'}); await loadArchives(); }
  catch(e){alert(e.message)}
}
window.deleteArchive=deleteArchive;

async function loadCorpora(){
  const rows=await jfetch('/api/corpora');
  $('#corpora').innerHTML=rows.length?rows.map(x=>`<div class="corpus item-block">
    <div class="item-title"><div><b>${esc(x.stem)}</b><div class="muted">${fmtBytes(x.total_size||0)}</div></div><button class="danger" onclick="deleteCorpus('${encodeURIComponent(x.stem)}')">Delete</button></div>
    <div class="export-row">${downloadButtons('corpora',x.stem,x.files)}</div>
  </div>`).join(''):'<p class="muted">No corpora yet.</p>';
}

async function deleteCorpus(stem){
  const decoded=decodeURIComponent(stem);
  if(!askDelete(`clean corpus "${decoded}" in MD/JSON/CSV formats`)) return;
  try{ await jfetch('/api/corpora/'+encodeURIComponent(decoded),{method:'DELETE'}); await loadCorpora(); }
  catch(e){alert(e.message)}
}
window.deleteCorpus=deleteCorpus;

document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  $('#tab-'+b.dataset.tab).classList.add('active');
  if(b.dataset.tab==='library')loadLibrary();
  if(b.dataset.tab==='archives'){loadArchives();loadCorpora();}
}));
$('#start-search').onclick=startSearch;
$('#refresh-jobs').onclick=loadJobs;
$('#library-search').onclick=loadLibrary;
$('#library-query').addEventListener('keydown',e=>{if(e.key==='Enter')loadLibrary()});
$('#web-query').addEventListener('keydown',e=>{if(e.key==='Enter')startSearch()});
$('#doc-close').onclick=()=>$('#doc-dialog').close();
loadStats();loadJobs();setInterval(()=>{loadJobs();loadStats()},4000);
