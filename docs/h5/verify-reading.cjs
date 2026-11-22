const {chromium}=require('playwright');
const {pathToFileURL}=require('node:url');const path=require('node:path'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
const browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});
await page.goto(pathToFileURL(path.join(__dirname,'../开题手记.html')).href);
const sizes=await page.evaluate(()=>Object.fromEntries(['.prose>p','.stage small','.arch-node p','.nav-links a'].map(s=>[s,getComputedStyle(document.querySelector(s)).fontSize])));
assert.equal(sizes['.prose>p'],'20px');assert(parseFloat(sizes['.stage small'])>=14);assert(parseFloat(sizes['.arch-node p'])>=16);
const sides=await page.locator('[data-node="student-codex"], [data-node="website"], [data-node="teacher-codex"]').evaluateAll(nodes=>nodes.map(node=>node.getBoundingClientRect().x));
assert(sides[0]<sides[1]&&sides[1]<sides[2],'student left, website center, teacher right');
await page.locator('[data-arch="4"]').click();
assert.equal(await page.locator('[data-node="teacher-codex"]').evaluate(el=>el.classList.contains('live')),true);
assert.equal(await page.locator('[data-node="student-codex"]').evaluate(el=>el.classList.contains('live')),false);
assert.equal(await page.locator('[data-node="teacher-mcp"]').evaluate(el=>el.classList.contains('live')),true);
await page.locator('[data-arch="2"]').click();
assert.equal(await page.locator('[data-node="student-codex"]').evaluate(el=>el.classList.contains('live')),true);
assert.equal(await page.locator('[data-node="teacher-codex"]').evaluate(el=>el.classList.contains('live')),false);
for(const selector of ['.stage.active','.arch-node.live']){
 await page.locator(selector).first().scrollIntoViewIfNeeded();await page.waitForTimeout(300);
 const before=await page.locator(selector).first().evaluate(el=>({animation:getComputedStyle(el,'::before').animationName,opacity:getComputedStyle(el,'::before').opacity}));
 assert.equal(before.animation,'node-breathe');await page.waitForTimeout(700);
 const after=await page.locator(selector).first().evaluate(el=>getComputedStyle(el,'::before').opacity);assert(Math.abs(Number(before.opacity)-Number(after))>.02,'breathing opacity changes');
}
await page.locator('.motion-toggle').click();
assert.equal(await page.locator('.arch-node.live').first().evaluate(el=>getComputedStyle(el,'::before').animationName),'none');
await page.locator('.motion-toggle').click();await page.emulateMedia({reducedMotion:'reduce'});
assert.equal(await page.locator('.stage.active').evaluate(el=>getComputedStyle(el,'::before').animationName),'none');
await page.addStyleTag({content:'.masthead,.progress,.skip{visibility:hidden!important}html{scroll-behavior:auto!important}'});
await page.locator('.architecture').screenshot({path:path.join(__dirname,'verification/architecture-desktop.png')});
await page.locator('#section-1').screenshot({path:path.join(__dirname,'verification/reading-desktop.png')});
await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('.prose>p').first().evaluate(el=>getComputedStyle(el).fontSize),'18px');
await page.locator('.flow-diagram').screenshot({path:path.join(__dirname,'verification/flow-mobile.png')});
await page.locator('.architecture').screenshot({path:path.join(__dirname,'verification/architecture-mobile.png')});
fs.writeFileSync(path.join(__dirname,'verification/reading-result.json'),JSON.stringify({sizes,breathing:'opacity changes on both diagrams',motionOff:'passed',reducedMotion:'passed',mobileBody:'18px'},null,2));await browser.close();console.log('Reading sizes and node breathing verified');
})().catch(e=>{console.error(e);process.exit(1)});
