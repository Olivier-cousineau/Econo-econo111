import { spawn } from 'node:child_process';
import process from 'node:process';
import { resolve } from 'node:path';

import { sendJson, methodNotAllowed } from '../../lib/http.js';

const OUTPUT_LINE_LIMIT = 20;
const OUTPUT_CHAR_LIMIT = 20_000;

function resolveScraperCommand() {
  const override = process.env.ADMIN_SCRAPER_COMMAND?.trim();
  if (override) {
    return { command: override, args: [], shell: true };
  }

  const pythonBinary =
    process.env.ADMIN_SCRAPER_PYTHON ||
    process.env.PYTHON ||
    process.env.PYTHON_EXECUTABLE ||
    'python3';

  return {
    command: pythonBinary,
    args: [resolve(process.cwd(), 'scraper.py')],
    shell: false,
  };
}

function appendWithLimit(buffer, chunk, limit = OUTPUT_CHAR_LIMIT) {
  const next = `${buffer || ''}${chunk ? chunk.toString() : ''}`;
  if (next.length <= limit) {
    return next;
  }
  return next.slice(next.length - limit);
}

function tailLines(stdout, stderr, limit = OUTPUT_LINE_LIMIT) {
  const combined = `${stdout || ''}${stdout && stderr ? '\n' : ''}${stderr || ''}`.trim();
  if (!combined) {
    return [];
  }
  const lines = combined.split(/\r?\n/);
  return lines.length > limit ? lines.slice(-limit) : lines;
}

async function executeScraper() {
  const { command, args, shell } = resolveScraperCommand();
  const start = Date.now();
  const rawBufferLimit = Number.parseInt(process.env.ADMIN_SCRAPER_OUTPUT_LIMIT || '', 10);
  const bufferLimit =
    Number.isFinite(rawBufferLimit) && rawBufferLimit > 0 ? rawBufferLimit : OUTPUT_CHAR_LIMIT;
  const rawTimeout = Number.parseFloat(process.env.ADMIN_SCRAPER_TIMEOUT || '');
  const timeoutMs = Number.isFinite(rawTimeout) && rawTimeout > 0 ? rawTimeout * 1000 : null;

  return await new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      shell,
      env: process.env,
    });

    let stdout = '';
    let stderr = '';
    let settled = false;
    let timeoutId = null;

    const finish = (error, result) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      if (error) {
        rejectPromise(error);
      } else {
        resolvePromise(result);
      }
    };

    child.stdout?.on('data', (chunk) => {
      stdout = appendWithLimit(stdout, chunk, bufferLimit);
    });

    child.stderr?.on('data', (chunk) => {
      stderr = appendWithLimit(stderr, chunk, bufferLimit);
    });

    child.on('error', (error) => {
      error.stdout = stdout;
      error.stderr = stderr;
      error.durationSeconds = (Date.now() - start) / 1000;
      finish(error);
    });

    child.on('close', (code, signal) => {
      const durationSeconds = (Date.now() - start) / 1000;
      if (code === 0) {
        finish(null, { stdout, stderr, durationSeconds });
        return;
      }
      const error = new Error(
        signal ? `Scraper terminated with signal ${signal}` : `Scraper exited with code ${code}`,
      );
      error.code = code;
      error.signal = signal;
      error.stdout = stdout;
      error.stderr = stderr;
      error.durationSeconds = durationSeconds;
      finish(error);
    });

    if (timeoutMs) {
      timeoutId = setTimeout(() => {
        const error = new Error('Le temps limite configuré pour le scraper est dépassé.');
        error.code = 'ETIMEDOUT';
        error.stdout = stdout;
        error.stderr = stderr;
        error.durationSeconds = (Date.now() - start) / 1000;
        child.kill('SIGTERM');
        finish(error);
      }, timeoutMs);
    }
  });
}

export default async function handler(req, res) {
  if (req?.method && req.method !== 'POST') {
    return methodNotAllowed(res, 'POST');
  }

  try {
    const result = await executeScraper();
    const payload = {
      status: 'ok',
      message: `Scraper terminé en ${result.durationSeconds.toFixed(1)} secondes.`,
      durationSeconds: result.durationSeconds,
      output: tailLines(result.stdout, result.stderr),
    };
    return sendJson(res, 200, payload);
  } catch (error) {
    const responsePayload = {
      error: error?.message || 'Impossible de lancer le scraper.',
      output: tailLines(error?.stdout, error?.stderr),
    };
    if (typeof error?.durationSeconds === 'number' && Number.isFinite(error.durationSeconds)) {
      responsePayload.durationSeconds = error.durationSeconds;
    }
    const statusCode = error?.code === 'ETIMEDOUT' ? 504 : 500;
    return sendJson(res, statusCode, responsePayload);
  }
}
