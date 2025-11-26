// pages/api/bureau-en-gros/deals.js

export default function handler(req, res) {
  res.status(200).json({
    ok: true,
    query: req.query,
  });
}
