"""Optional installed-Edge smoke check. Refuses real drawing bundles.

All generated proposals are synthetic and remain outside the real collection.
Browser profile and diagnostics are confined to the supplied synthetic bundle.
"""

import argparse
import html
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle')
    parser.add_argument('--browser', default=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    args = parser.parse_args()
    bundle = Path(args.bundle).resolve()
    registry = json.loads((bundle / 'controls.json').read_text(encoding='utf-8'))
    if not all(d['source']['source_pdf'].startswith('SYNTHETIC-') for d in registry['drawings']):
        raise ValueError('Browser smoke check is allowed only on explicitly SYNTHETIC drawing bundles')
    script = r"""
<script>
try {
 const check=(ok,s)=>{if(!ok)throw Error(s);};
 const set=(id,v)=>document.getElementById(id).value=v;
 const clickPixel=(index,x,y)=>{
   const svg=document.querySelectorAll(".drawing")[index];
   const p=new DOMPoint(x,y).matrixTransform(svg.getScreenCTM());
   svg.dispatchEvent(new MouseEvent("click",{clientX:p.x,clientY:p.y,bubbles:true}));
 };
 const pixelTolerance=index=>2/Math.abs(document.querySelectorAll(".drawing")[index].getScreenCTM().a);
 set("author","SYNTHETIC browser proposer");set("reason","SYNTHETIC browser smoke check");
 set("description","SYNTHETIC browser control");
 clickPixel(0,10,15);
 check(Math.abs(Number($("pixel-x").value)-10)<pixelTolerance(0),"Original pixel pick failed: "+$("pixel-x").value);
 const zoom=document.querySelector(".zoom");zoom.value=3;zoom.oninput();
 document.querySelector(".viewport").scrollLeft=40;
 clickPixel(0,20,25);
 check(Math.abs(Number($("pixel-x").value)-20)<pixelTolerance(0)&&Math.abs(Number($("pixel-y").value)-25)<pixelTolerance(0),"Zoom/scroll pixel mapping failed: "+$("pixel-x").value+","+$("pixel-y").value);
 document.querySelector(".reference-pick").dispatchEvent(new MouseEvent("click",{bubbles:true}));
 check($("crs").value==="EPSG:4326"&&$("feature-id").value==="SYNTHETIC-ROAD","Reference vertex proposal failed");
 set("point-identity","SYNTHETIC identity only");set("historical","SYNTHETIC unchanged feature");
 $("independent-evidence").checked=true;$("save").click();
 let draft=JSON.parse($("queue").textContent);
 check(draft.operations.length===1&&draft.operations[0].action==="add_control","Control draft was not queued");
 $("independent-review").checked=true;$("approve").click();
 check(JSON.parse($("queue").textContent).operations.length===1,"Self approval was not blocked");
 set("author","SYNTHETIC browser editor");set("description","SYNTHETIC corrected browser control");$("save").click();
 check(JSON.parse($("queue").textContent).operations[1].action==="edit","Edit not queued");
 set("sheet-select",1);$("sheet-select").onchange();
 check($("sheet-select").value==="0","Editing could silently switch source image");
 $("new").click();set("mode","tie");$("mode").onchange();
 set("sheet-select",0);$("sheet-select").onchange();clickPixel(0,15,20);$("pick-left").click();
 set("sheet-select",1);$("sheet-select").onchange();clickPixel(1,25,30);$("pick-right").click();
 set("description","SYNTHETIC adjacent-sheet tie");set("source","SYNTHETIC source drawings");
 set("source-reference","SYNTHETIC matchline");set("point-identity","SYNTHETIC corresponding feature");
 set("historical","SYNTHETIC same edition");set("station","78+75");
 $("save").click();draft=JSON.parse($("queue").textContent);
 check(draft.operations.length===3&&draft.operations[2].action==="add_tie","Image tie draft not queued");
 check(!("geographic" in draft.operations[2].values),"Tie acquired a ground coordinate");
 const p=document.createElement("pre");p.id="browser-check-result";
 p.textContent=JSON.stringify({status:"passed",checks:["original pixels","zoom/scroll coordinates","GIS vertex pick","draft creation","self approval blocked","edit queued","sheet binding","image-only tie"],draft});
 document.body.append(p);
} catch(e) {
 const p=document.createElement("pre");p.id="browser-check-result";p.textContent=JSON.stringify({status:"failed",error:e.stack||String(e)});document.body.append(p);
}
</script>
"""
    page = (bundle / 'REVIEW.html').read_text(encoding='utf-8').replace('</html>', script + '</html>')
    path = bundle / 'browser-smoke.html'; path.write_text(page, encoding='utf-8')
    command = [args.browser, '--headless', '--disable-gpu', '--disable-background-networking', '--disable-sync',
               '--no-first-run', '--allow-file-access-from-files', '--user-data-dir=' + str(bundle / 'browser-profile'),
               '--virtual-time-budget=3000', '--dump-dom', path.as_uri()]
    proc = subprocess.run(command, capture_output=True, timeout=45,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    dom = proc.stdout.decode('utf-8', errors='replace')
    marker = re.search(r'<pre id="browser-check-result">(.*?)</pre>', dom, re.S)
    result = json.loads(html.unescape(marker.group(1))) if marker else {
        'status': 'browser_unavailable', 'returncode': proc.returncode, 'diagnostic': proc.stderr.decode('utf-8', errors='replace')[-2000:]}
    (bundle / 'browser-check-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'draft'}, indent=2))
    if result['status'] == 'passed':
        (bundle / 'browser-decisions.json').write_text(json.dumps(result['draft'], indent=2) + '\n', encoding='utf-8')
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
