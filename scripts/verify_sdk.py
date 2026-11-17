"""Run the unmodified official Python SDK and validate raw responses against upstream OpenAPI."""
import json
from pathlib import Path
import time
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

root=Path(__file__).resolve().parents[1]
key=next(x.split('=',1)[1] for x in (root/'.env').read_text().splitlines() if x.startswith('API_KEY='))
spec=json.loads((root/'docs/upstream/typesafe-openapi.json').read_text())
registry=Registry().with_resource('urn:typesafe',Resource.from_contents({'$schema':'https://json-schema.org/draft/2020-12/schema',**spec}))
validator=Draft202012Validator({'$ref':'urn:typesafe#/components/schemas/SystemOneResponse'},registry=registry)
start=time.monotonic()
with TypeSafeClient(api_key=key,base_url='http://127.0.0.1:8080',model='jev-latest',timeout=3600,compression='zstd') as client:
    models=client.models.list()
    result=client.system_one(state={'ticket':'Please cancel my order and refund it. Do not ship it.'},questions={
        'intent':Choice(instructions={'task':'Identify the requested action'},criteria={'refund':['Cancel','Refund'],'ship':'Ship the order'}),
        'ship':Noul(instructions='Does the customer want shipment?'),
        'refund':Score(instructions='How explicit is the refund request?',criteria=['absent','uncertain',{'meaning':'explicit'}])})
    raw=result.raw_http_response.json()
    validator.validate(raw)
    assert result.choices['intent'].choice=='refund'
    assert result.nouls['ship'].noul<.5
    assert result.scores['refund'].score>1
    output={'sdk':'typesafe-sdk 0.7.5','compression':'zstd','schema_valid':True,'elapsed_seconds':time.monotonic()-start,
            'response':raw,'model_count':len(models.models)}
    (root/'artifacts/python-sdk.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output),flush=True)
