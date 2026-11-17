import {readFileSync, writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
const require = createRequire(new URL('../tests/sdk-js/package.json', import.meta.url));
const current = require('@typesafe-ai/sdk');
const old = require('typesafe-sdk-old');
const key=readFileSync(new URL('../.env', import.meta.url),'utf8').split('\n').find(l=>l.startsWith('API_KEY=')).slice(8);
const outputs=[];
for(const [version,sdk] of [['0.7.0',current],['0.5.7',old]]) {
 const client=new sdk.TypeSafeClient({apiKey:key,baseURL:'http://127.0.0.1:8080',timeout:3600000,compression:'zstd'});
 const models=await client.models.list();
 const start=performance.now();
 const result=await client.systemOne({state:{ticket:'Cancel and refund my order. Do not ship it.'},questions:{
  intent:{type:'choice',instructions:'What action is requested?',criteria:{refund:'Refund',ship:'Ship'}},
  ship:{type:'noul',instructions:'Does the customer want shipment?'},
  refund:{type:'score',instructions:'How clear is the refund request?',criteria:['absent','uncertain','explicit']}
 }});
 if(result.answers.intent.choice!=='refund'||result.answers.ship.noul>=.5||result.answers.refund.score<=1) throw new Error(JSON.stringify(result));
 outputs.push({sdk:'@typesafe-ai/sdk '+version,compression:'zstd',elapsed_seconds:(performance.now()-start)/1000,result,models});
}
writeFileSync(new URL('../artifacts/javascript-sdk.json', import.meta.url),JSON.stringify(outputs,null,2)+'\n');
console.log(JSON.stringify(outputs));
