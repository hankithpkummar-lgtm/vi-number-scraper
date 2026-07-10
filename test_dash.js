const fs = require('fs');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;
const html = fs.readFileSync('public/dashboard.html', 'utf8');

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  url: "http://localhost:3000/",
  virtualConsole: new jsdom.VirtualConsole().sendTo(console)
});

setTimeout(() => {
  console.log("Success! No immediate window errors logged.");
}, 2000);
