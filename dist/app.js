let jobs = [];

const state = {
  read:new Set(JSON.parse(localStorage.getItem("klidna-read")||"[]")),
  saved:new Set(JSON.parse(localStorage.getItem("klidna-saved")||"[]")),
  hidden:new Set(JSON.parse(localStorage.getItem("klidna-hidden")||"[]"))
};
const $=s=>document.querySelector(s);
const persist=()=>{for(const k of ["read","saved","hidden"])localStorage.setItem("klidna-"+k,JSON.stringify([...state[k]]));};
const esc=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function filtered(){
  const q=$("#search").value.trim().toLocaleLowerCase("cs");
  const cat=$("#category").value, loc=$("#location").value, status=$("#status").value;
  return jobs.filter(j=>{
    const statusOk=status==="hidden"?state.hidden.has(j.id):status==="saved"?state.saved.has(j.id)&&!state.hidden.has(j.id):!state.hidden.has(j.id);
    return statusOk&&(cat==="all"||j.category===cat)&&(loc==="all"||j.location===loc)&&(!q||[j.title,j.company,j.place,j.why,j.description].join(" ").toLocaleLowerCase("cs").includes(q));
  });
}
function render(){
  const root=$("#jobs"); root.innerHTML="";
  const list=filtered();
  list.forEach(j=>{
    const el=$("#jobTemplate").content.firstElementChild.cloneNode(true);
    el.dataset.id=j.id; el.classList.toggle("read",state.read.has(j.id)); el.classList.toggle("saved",state.saved.has(j.id));
    el.querySelector(".rank").textContent=j.rank;
    el.querySelector(".tags").innerHTML=j.tags.map(t=>'<span class="tag '+t[1]+'">'+esc(t[0])+"</span>").join("");
    el.querySelector(".date").textContent=j.date;
    el.querySelector(".title").textContent=j.title;
    el.querySelector(".company").textContent=j.company;
    el.querySelector(".facts").innerHTML='<span>⌖ '+esc(j.place)+'</span><span>◷ Plný úvazek</span><span>◈ '+esc(j.salary)+'</span>';
    el.querySelector(".why").textContent=j.why;
    el.querySelector(".description").textContent=j.description;
    el.querySelector(".apply").href=j.url;
    el.querySelector(".source").textContent="Zdroj: "+j.source;
    const save=el.querySelector(".save"); save.textContent=state.saved.has(j.id)?"♥":"♡";
    save.onclick=()=>{state.saved.has(j.id)?state.saved.delete(j.id):state.saved.add(j.id);persist();render();};
    el.querySelector(".hide").onclick=()=>{state.hidden.has(j.id)?state.hidden.delete(j.id):state.hidden.add(j.id);persist();render();};
    el.querySelector("details").addEventListener("toggle",()=>{state.read.add(j.id);persist();updateCounts();el.classList.add("read");});
    el.querySelector(".apply").addEventListener("click",()=>{state.read.add(j.id);persist();updateCounts();});
    root.appendChild(el);
  });
  $("#empty").hidden=list.length>0; updateCounts(list.length);
}
function updateCounts(visible=filtered().length){
  $("#visibleCount").textContent=visible;
  $("#newCount").textContent=jobs.filter(j=>!state.read.has(j.id)&&!state.hidden.has(j.id)).length;
}
["search","category","location","status"].forEach(id=>$("#"+id).addEventListener(id==="search"?"input":"change",render));
$("#markRead").onclick=()=>{jobs.forEach(j=>state.read.add(j.id));persist();render();};

fetch("data/jobs.json", {cache:"no-store"})
  .then(r=>{if(!r.ok) throw new Error("Data nejsou dostupná"); return r.json();})
  .then(data=>{
    jobs=(data.jobs||[]).map((j,i)=>({...j,rank:i+1}));
    $("#checkedAt").textContent="Ověřeno "+(data.checked_display||"nedávno");
    render();
  })
  .catch(()=>{
    $("#checkedAt").textContent="Ověření se nepodařilo načíst";
    $("#empty h2").textContent="Nabídky se nepodařilo načíst";
    $("#empty p").textContent="Zkuste stránku obnovit později.";
    render();
  });
