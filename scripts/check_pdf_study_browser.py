"""Optional installed-Edge smoke check of an offline classification report.

Simulates an explicitly nonindependent AI review in a separate HTML copy. Never
applies or saves decisions. Uses an isolated workspace profile; installs nothing.
"""

import argparse
import html
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('study')
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser', default=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    args = parser.parse_args()
    study, output = Path(args.study).resolve(), Path(args.output).resolve()
    report = json.loads((study / 'inspection.json').read_text(encoding='utf-8'))
    count = sum(len(d['pages']) for d in report['documents'])
    if not count:
        raise ValueError('A nonempty inspection is required for the browser check')
    output.mkdir(parents=True, exist_ok=False)
    script = r'''
<script>
(async()=>{try{
 const check=(ok,label)=>{if(!ok)throw Error(label);};
 check(document.querySelectorAll('article').length===PAGE_COUNT,'Source page cards');
 document.querySelector('#download').click();
 check(document.querySelector('#message').textContent.includes('required'),'Blank reviewer blocked');
 document.querySelector('#reviewer').value='SYNTHETIC UI smoke check';document.querySelector('#type').value='ai';document.querySelector('#independent').checked=true;
 document.querySelector('#download').click();
 check(document.querySelector('#message').textContent.includes('human'),'AI independent acceptance blocked');
 document.querySelector('#independent').checked=false;
 const first=document.querySelector('article');first.querySelector('.action').value='correct';first.querySelector('.primary').value='indeterminate';first.querySelector('.primary').onchange();
 check(first.querySelector('.label[value="indeterminate"]').checked,'Primary label synchronized');
 first.querySelector('.reason').value='SYNTHETIC nonaccepted UI test only; never applied';
 let captured;URL.createObjectURL=b=>{captured=b;return 'blob:synthetic-test';};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=function(){};
 document.querySelector('#download').click();
 const data=JSON.parse(await captured.text());check(data.decisions.length===PAGE_COUNT,'Page IDs exported');check(data.inspection_sha256===REPORT_HASH,'Inspection hash binding');check(data.reviewer_type==='ai'&&!data.independent,'Nonindependent AI status retained');check(data.decisions[0].action==='correct','Correction exported');
 const p=document.createElement('pre');p.id='browser-check-result';p.textContent=JSON.stringify({status:'passed',checks:['source page cards','blank reviewer blocked','AI independent acceptance blocked','primary label synchronized','hash-bound export','nonaccepted AI status retained'],simulated_decisions_applied:false});document.body.append(p);
}catch(e){const p=document.createElement('pre');p.id='browser-check-result';p.textContent=JSON.stringify({status:'failed',error:e.stack||String(e)});document.body.append(p);}})();
</script>
'''
    import hashlib
    report_hash = hashlib.sha256((study / 'inspection.json').read_bytes()).hexdigest()
    script = script.replace('PAGE_COUNT', str(count)).replace('REPORT_HASH', json.dumps(report_hash))
    page = (study / 'REVIEW.html').read_text(encoding='utf-8')
    page = page.replace('<meta charset=', f'<base href="{html.escape(study.as_uri(), quote=True)}/"><meta charset=', 1)
    path = output / 'browser-smoke.html'
    path.write_text(page.replace('</html>', script + '</html>'), encoding='utf-8')
    command = [args.browser, '--headless', '--disable-gpu', '--disable-background-networking', '--disable-sync',
               '--no-first-run', '--allow-file-access-from-files', '--user-data-dir=' + str(output / 'browser-profile'),
               '--virtual-time-budget=3000', '--window-size=1400,1000', '--screenshot=' + str(output / 'review.png'),
               '--dump-dom', path.as_uri()]
    proc = subprocess.run(command, capture_output=True, timeout=45,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    dom = proc.stdout.decode('utf-8', errors='replace')
    marker = re.search(r'<pre id="browser-check-result">(.*?)</pre>', dom, re.S)
    result = json.loads(html.unescape(marker.group(1))) if marker else {
        'status': 'browser_unavailable', 'returncode': proc.returncode,
        'diagnostic': proc.stderr.decode('utf-8', errors='replace')[-2000:]}
    result.update(study=str(study), inspection_sha256=report_hash)
    (output / 'browser-check-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
