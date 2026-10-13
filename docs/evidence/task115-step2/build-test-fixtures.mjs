// Pure disposable TEST fixture preparation. Does not seed protected journals,
// publish authority/results, call Writer, run models or change native records.
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
const [sourceRoot,inputPath,outputPath]=process.argv.slice(2);
if(!sourceRoot||!inputPath||!outputPath)throw Error('usage: node builder.mjs SOURCE_ROOT public-observations.json OUTPUT_DIR');
const imported=await import(pathToFileURL(join(resolve(sourceRoot),'contracts/src/github-authority.mjs')));
const {resolveTaskAuthority,createAdmissionSnapshot,admissionBinding,canonicalAuthorityJson,sha256Body,validateAuthorityRecord}=imported;
const {CONSUMER,CONSUMER_DIGEST}=await import(pathToFileURL(join(resolve(sourceRoot),'consumer/consumer.mjs')));
const {VERSION,validateEnvelope,NATIVE_VALIDATIONS}=await import(pathToFileURL(join(resolve(sourceRoot),'controller/src/execution-contract.mjs')));
const {projectedRequestTitle}=await import(pathToFileURL(join(resolve(sourceRoot),'controller/src/step-metadata.mjs')));
if(CONSUMER.repository!=='jresearchsoftware/codex-relay-testbed'||CONSUMER.paths.claimRoot!=='/var/lib/codex-relay-test/writer-claims'||CONSUMER.paths.writerHelper!=='/opt/codex-relay-test/relay-writer-controller')throw Error('NOT_ISOLATED_TEST_CONSUMER');
const input=JSON.parse(await readFile(inputPath,'utf8'));const {issue,pr,reviewer,sourceRevision}=input;
if(issue.number!==6||issue.id!==5805525646||issue.state!=='open'||issue.user.login!=='foal'||issue.labels.some(x=>x.name.startsWith('codex-ready-'))||pr.number!==7||pr.state!=='open'||pr.merged||!pr.draft||pr.head.ref!=='codex/task-115-manual-outcome-fixture'||pr.head.repo.full_name!==CONSUMER.repository||pr.base.repo.full_name!==CONSUMER.repository||reviewer.login!=='jresearch-relay-test-reviewer[bot]'||reviewer.type!=='Bot'||!Number.isSafeInteger(reviewer.id)||!/^[a-f0-9]{40}$/.test(sourceRevision))throw Error('FIXTURE_IDENTITY_CHANGED');
const parent={kind:'issue',number:6};
const native=(v,kind,parent)=>({kind,id:v.id,repository:CONSUMER.repository,parent,author:v.user,body:v.body??'',state:v.state,commit_id:v.commit_id});
const records=[native(issue,'issue-body',parent),...(input.comments??[]).filter(x=>/^```relay-authority/m.test(x.body??'')).map(x=>native(x,'issue-comment',parent))];
const binding={repository:CONSUMER.repository,task:6,charterId:issue.id,charterBody:issue.body,trustedAuthor:reviewer,compatibility:false,route:'manual',purpose:issue.title.replace(/^Task\s+#?\d+\s*[-–—:·|]+\s*/i,''),projectDefaults:{model:CONSUMER.defaultProfile.cliModelId,effort:CONSUMER.defaultProfile.effort,subagents:true,validation:[...NATIVE_VALIDATIONS]},startingState:{branch:null,base_sha:null,starting_head:null,existing_pr:null}};
const resolved=resolveTaskAuthority(records,binding);
const cases=[];
for(const [name,runId]of [['no_pr',9007115000401],['pr',9007115000402]]){
const linked=name==='pr';const attempt=`run-${runId}`;
const state=linked?{branch:pr.head.ref,base_sha:pr.base.sha,starting_head:pr.head.sha,existing_pr:7}:{branch:null,base_sha:null,starting_head:null,existing_pr:null};
const caseResolved=resolveTaskAuthority(records,{...binding,startingState:state});
const snapshot=createAdmissionSnapshot(caseResolved,{step:1,route:'manual',attempt,runId,lineage:null});
const envelope={version:VERSION,repository:CONSUMER.repository,consumerDigest:CONSUMER_DIGEST,runId,attemptId:attempt,target:'issue',number:6,issueNumber:6,route:'manual',step:1,branch:snapshot.branch,startHead:snapshot.starting_head,historicalBase:snapshot.base_sha,targetBase:input.mainHead??pr.base.sha,reviewId:null,authorityDigest:snapshot.authority.sha256,profile:{cliModelId:snapshot.model,effort:snapshot.effort},subagentsAllowed:snapshot.subagents,validation:snapshot.validation,thread:`Task 6 — Step 1 — ${snapshot.purpose}`,title:`Task 6 · Step 1 · ${snapshot.purpose}`,closure:'Related to #6',request:snapshot,requestReference:snapshot.authority.charter,...(linked?{continuation:{head:pr.head.sha,pullRequest:7}}:{})};
validateEnvelope(envelope);
const result={schema_version:'4.0',kind:'outcome',repository:CONSUMER.repository,task:6,parent:linked?{kind:'pull_request',number:7}:parent,charter_sha256:snapshot.charter_sha256,step:1,authority:snapshot.authority,admission:admissionBinding(snapshot),attempt,status:'implemented',result:{kind:linked?'git':'qualification',revision:linked?pr.head.sha:sourceRevision,identities:[{kind:'qualification-fixture',id:`task115-step2-installed-f1-${name}`} ]},summary:'Official TEST App F1 publication fixture after a trusted Task Decision changed current requirements. Protected admission-shaped state is synthetic; no real admission, Relay/model execution, new project Task or Step is asserted.',warnings:[],limitations:['Synthetic admission-shaped state qualifies installed publication, not real Writer admission or worker/model execution.','Product Task115 Step1/Step2 PROD admissions and original PR118 execution markers are untouched.','No independent product acceptance, product merge, PROD installation or Issue closure is asserted.']};
validateAuthorityRecord(result,{repository:CONSUMER.repository,task:6,charterBody:issue.body});
const claim={envelope,...(linked?{prNumber:7}:{}),qualificationFixture:{synthetic:true,realExecution:false,source:sourceRevision,ownerRequest:'PR118 review5487214267',channel:'official-test-app-step2-f1'}};
const submission={repository:CONSUMER.repository,task:6,run_id:runId,result};cases.push({name,runId,claim,submission});
}
const predecessor=resolved.authority.decisions.at(-1)??null;
const decision={schema_version:'4.0',kind:'decision',repository:CONSUMER.repository,task:6,parent,charter_sha256:sha256Body(issue.body),purpose:'Qualify immutable manual Outcome publication after trusted Task requirement drift',amendments:{scope:['Verify that the installed TEST Writer honestly reports one immutable-admission-bound synthetic result after this trusted Task requirement amendment, with current-authority drift visible for independent review.']},supersedes:predecessor,context:[]};
validateAuthorityRecord(decision,{repository:CONSUMER.repository,task:6,charterBody:issue.body});
await mkdir(outputPath,{recursive:true,mode:0o700});
for(const item of cases){await writeFile(join(outputPath,`${item.runId}.claim.json`),JSON.stringify(item.claim,null,2)+'\n',{mode:0o600});await writeFile(join(outputPath,`${item.name}.submission.json`),JSON.stringify(item.submission,null,2)+'\n',{mode:0o600});}
await writeFile(join(outputPath,'decision.json'),JSON.stringify({repository:CONSUMER.repository,record:decision},null,2)+'\n',{mode:0o600});
await writeFile(join(outputPath,'pr-marker.txt'),`Execution admission digest: ${cases.find(x=>x.name==='pr').submission.result.admission.sha256}\n`,{mode:0o600});
const manualPr=cases.find(x=>x.name==='pr');await writeFile(join(outputPath,'manual-pr-setup.json'),JSON.stringify({issue:6,pr:7,labels:['step-1'],title:projectedRequestTitle(manualPr.claim.envelope.request),body:pr.body.replace(/^Execution admission digest: [a-f0-9]{64}$/m,'Execution admission digest: '+manualPr.submission.result.admission.sha256)},null,2)+'\n',{mode:0o600});
// Automatic completion contract fixtures. All execution, collection and prior
// publication fields below are synthetic expected-state inputs, not proof of a
// real child/process, trusted import, Git push or Actions run.
for(const [name,runId]of [['auto_nochange',9007115000403],['auto_finish',9007115000404]]){
const linked=name==='auto_finish';const attempt=`run-${runId}`;
const state={branch:linked?pr.head.ref:'codex/task-115-step2-auto-nochange-fixture',base_sha:linked?pr.base.sha:input.mainHead,starting_head:linked?pr.head.sha:input.mainHead,existing_pr:linked?7:null};
const caseResolved=resolveTaskAuthority(records,{...binding,route:'auto',startingState:state});
const snapshot=createAdmissionSnapshot(caseResolved,{step:1,route:'auto',attempt,runId,lineage:null});
const envelope={version:VERSION,repository:CONSUMER.repository,consumerDigest:CONSUMER_DIGEST,runId,attemptId:attempt,target:'issue',number:6,issueNumber:6,route:'auto',step:1,branch:snapshot.branch,startHead:snapshot.starting_head,historicalBase:snapshot.base_sha,targetBase:input.mainHead,reviewId:null,authorityDigest:snapshot.authority.sha256,profile:{cliModelId:snapshot.model,effort:snapshot.effort},subagentsAllowed:snapshot.subagents,validation:snapshot.validation,thread:`Task 6 — Step 1 — ${snapshot.purpose}`,title:`Task 6 · Step 1 · ${snapshot.purpose}`,closure:'Related to #6',request:snapshot,requestReference:snapshot.authority.charter,...(linked?{continuation:{head:pr.head.sha,pullRequest:7}}:{})};
validateEnvelope(envelope);
const fixture={synthetic:true,realExecution:false,source:sourceRevision,ownerRequest:'PR118 review5487214267',channel:`installed-test-writer-step2-f1-${name}`,limitations:'Admission, contained execution, clean collection and prior publication fields are synthetic fixtures; no model/process/Git import/push/Actions run was executed.'};
const taskResult={summary:'Synthetic TEST automatic-completion contract fixture after trusted Task drift. Admission, successful contained execution, clean collection and prior publication metadata are explicitly seeded expected-state inputs. No actual worker/model, ready/dispatch, Git push or real Actions run is asserted.',validation:['Fixture validates installed automatic Writer publication only; real admission, worker execution, trusted Git collection and native CI are not qualified.']};
const claim={envelope,qualificationFixture:fixture,publicationIntent:null,publishedHead:linked?pr.head.sha:null,finalHead:null,outcome:null,...(linked?{prNumber:7}:{}),controllerLifecycle:{version:1,status:'complete',child:'started',containment:'reaped'}};
const journal={version:VERSION,envelope,qualificationFixture:fixture,execution:{reserved:true,returned:true,child:'started',containment:'reaped',result:{status:'success',...taskResult}},collection:{head:envelope.startHead,clean:true},progress:linked?{head:pr.head.sha,prNumber:7,clean:true}:null,outcome:null,diagnostic:null};
const request={operation:linked?'finish':'finish-no-change',runId,attemptId:attempt,head:envelope.startHead,taskResult,...(linked?{executionWarnings:[]}:{} )};
await writeFile(join(outputPath,`${runId}.claim.json`),JSON.stringify(claim,null,2)+'\n',{mode:0o600});
await writeFile(join(outputPath,`${runId}.journal.json`),JSON.stringify(journal,null,2)+'\n',{mode:0o600});
await writeFile(join(outputPath,`${name}.request.json`),JSON.stringify(request,null,2)+'\n',{mode:0o600});
if(linked)await writeFile(join(outputPath,'auto-pr-marker.txt'),`Execution admission digest: ${admissionBinding(snapshot).sha256}\n`,{mode:0o600});
if(linked)await writeFile(join(outputPath,'auto-pr-setup.json'),JSON.stringify({issue:6,pr:7,labels:['step-1'],title:projectedRequestTitle(envelope.request),body:pr.body.replace(/^Execution admission digest: [a-f0-9]{64}$/m,'Execution admission digest: '+admissionBinding(snapshot).sha256)},null,2)+'\n',{mode:0o600});
}
console.log(JSON.stringify({preparedOnly:true,repository:CONSUMER.repository,outputPath,installedSourceRequested:sourceRevision,originalAuthority:resolved.authority,syntheticRuns:cases.map(x=>({name:x.name,runId:x.runId,admission:x.submission.result.admission})),decision:decision.purpose},null,2));
