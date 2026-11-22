const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const output=path.join(__dirname,'verification');fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(pathToFileURL(path.join(__dirname,'../开题手记.html')).href);
 assert.equal(await page.locator('.chapter').count(),7);
 assert.equal(await page.locator('.nav-links a').count(),7);
 assert.equal(await page.locator('#section-8').count(),0);
 for(const img of await page.locator('.prose img').all()){await img.scrollIntoViewIfNeeded();await img.evaluate(el=>el.decode());assert(await img.evaluate(el=>el.naturalWidth>0));}
 await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
 await page.screenshot({path:path.join(output,'desktop-cover.png')});
 const layouts=[];
 for(const width of [1440,1024,768,390,375,320]){
  await page.setViewportSize({width,height:1000});
  for(const id of ['top','section-3','section-4','section-5','section-6','section-7']){
   await page.locator('#'+id).scrollIntoViewIfNeeded();
   await page.waitForTimeout(120);
   const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
   assert(size.scroll<=size.width,`${id} overflows at ${width}: ${size.scroll}`);
  }
  layouts.push(width);
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.locator('#section-3').scrollIntoViewIfNeeded();
 await page.locator('[data-stage="2"]').click();assert.match(await page.locator('#stage-title').textContent(),/改变了理解/);
 await page.locator('[data-decision="supplement"]').click();assert.match(await page.locator('#branch-note').textContent(),/回到D/);assert.equal(await page.locator('[data-stage="3"]').getAttribute('aria-pressed'),'true');
 await page.locator('[data-decision="redirect"]').click();assert.match(await page.locator('#branch-route').textContent(),/相关阶段/);
 await page.locator('[data-decision="approve"]').click();
 await page.locator('[data-stage="0"]').click();await page.locator('#flow-play').click();
 await page.waitForTimeout(2800);assert.equal(await page.locator('[data-stage="1"]').getAttribute('aria-pressed'),'true');
 await page.locator('#flow-play').click();assert.equal(await page.locator('#flow-play').getAttribute('aria-pressed'),'false');
 await page.locator('.flow-diagram').screenshot({path:path.join(output,'flow-desktop.png')});
 await page.locator('#section-4').scrollIntoViewIfNeeded();await page.locator('[data-arch="2"]').click();assert.match(await page.locator('#arch-description').textContent(),/检查归属/);
 assert.equal(await page.locator('[data-node="store"]').evaluate(el=>el.classList.contains('live')),true);
 await page.locator('[data-arch="0"]').click();await page.locator('#arch-play').click();await page.waitForTimeout(3200);assert.equal(await page.locator('[data-arch="1"]').getAttribute('aria-pressed'),'true');
 await page.locator('#arch-play').click();await page.locator('[data-arch="2"]').click();
 await page.locator('.architecture').screenshot({path:path.join(output,'architecture-desktop.png')});
 await page.locator('.zoom').first().click();assert.equal(await page.locator('#image-dialog').evaluate(el=>el.open),true);await page.keyboard.press('Escape');assert.equal(await page.locator('#image-dialog').evaluate(el=>el.open),false);
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:path.join(output,'mobile-cover.png')});
 await page.locator('.menu-toggle').click();await page.locator('.nav-links a[href="#section-4"]').click();assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'),'false');
 await page.locator('.architecture').screenshot({path:path.join(output,'architecture-mobile.png')});
 await page.locator('.flow-diagram').screenshot({path:path.join(output,'flow-mobile.png')});
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>document.body.classList.contains('motion-off'));assert.equal(await page.locator('body').evaluate(el=>el.classList.contains('motion-off')),true);
 await page.locator('[data-stage="0"]').click();await page.locator('#flow-play').click();assert.equal(await page.locator('[data-stage="1"]').getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('#flow-play').getAttribute('aria-pressed'),'false');
 await page.emulateMedia({media:'print'});await page.pdf({path:path.join(output,'print-check.pdf'),format:'A4',printBackground:true,margin:{top:'12mm',bottom:'12mm',left:'12mm',right:'12mm'}});
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({layouts,consoleErrors:errors,flowBranches:'passed',flowPlayback:'passed',architecturePlayback:'passed',screenshotDialog:'passed',mobileNavigation:'passed',reducedMotion:'passed',print:'rendered'},null,2));
 await browser.close();console.log('Magazine verification passed: '+layouts.join(', '));
})().catch(e=>{console.error(e);process.exit(1)});
