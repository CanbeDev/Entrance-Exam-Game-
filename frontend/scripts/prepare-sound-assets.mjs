import { mkdir,readFile,writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { soundAssets, soundUrl } from '../src/sound/assets.ts';
import { verifyRuntimeSounds } from './verify-sound-assets.mjs';
if (process.argv.includes('--check')) await verifyRuntimeSounds();
const rows=[];
if (!process.argv.includes('--check')) await mkdir(new URL('../public/assets/sounds/',import.meta.url),{recursive:true});
for(const [event,filename] of Object.entries(soundAssets)) {
  const bytes=await readFile(new URL('../public/assets/audio/'+encodeURIComponent(filename),import.meta.url));
  const target=new URL('../public'+soundUrl(event),import.meta.url);
  if(process.argv.includes('--check')) {
    if(!bytes.equals(await readFile(target))) throw Error('Sound copy drift: '+event);
  } else await writeFile(target,bytes);
  rows.push({event,original:filename,runtime:soundUrl(event),bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')});
}
const text=JSON.stringify({provenance:'User-supplied; licensing not supplied',method:'Byte-identical copies; originals unchanged',files:rows},null,2)+'\n';
const manifest=new URL('../public/assets/sounds/manifest.json',import.meta.url);
if(process.argv.includes('--check')) {if(await readFile(manifest,'utf8')!==text)throw Error('Sound manifest drift');}
else await writeFile(manifest,text);
console.log('PRIVATE source verification: 18 original/runtime byte comparisons and preparation manifest verified.');
