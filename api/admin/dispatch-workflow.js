import process from 'node:process';

import { sendJson, methodNotAllowed } from '../../lib/http.js';
import { readJsonBody } from '../../lib/request.js';

const GITHUB_API_BASE_URL = 'https://api.github.com';
const DEFAULT_REF = 'main';

function resolveRepository() {
  const repo =
    process.env.ADMIN_WORKFLOW_REPOSITORY?.trim() ||
    process.env.ADMIN_WORKFLOW_REPO?.trim() ||
    process.env.GITHUB_REPOSITORY?.trim();
  return repo || '';
}

function resolveWorkflowIdentifier() {
  const identifier =
    process.env.ADMIN_WORKFLOW_ID?.trim() ||
    process.env.ADMIN_WORKFLOW_FILE?.trim() ||
    process.env.ADMIN_WORKFLOW_FILENAME?.trim();
  return identifier || '';
}

function resolveToken() {
  const token =
    process.env.ADMIN_WORKFLOW_TOKEN?.trim() ||
    process.env.GITHUB_TOKEN?.trim();
  return token || '';
}

function normaliseInputs(inputs) {
  if (!inputs || typeof inputs !== 'object') {
    return undefined;
  }

  const entries = Object.entries(inputs).filter(([key]) => key);
  if (!entries.length) {
    return undefined;
  }

  return Object.fromEntries(
    entries.map(([key, value]) => [key, value == null ? '' : String(value)]),
  );
}

export default async function handler(req, res) {
  if (req?.method && req.method !== 'POST') {
    return methodNotAllowed(res, 'POST');
  }

  const repository = resolveRepository();
  if (!repository) {
    return sendJson(res, 500, {
      error:
        "ADMIN_WORKFLOW_REPOSITORY (ou ADMIN_WORKFLOW_REPO) n'est pas configurée.",
    });
  }

  const workflowIdentifier = resolveWorkflowIdentifier();
  if (!workflowIdentifier) {
    return sendJson(res, 500, {
      error:
        "ADMIN_WORKFLOW_FILE (ou ADMIN_WORKFLOW_ID) n'est pas configuré.",
    });
  }

  const token = resolveToken();
  if (!token) {
    return sendJson(res, 500, {
      error:
        "ADMIN_WORKFLOW_TOKEN (ou GITHUB_TOKEN) est requis pour déclencher le workflow.",
    });
  }

  let payload = {};
  try {
    payload = (await readJsonBody(req)) || {};
  } catch (error) {
    payload = {};
  }

  const ref =
    (typeof payload.ref === 'string' && payload.ref.trim()) ||
    process.env.ADMIN_WORKFLOW_REF?.trim() ||
    DEFAULT_REF;

  const inputs = normaliseInputs(payload.inputs);

  const url = `${GITHUB_API_BASE_URL}/repos/${repository}/actions/workflows/${encodeURIComponent(
    workflowIdentifier,
  )}/dispatches`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'econodeal-admin-workflow-trigger',
      },
      body: JSON.stringify(
        inputs ? { ref: ref || DEFAULT_REF, inputs } : { ref: ref || DEFAULT_REF },
      ),
    });

    if (!response.ok) {
      let errorMessage = `GitHub a retourné le statut ${response.status}.`;
      try {
        const details = await response.json();
        if (details?.message) {
          errorMessage = details.message;
        }
      } catch (error) {
        // ignore JSON parsing issues
      }
      return sendJson(res, response.status, {
        error: errorMessage,
      });
    }

    return sendJson(res, 200, {
      status: 'ok',
      message:
        'Déclenchement du workflow GitHub effectué. Surveillez l’onglet Actions pour suivre le run.',
    });
  } catch (error) {
    return sendJson(res, 500, {
      error: `Impossible de contacter l’API GitHub : ${error?.message || error}`,
    });
  }
}
