const {chromium}=require('playwright');
const {pathToFileURL}=require('node:url');const path=require('node:path'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage();const results=[];
for(const [width,height] of [[1366,768],[1440,900],[1536,864],[1500,790],[1876,991]]){
await page.setViewportSize({width,height});await page.goto(pathToFileURL(path.join(__dirname,'../开题手记.html')).href);await page.emulateMedia({reducedMotion:'reduce'});
const positions=await page.locator('.split-architecture').evaluate(el=>['student-side','student-bridge','arch-web','teacher-bridge','arch-teacher'].map(cls=>{const r=el.querySelector('.'+cls).getBoundingClientRect();return {left:r.left,right:r.right}}));
assert(positions.every((p,i)=>i===0||p.left>=positions[i-1].right),'MCP bridges sit between the three environments without overlap');
for(let i=0;i<6;i++){
await page.locator(`[data-arch="${i}"]`).click();
await page.locator('.architecture').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));
const box=await page.locator('.architecture').evaluate(el=>{const r=el.getBoundingClientRect(),nav=document.querySelector('.masthead').getBoundingClientRect();return{top:r.top,bottom:r.bottom,height:r.height,navBottom:nav.bottom,screen:innerHeight,stepsAbove:el.querySelector('.arch-timeline').getBoundingClientRect().bottom<el.querySelector('.architecture-grid').getBoundingClientRect().top}});
assert(box.stepsAbove);assert(box.top>=box.navBottom-1);assert(box.bottom<=box.screen,JSON.stringify({width,height,i,...box}));results.push({width,height,step:i+1,diagramHeight:box.height});
}
if(width===1366)await page.screenshot({path:path.join(__dirname,'verification/architecture-pc-fit.png')});
}fs.writeFileSync(path.join(__dirname,'verification/fit-result.json'),JSON.stringify(results,null,2));await browser.close();console.log('All six steps fit five PC viewports');})().catch(e=>{console.error(e);process.exit(1)});
