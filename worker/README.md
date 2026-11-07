---
title: DuckClean Worker
emoji: 🦆
colorFrom: gray
colorTo: orange
sdk: docker
app_port: 7860
pinned: false
---

# DuckClean worker

CPU worker for probe, proxy, poster and cancel. The API calls this service with
an HMAC-signed request. No database and no R2 credential live here: every input
and output uses a short-lived presigned URL.

Health: `GET /health`
