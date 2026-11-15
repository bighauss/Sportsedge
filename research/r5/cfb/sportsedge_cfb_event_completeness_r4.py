"""CFB census R4 CLI: fail-closed entry point for R3 structural validator.
No authentication claim: successful structural checks return exit 4 until independently admitted.
"""
import argparse,csv,hashlib,json,sys
from pathlib import Path
from sportsedge_cfb_event_completeness_r3 import audit

def run(paths):
    hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()}
    try:
        data={k:json.loads(v.read_text(encoding='utf-8-sig')) for k,v in paths.items() if k!='team_map'}
        with paths['team_map'].open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        result=audit(data['primary'],data['control'],data['census'],rows,data['metadata'])
        if result['status']=='STRUCTURAL_PASS_SOURCE_AUTH_PENDING':
            result['release_status']='PAPER_0U'; result['source_admitted']=False
    except (ValueError,KeyError,IndexError,TypeError,UnicodeError,json.JSONDecodeError) as e:
        result={'status':'QUARANTINE','reason':f'{type(e).__name__}:{e}','release_status':'PAPER_0U','source_admitted':False}
    result['sha256']=hashes
    return result

def main(argv=None):
    p=argparse.ArgumentParser()
    for k in ('primary','control','census','team_map','metadata'):p.add_argument(k,type=Path)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args(argv)
    paths={k:getattr(args,k) for k in ('primary','control','census','team_map','metadata')}
    try: result=run(paths)
    except (OSError,UnicodeError) as e: result={'status':'QUARANTINE','reason':f'io:{e}','release_status':'PAPER_0U','source_admitted':False}
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return 4 # never promote source from structural checks
if __name__=='__main__':sys.exit(main())
