// Source/build binding, stored outside the public web root in the final image.
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, join, relative } from 'node:path';

const root = process.cwd();
const walk = (folder) => !existsSync(folder) ? [] : readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
  const path = join(folder, entry.name);
  return entry.isDirectory() ? walk(path) : [path];
});
const hash = (path, normalize = false) => {
  const data = readFileSync(path);
  const bytes = normalize && (/\.(tsx?|m?js|css|json|html|lock|yaml|template|conf)$/.test(path) || ['Dockerfile', '.dockerignore'].includes(basename(path)))
    ? Buffer.from(data.toString('utf8').replace(/\r\n/g, '\n')) : data;
  return createHash('sha256').update(bytes).digest('hex');
};
const inputs = ['src', 'public'].flatMap((name) => walk(join(root, name)));
inputs.push(...['package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'index.html',
  'tsconfig.json', 'vite.config.ts', 'nginx.local-product.conf.template', 'Dockerfile',
  '.dockerignore', 'scripts/write-build-manifest.mjs'].map((name) => join(root, name)));
const mapping = (paths, base, normalize) => Object.fromEntries(paths.sort().map((path) => [relative(base, path).replaceAll('\\', '/'), hash(path, normalize)]));
writeFileSync('release-manifest.json', JSON.stringify({ schema: 1, kind: 'web',
  files: mapping(inputs, root, true), artifacts: mapping(walk(join(root, 'dist')), join(root, 'dist'), false),
  build: Object.fromEntries(['VITE_DISCOVERY_PRODUCT', 'VITE_TRAVEL_CONTENT_CONTRACT', 'VITE_ASSISTANT_CONTEXT_CONTRACT'].map((name) => [name, process.env[name] ?? ''])),
}, null, 2));
