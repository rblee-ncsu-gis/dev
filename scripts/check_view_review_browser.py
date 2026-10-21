"""Optional installed-Edge check. Simulated AI drafts are never saved or applied."""

import argparse
import html
import json
from pathlib import Path
import re
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('collection')
    parser.add_argument('--output',required=True)
    parser.add_argument('--browser',default=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    args=parser.parse_args()
    source,output=Path(args.collection).resolve(),Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    script=r'''
<script>
(async()=>{try{
const check=(ok,s)=>{if(!ok)throw Error(s);},set=(id,v)=>document.getElementById(id).value=v;
check(document.querySelector('#view-select').options.length===R.views.length,'View list');
set('author','SYNTHETIC UI actor');set('reason','SYNTHETIC browser-only draft; never applied');set('reviewer-type','ai');document.querySelector('#independent').checked=true;
document.querySelector('#approve-view').click();check(document.querySelector('#message').textContent.includes('human'),'AI acceptance blocked');
set('reviewer-type','human');set('author',current.last_evidence_author);document.querySelector('#approve-view').click();check(document.querySelector('#message').textContent.includes('own evidence'),'Self acceptance blocked');
set('reviewer-type','ai');set('author','SYNTHETIC UI actor');document.querySelector('#independent').checked=false;
const svg=document.querySelector('.drawing');svg.setPointerCapture=()=>{};
const pointer=(kind,x,y)=>{const p=new DOMPoint(x,y).matrixTransform(svg.getScreenCTM());svg.dispatchEvent(new PointerEvent(kind,{clientX:p.x,clientY:p.y,bubbles:true,pointerId:1}));};
const initial=current.spec.bbox;
pointer('pointerdown',initial[0]+5,initial[1]+5);pointer('pointerup',initial[2]-5,initial[3]-5);
check(Math.abs(Number(document.querySelector('#x0').value)-(initial[0]+5))<.1,'Page coordinate drag');
set('zoom',2);document.querySelector('#zoom').oninput();document.querySelector('.canvas').scrollLeft=50;
set('pick-mode','bar');pointer('pointerdown',initial[0]+20,initial[1]+20);pointer('pointerdown',initial[0]+100,initial[1]+20);
check(Math.abs(Number(document.querySelector('#a-x').value)-(initial[0]+20))<.1,'Zoom/scroll page coordinate pick');
check(document.querySelector('.bar').getAttribute('visibility')==='visible','Bar overlay');
document.querySelector('#save-view').click();check(operations.length===1&&operations[0].action==='edit','View draft queued');
const index=R.views.findIndex(v=>R.pages[v.page_id].native_segments.length);
if(index>=0){set('view-select',index);document.querySelector('#view-select').onchange();set('native-segment','0');document.querySelector('#use-segment').click();document.querySelector('#calculate').click();check(document.querySelector('#measurement').textContent.includes('unresolved'),'Unknown ground distance stays unresolved');document.querySelector('#save-scale').click();check(operations.at(-1).spec.native_segment!==null,'Native segment binding');}
let captured;URL.createObjectURL=b=>{captured=b;return 'blob:synthetic-test';};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=function(){};
document.querySelector('#download').click();const data=JSON.parse(await captured.text());check(data.registry_sha256===DATA.registry_sha256,'Parent hash binding');check(data.operations.every(o=>o.independent===false&&o.reviewer_type==='ai'),'No human approvals in simulated drafts');
const p=document.createElement('pre');p.id='browser-check-result';p.textContent=JSON.stringify({status:'passed',checks:['view selection','AI acceptance blocked','self acceptance blocked','page-coordinate boundary drag','zoom/scroll coordinate pick','bar overlay','native segment binding','unknown ground distance unresolved','hash-bound export','no human approvals'],simulated_decisions_applied:false});document.body.append(p);
set('view-select',0);document.querySelector('#view-select').onchange();set('zoom',1);document.querySelector('#zoom').oninput();
}catch(e){const p=document.createElement('pre');p.id='browser-check-result';p.textContent=JSON.stringify({status:'failed',error:e.stack||String(e)});document.body.append(p);}})();
</script>
'''
    page=(source/'REVIEW.html').read_text(encoding='utf-8').replace('<meta charset=',f'<base href="{html.escape(source.as_uri(),quote=True)}/"><meta charset=',1)
    path=output/'browser-smoke.html';path.write_text(page.replace('</html>',script+'</html>'),encoding='utf-8')
    command=[args.browser,'--headless','--disable-gpu','--disable-background-networking','--disable-sync','--no-first-run',
             '--allow-file-access-from-files','--user-data-dir='+str(output/'browser-profile'),'--virtual-time-budget=5000',
             '--window-size=1500,1100','--screenshot='+str(output/'review.png'),'--dump-dom',path.as_uri()]
    process=subprocess.run(command,capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    dom=process.stdout.decode('utf-8',errors='replace');marker=re.search(r'<pre id="browser-check-result">(.*?)</pre>',dom,re.S)
    result=json.loads(html.unescape(marker.group(1))) if marker else {'status':'browser_unavailable','returncode':process.returncode,'diagnostic':process.stderr.decode('utf-8',errors='replace')[-1500:]}
    (output/'browser-check-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
