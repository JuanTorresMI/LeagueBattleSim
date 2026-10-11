// Browser check of kalista_spikes.html: no script errors, no horizontal scroll at desktop
// and phone width, and the build editor loads Pyodide and fills its tables.
//   PLAYWRIGHT=/path/to/node_modules/playwright node tools/check_page.js [page.html]
// Needs network access to cdn.jsdelivr.net; writes editor.png and phone.png to the current folder.
const { chromium } = require(process.env.PLAYWRIGHT || "playwright");
(async () => {
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined;
  const browser = await chromium.launch({ proxy, args: ["--ignore-certificate-errors"] });
  const results = {};
  for (const [name, vp] of [["desktop", {width: 1100, height: 900}], ["phone", {width: 390, height: 844}]]) {
    const page = await browser.newPage({ viewport: vp, ignoreHTTPSErrors: true });
    const errors = [];
    page.on("pageerror", e => errors.push(String(e)));
    page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto("file://" + require("path").resolve(process.argv[2] || require("path").join(__dirname, "..", "kalista_spikes.html")));
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (name === "desktop") {
      await page.click("#edstart");
      await page.waitForSelector("#edform:not([hidden])", { timeout: 180000 });
      await page.waitForFunction(() => document.querySelector("#edfights tbody tr"), null, { timeout: 60000 });
      results.fights = await page.$$eval("#edfights tbody tr", rs => rs.map(r => r.innerText.replace(/\s+/g, " ")));
      results.lane = await page.$$eval("#edlane tbody tr", rs => rs.map(r => r.innerText.replace(/\s+/g, " ")));
      results.preset = await page.$eval("#edpreset", s => s.options[s.selectedIndex].text);
      await page.selectOption('#eitems select[data-slot="6"]', "3036");
      await page.waitForTimeout(800);
      results.warn = await page.$eval("#edwarn", e => e.hidden ? "" : e.textContent);
      await page.locator("#editor").screenshot({ path: "editor.png" });
    } else {
      await page.screenshot({ path: "phone.png", fullPage: false });
    }
    results[name] = { overflow, errors };
  }
  console.log(JSON.stringify(results, null, 1));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
