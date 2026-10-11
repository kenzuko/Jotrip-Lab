'use strict';
const path=require('path'),fs=require('fs');
const esbuild=require('C:/Users/Public/OpenPQ/living-kyoto-reference-proof-20261010/kyoto-higashiyama/node_modules/esbuild');
esbuild.buildSync({entryPoints:[path.join(__dirname,'main.js')],outfile:path.join(__dirname,'app.js'),
 bundle:true,minify:true,legalComments:'inline',format:'esm',platform:'browser',target:'es2022',
 nodePaths:['C:/Users/Public/OpenPQ/living-r07-splat-proof-20261010/node_modules'],
 alias:{'node:worker_threads':'C:/Users/Public/OpenPQ/living-r07-splat-proof-20261010/worker-threads-stub.cjs'}});
console.log('R20_MINIFIED_ISOLATED_BUILD_OK',fs.statSync(path.join(__dirname,'app.js')).size);