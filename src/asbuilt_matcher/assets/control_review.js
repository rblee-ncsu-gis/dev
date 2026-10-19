/* Local draft collection only. Python validates and commits into a new snapshot. */
"use strict";
const DATA = JSON.parse(document.getElementById("collection-data").textContent);
const $ = id => document.getElementById(id);
let records = structuredClone(DATA.registry.records), operations = [], selected = null, pick = null;
let geographicExtra = {}, dirty = false;
const num = id => $(id).value.trim() === "" ? null : Number($(id).value);
const pair = (a,b) => num(a) === null || num(b) === null ? null : [num(a),num(b)];
const put = (id,v) => {$(id).value = v ?? "";};
const say = (s,error=false) => {$("message").textContent=s;$("message").className=error?"error":"";};
const uid = () => globalThis.crypto?.randomUUID?.() || `draft-${Date.now()}-${Math.random().toString(16).slice(2)}`;
function actor() {
  if (!$("author").value.trim() || !$("reason").value.trim()) throw Error("Enter actor name and audit reason.");
  return {operation_id:uid(),author:$("author").value.trim(),reviewer_type:$("reviewer-type").value,reason:$("reason").value.trim(),independent:false};
}
function showSheet() {
  document.querySelectorAll(".sheet").forEach(e=>{e.hidden=e.dataset.sheet!==$("sheet-select").value;});
}
function showMode() {$("control-fields").hidden=$("mode").value!=="control";$("tie-fields").hidden=$("mode").value!=="tie";}
function drawMarkers() {
  document.querySelectorAll(".drawing").forEach(svg=>{
    const g=svg.querySelector(".markers");g.replaceChildren();
    const drawing=DATA.registry.drawings[Number(svg.dataset.drawing)];
    records.filter(r=>r.record_type==="control"&&r.drawing_id===drawing.drawing_id&&r.pixel).forEach(r=>{
      const c=document.createElementNS("http://www.w3.org/2000/svg","circle");
      c.setAttribute("cx",r.pixel[0]);c.setAttribute("cy",r.pixel[1]);c.setAttribute("r",12);
      const t=document.createElementNS(c.namespaceURI,"title");t.textContent=r.id; c.append(t);g.append(c);
    });
  });
}
function render() {
  const body=$("records");body.replaceChildren();
  for(const r of records){
    const tr=document.createElement("tr");
    for(const v of [r.id,r.record_type+(r.role?" / "+r.role:""),r.description,r.proposer_type,r.draft?"Draft; not committed":r.verification_status]){
      const td=document.createElement("td");td.textContent=v??"";tr.append(td);
    }
    const td=document.createElement("td"),b=document.createElement("button");b.textContent="Inspect / edit";b.onclick=()=>load(r);td.append(b);tr.append(td);body.append(tr);
  }
  $("queue").textContent=JSON.stringify({registry_sha256:DATA.registry_sha256,operations},null,2);
  drawMarkers();
}
function load(r){
  selected=r.id;$("editing").textContent="Selected "+r.id;$("mode").value=r.record_type;showMode();
  put("description",r.description);put("source",r.evidence?.source);put("source-date",r.evidence?.source_date);
  put("source-reference",r.evidence?.source_reference);put("point-identity",r.evidence?.point_identity);
  put("historical",r.evidence?.historical_consistency||r.historical_change_notes);
  $("independent-evidence").checked=r.evidence?.independently_determined===true;$("independent-review").checked=false;
  if(r.record_type==="control"){
    $("sheet-select").value=DATA.registry.drawings.findIndex(d=>d.drawing_id===r.drawing_id);showSheet();
    put("pixel-x",r.pixel?.[0]);put("pixel-y",r.pixel?.[1]);put("geo-x",r.geographic?.x);put("geo-y",r.geographic?.y);
    $("crs").value=r.geographic?.crs||DATA.registry.target_crs;put("feature-type",r.feature_type);put("feature-id",r.reference_feature_id);
    put("accuracy",r.estimated_accuracy_m);$("role").value=r.role;$("independent-fit").checked=r.independent_of_fit===true;
    geographicExtra={transformed_geographic:r.transformed_geographic??null,source_sha256:r.evidence?.source_sha256??null};
  }else{
    $("left-sheet").value=DATA.registry.drawings.findIndex(d=>d.drawing_id===r.left_drawing_id);
    $("right-sheet").value=DATA.registry.drawings.findIndex(d=>d.drawing_id===r.right_drawing_id);
    ["left","right"].forEach(s=>{put(s+"-x",r[s+"_pixel"]?.[0]);put(s+"-y",r[s+"_pixel"]?.[1]);});
    put("station",r.station_text);$("station-verified").checked=r.station_verified===true;
  }
}
function save(){
  try{
    const a=actor(),mode=$("mode").value,existing=records.find(r=>r.id===selected);
    if(existing&&existing.record_type!==mode)throw Error("Start a new record to change correspondence type.");
    if(!$("description").value.trim())throw Error("Describe the physical point.");
    const evidence={source:$("source").value,source_date:$("source-date").value||null,source_reference:$("source-reference").value,
      point_identity:$("point-identity").value,historical_consistency:$("historical").value,independently_determined:$("independent-evidence").checked,
      model_input_landmark:false,source_sha256:geographicExtra.source_sha256??null};
    let values={description:$("description").value,evidence,historical_change_notes:$("historical").value};
    if(mode==="control"){
      const x=num("geo-x"),y=num("geo-y"),crs=$("crs").value;
      values={...values,pixel:pair("pixel-x","pixel-y"),geographic:x===null||y===null?null:{x,y,crs,units:crs==="EPSG:2264"?"US survey foot":"degree"},
        transformed_geographic:geographicExtra.transformed_geographic??null,feature_type:$("feature-type").value,reference_feature_id:$("feature-id").value,
        role:$("role").value,estimated_accuracy_m:num("accuracy"),independent_of_fit:$("independent-fit").checked};
      if(!existing)values.drawing_id=DATA.registry.drawings[Number($("sheet-select").value)].drawing_id;
    }else{
      values={...values,left_pixel:pair("left-x","left-y"),right_pixel:pair("right-x","right-y"),station_text:$("station").value||null,station_verified:$("station-verified").checked};
      if(!existing){values.left_drawing_id=DATA.registry.drawings[Number($("left-sheet").value)].drawing_id;values.right_drawing_id=DATA.registry.drawings[Number($("right-sheet").value)].drawing_id;}
    }
    const id=selected||uid();operations.push({...a,id,action:existing?"edit":mode==="control"?"add_control":"add_tie",values});
    if(existing)Object.assign(existing,values,{draft:true,last_evidence_author:a.author});
    else records.push({...values,id,record_type:mode,proposer_type:a.reviewer_type,last_evidence_author:a.author,draft:true});
    selected=id;dirty=true;render();say("Proposal/edit queued. Download and apply to preserve it; any existing approval will reset.");
  }catch(e){say(e.message,true);}
}
function review(status){
  try{
    if(!selected)throw Error("Select a correspondence first.");const a=actor(),r=records.find(x=>x.id===selected);
    a.independent=$("independent-review").checked;
    if(status==="verified"&&(a.reviewer_type!=="human"||!a.independent||a.author.toLowerCase()===r.last_evidence_author?.trim().toLowerCase()))
      throw Error("Independent approval needs an explicit human attestation and a reviewer distinct from the latest evidence author.");
    operations.push({...a,id:selected,action:"review",status});dirty=true;render();say("Review decision queued, not committed. Python will validate complete source evidence.");
  }catch(e){say(e.message,true);}
}
$("sheet-select").onchange=()=>{
  const r=records.find(x=>x.id===selected),d=DATA.registry.drawings[Number($("sheet-select").value)];
  if(r?.record_type==="control"&&r.drawing_id!==d.drawing_id){
    $("sheet-select").value=DATA.registry.drawings.findIndex(x=>x.drawing_id===r.drawing_id);
    say("A control stays bound to its original sheet. Start a new record to collect another sheet.",true);
  }
  showSheet();
};$("mode").onchange=showMode;
document.querySelectorAll(".zoom").forEach(e=>{e.oninput=()=>{e.closest("section").querySelector(".drawing").style.width=Number(e.value)*100+"%";};});
document.querySelectorAll(".drawing").forEach(svg=>{svg.onclick=event=>{
  const r=records.find(x=>x.id===selected),d=DATA.registry.drawings[Number(svg.dataset.drawing)];
  if(r?.record_type==="control"&&r.drawing_id!==d.drawing_id){say("Image pick belongs to a different sheet. Start a new record.",true);return;}
  const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());
  pick={sheet:Number(svg.dataset.drawing),xy:[p.x,p.y]};put("pixel-x",p.x);put("pixel-y",p.y);
  say("Image pick recorded in original composition pixels. Add geographic evidence separately.");
};});
function vertexList(geometry){const c=geometry.coordinates,t=geometry.type;if(t==="Point")return[c];if(t==="LineString")return c;if(t==="Polygon"||t==="MultiLineString")return c.flat();if(t==="MultiPolygon")return c.flat(2);return c;}
document.querySelectorAll(".reference-pick").forEach(e=>{const select=()=>{
  const f=DATA.reference_features.features[Number(e.dataset.feature)],p=vertexList(f.geometry)[Number(e.dataset.vertex)];
  $("crs").value="EPSG:4326";put("geo-x",p[0]);put("geo-y",p[1]);put("source",f.source);put("source-reference",f.native_id+" / vertex "+e.dataset.vertex);
  put("source-date",f.source_date?.slice(0,10));put("feature-id",f.native_id);put("feature-type",f.kind+" source vertex");
  geographicExtra={source_sha256:f.source_sha256,transformed_geographic:null};$("independent-evidence").checked=false;
  say("Source GIS vertex proposed. Verify physical identity and historical consistency; no acceptance or accuracy inferred.");
};e.onclick=select;e.onkeydown=ev=>{if(ev.key==="Enter")select();};});
["left","right"].forEach(side=>{$("pick-"+side).onclick=()=>{
  if(!pick){say("Click the relevant drawing first.",true);return;}
  $(side+"-sheet").value=pick.sheet;put(side+"-x",pick.xy[0]);put(side+"-y",pick.xy[1]);
};});
$("save").onclick=save;$("approve").onclick=()=>review("verified");$("reject").onclick=()=>review("rejected");$("unreadable").onclick=()=>review("unreadable");
$("new").onclick=()=>{selected=null;pick=null;geographicExtra={};$("editing").textContent="New record";
  for(const id of ["description","pixel-x","pixel-y","geo-x","geo-y","feature-type","feature-id","accuracy","source","source-date","source-reference","point-identity","historical","left-x","left-y","right-x","right-y","station"])put(id,"");
  for(const id of ["independent-evidence","independent-review","independent-fit","station-verified"])$(id).checked=false;
};
$("download").onclick=()=>{
  const blob=new Blob([JSON.stringify({schema_version:1,registry_sha256:DATA.registry_sha256,operations},null,2)],{type:"application/json"});
  const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="control-decisions.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);dirty=false;
  say("Draft downloaded. Apply with controls-apply into a new output directory.");
};
$("draft-file").onchange=async()=>{try{
  const file=$("draft-file").files[0];if(!file)return;const draft=JSON.parse(await file.text());
  if(draft.registry_sha256!==DATA.registry_sha256||!Array.isArray(draft.operations))throw Error("Draft does not match this frozen registry.");
  if(operations.length)throw Error("Download the current draft and reopen this page before loading another draft.");
  operations=draft.operations;dirty=true;render();say("Draft loaded for export; Python remains the validation authority. Imported operations appear in the queue; apply them before editing their resulting records.");
}catch(e){say(e.message,true);}};
window.addEventListener("beforeunload",e=>{if(dirty){e.preventDefault();e.returnValue="Download your decision draft before leaving.";}});
if(DATA.registry.drawings.length>1)$("right-sheet").value="1";
["geo-x","geo-y","crs"].forEach(id=>{$(id).addEventListener("change",()=>{geographicExtra.transformed_geographic=null;});});
$("crs").value=DATA.registry.target_crs;showMode();showSheet();render();
