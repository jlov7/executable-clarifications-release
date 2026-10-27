"""Generate bounded browser sessions from the SAME Python question/export logic.

Run from the repository after installing the package. No model calls or external data.
"""
import argparse
import hashlib
import json
from pathlib import Path

from executable_clarifications.core import Candidate, default_boundary_domain
from executable_clarifications.session import (
    Session,
    assumptions,
    contract_template,
    render_contract,
)


def build_cases():
    cases=[]
    definitions=[
        ('orders','Include orders within the selected age window.', 'days',20,30,'<=','<'),
        ('batch','Accept a batch at or above the minimum quantity.', 'quantity',10,20,'>=','>'),
        ('response','Flag a response inside the selected hour window.', 'hours',24,48,'<=','<')]
    for name,title,field,a,b,op1,op2 in definitions:
        candidates=[Candidate(f'c{i}',field,op,t) for i,(op,t) in enumerate(
            [(op1,a),(op2,a),(op1,b),(op2,b)])]
        root=Session(candidates,default_boundary_domain(candidates))
        nodes={}
        def visit(session, node_id, nodes=nodes):
            q=session.question()
            record=session.export_record()
            contract=(render_contract(session,'implementation:decide')
                      if session.status!='UNRESOLVED' and session.examples() else None)
            node={'record':record,'question':q,'status':session.status,
                  'remaining':session.remaining_ids,'contract':contract,
                  'assumptions':assumptions(session),'branches':{}}
            nodes[node_id]=node
            if q is not None:
                for key,answer in [('true',True),('false',False),('neither',None)]:
                    child=Session.from_record(record)
                    child.answer(q['id'],answer)
                    next_id=node_id+'-'+key
                    node['branches'][key]=next_id
                    visit(child,next_id)
        visit(root,'root')
        cases.append({'id':name,'title':title,'field':field,'nodes':nodes})
    return cases


def render_data():
    data=json.dumps(build_cases(),ensure_ascii=True,separators=(',',':'),sort_keys=True)
    # Even future descriptive text cannot terminate a script element.
    data=data.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return ('"use strict";\nwindow.CLARIFICATION_CASES = '+data+';\n' +
            'window.CLARIFICATION_CONTRACT_TEMPLATE = ' + json.dumps(contract_template()) + ';\n' +
            'window.CLARIFICATION_EXAMPLE_SET = ' + json.dumps(json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/known_examples.json').read_text()),separators=(',',':'),sort_keys=True) + ';\n')


def verify_assets():
    web = Path(__file__).resolve().parents[1] / 'web'
    rendered = render_data()
    if ((web / 'session-data.js').read_text() != rendered or
            (web / 'session-data.sha256').read_text().strip() !=
            hashlib.sha256(rendered.encode()).hexdigest()):
        raise ValueError('browser data or digest is stale; run scripts/build_session_demo.py')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        verify_assets()
    else:
        web = Path(__file__).resolve().parents[1] / 'web'
        rendered = render_data()
        (web / 'session-data.js').write_text(rendered)
        (web / 'session-data.sha256').write_text(hashlib.sha256(rendered.encode()).hexdigest() + '\n')
