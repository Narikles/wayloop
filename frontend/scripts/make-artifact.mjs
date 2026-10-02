// Transforme dist-demo/index.html (build « demo ») en page publiable comme artifact :
// sans doctype/html/head/body (ajoutés à la publication), titre et styles en tête.
import { readFileSync, writeFileSync } from "node:fs";

const src = readFileSync(new URL("../dist-demo/index.html", import.meta.url), "utf8");
const scriptStart = src.indexOf('<script type="module" crossorigin>');
const styleStart = src.indexOf("<style", scriptStart);
const scriptEnd = src.lastIndexOf("</script>", styleStart);
const styleEnd = src.indexOf("</style>", styleStart);
if (scriptStart < 0 || styleStart < 0 || scriptEnd < 0 || styleEnd < 0) throw new Error("structure inattendue");
const script = src.slice(scriptStart + '<script type="module" crossorigin>'.length, scriptEnd);
const style = src.slice(src.indexOf(">", styleStart) + 1, styleEnd);
const out = `<title>Démo WayLoop</title>
<meta name="description" content="Démo hors ligne de WayLoop, le logiciel de recrutement pour TPE et PME">
<script>try { document.documentElement.dataset.theme = localStorage.getItem("wayloop.theme") === "dark" ? "dark" : "light"; } catch (e) { document.documentElement.dataset.theme = "light"; }</script>
<style>${style}</style>
<div id="root"></div>
<script type="module">${script}</script>
`;
writeFileSync(new URL("../dist-demo/artifact.html", import.meta.url), out);
console.log(`artifact.html : ${(out.length / 1024).toFixed(0)} Ko`);
