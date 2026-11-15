"""R5 immutable input snapshot and append-only output for CFB census research.
No structural check can authenticate independent source provenance.
"""
import argparse,csv,hashlib,io,json,os,sys
from pathlib import Path
from sportsedge_cfb_event_completeness_r3 import audit
KEYS=('primary','control','census','team_map','metadata')

def run(paths):
    raw={}; hashes={}
    try:
        for k in KEYS:
            raw[k]=paths[k].read_bytes()  # exactly one read per input
            hashes[k]=hashlib.sha256(raw[k]).hexdigest()
        data={k:json.loads(raw[k].decode('utf-8-sig')) for k in KEYS if k!='team_map'}
        rows=list(csv.DictReader(io.StringIO(raw['team_map'].decode('utf-8-sig'),newline='')))
        result=audit(data['primary'],data['control'],data['census'],rows,data['metadata'])
        if result['status']=='STRUCTURAL_PASS_SOURCE_AUTH_PENDING':
            result['release_status']='PAPER_0U'
            result['source_admitted']=False
    except (OSError,ValueError,KeyError,IndexError,TypeError,UnicodeError) as exc:
        result={'status':'QUARANTINE','reason':f'{type(exc).__name__}:{exc}','release_status':'PAPER_0U','source_admitted':False}
    result['sha256']=hashes
    result['validator']='sportsedge_cfb_event_completeness_r5'
    result['source_admitted']=False
    result['release_status']='PAPER_0U'
    return result

def main(argv=None):
    p=argparse.ArgumentParser()
    for k in KEYS:p.add_argument(k,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args(argv)
    result=run({k:getattr(a,k) for k in KEYS})
    payload=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode()
    try:
        # O_EXCL: never overwrite prior audit output; no partial JSON accepted.
        fd=os.open(a.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
    except OSError as e:
        print(f'QUARANTINE: output not created: {e}',file=sys.stderr)
        return 5
    return 4
if __name__=='__main__':sys.exit(main())
