import { readdir,readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { soundAssets } from '../src/sound/assets.ts';
const directory=new URL('../public/assets/audio/',import.meta.url);
let decoded=[];
try {decoded=JSON.parse(await readFile(new URL('../../output/ui-stage8-5/audio-metadata.json',import.meta.url),'utf8'));} catch { /* Duration stays unknown until the isolated browser decodes it. */ }
const files=[];
for(const filename of (await readdir(directory)).sort()) {
  const bytes=await readFile(new URL(encodeURIComponent(filename),directory));
  const metadata=decoded.find(m=>m.filename===filename);
  files.push({filename,format:filename.endsWith('.mp3')?'MP3':'unknown',bytes:bytes.length,
    duration:metadata?.duration??null,decoded:metadata?.decoded??false,playable:metadata?.playable??false,
    events:Object.entries(soundAssets).filter(([,name])=>name===filename).map(([event])=>event),
    sha256:createHash('sha256').update(bytes).digest('hex'),provenance:'User-supplied; licence not supplied',
    portability:filename.includes('#')?'Original hash character; use byte-identical portable runtime copy':'No hash character'});
}
console.log(JSON.stringify({files,exactDuplicates:files.filter((f,i)=>files.findIndex(g=>g.sha256===f.sha256)<i).map(f=>f.filename)},null,2));
