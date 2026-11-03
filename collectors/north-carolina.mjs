import { parseNorthCarolina, sourceUrl } from "../frontend/north-carolina.mjs";

import { execFile } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';

const exec = promisify(execFile);
export async function collectNorthCarolina() {
  const response = await fetch(sourceUrl, { redirect: 'error', signal: AbortSignal.timeout(30_000) });
  if (!response.ok) throw new Error(`North Carolina archive returned HTTP ${response.status}`);
  const archive = await response.arrayBuffer();
  if (archive.byteLength > 16 * 1024 * 1024) throw new Error('North Carolina archive exceeds size limit');
  const directory = await mkdtemp(join(tmpdir(), 'senate-nc-'));
  try {
    const zip = join(directory, 'results.zip');
    await writeFile(zip, Buffer.from(archive));
    const { stdout } = await exec('unzip', ['-p', zip, 'results_pct_20261103.txt'], {
      encoding: 'buffer', maxBuffer: 64 * 1024 * 1024, timeout: 15_000,
    });
    // NCSBE exports have included both UTF-8 and Windows-1252 text.
    let tsv;
    try {
      tsv = new TextDecoder('utf-8', { fatal: true }).decode(stdout);
    } catch {
      tsv = new TextDecoder('windows-1252').decode(stdout);
    }
    return { ...parseNorthCarolina(tsv), sourceUrl };
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
