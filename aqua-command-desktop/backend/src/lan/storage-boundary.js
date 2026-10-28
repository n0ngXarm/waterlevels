import fs from 'node:fs';import path from 'node:path';
/** Fail closed on aliases in owned writable storage; never traverse a link target. */
export function assertOwnedStorage(root){
 root=path.resolve(root);let current=path.parse(root).root;
 for(const part of root.slice(current.length).split(path.sep).filter(Boolean)){current=path.join(current,part);try{if(fs.lstatSync(current).isSymbolicLink())throw Error('Writable storage symlink/alias forbidden')}catch(e){if(e.code==='ENOENT')break;throw e}}
 let visited=0;const inspect=p=>{if(++visited>10000)throw Error('Owned storage inventory limit reached');let stat;try{stat=fs.lstatSync(p)}catch(e){if(e.code==='ENOENT')return;throw e}if(stat.isSymbolicLink())throw Error('Writable storage symlink/alias forbidden');if(stat.isFile()&&stat.nlink>1)throw Error('Writable storage hardlink forbidden');if(stat.isDirectory())for(const name of fs.readdirSync(p))inspect(path.join(p,name))};inspect(root);
}
