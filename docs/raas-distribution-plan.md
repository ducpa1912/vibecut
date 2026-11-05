# Studio RaaS · render as a service

Date: 2026-11-05
Status: plan only, nothing built
Companions: [distribution plan](distribution-plan.md) · [cloud architecture](cloud-architecture.md) · [license audit](licensing-audit.md)

**The offer:** people visit the site, plan the cut in Studio, pay for the final render, and download the file.

**Recommendation:** build RaaS as a new hosted profile of Studio, with a private beta before any payment. Start only after the Clean retest passes. The Mac app stays a separate product. Prices, speeds and costs below are starting assumptions until Phase 0 measures them.

---

## 1. SaaS and RaaS

| | SaaS | RaaS |
|---|---|---|
| Customer pays for | Access to the app, usually monthly | Each finished file |
| Who carries idle or heavy use | The business: a flat fee, whatever they use | The customer: cost follows use |
| Planning | Part of the plan | Free or cheap, within limits |
| Where the money shows up | Sign-up | Final render |
| Good for | Regular users | Occasional users, and people who will not subscribe |

RaaS is not a different kind of software. It is hosted software, so it is a form of SaaS, sold per result. For licensing it is the same as Profile A in the distribution plan: customers get a browser and output files, and no binary.

**What does change:** [cloud-architecture.md](cloud-architecture.md) plans one server per customer. That cannot serve a public site where strangers walk in, so RaaS needs real accounts and shared workers.

| Product | Who it suits | Payment |
|---|---|---|
| Mac app | Regular creator with a Mac who wants local files and flat cost | One-time |
| Hosted SaaS | Team that wants its own private server | Monthly |
| RaaS | Anyone with a browser who makes clips now and then | Per render |

## 2. This reverses written product rules

Founder sign-off is needed, because these are in force today:

- `ROADMAP.md` never-list: "No accounts, cloud sync, team seats, subscription, credits, per-clip meter."
- `ROADMAP.md` local rule: everything works with the network off.
- `PRD.md`: the main buyer "will not accept Terminal install, watermark, meter, or mandatory cloud."

Those rules describe the Mac buyer, so RaaS targets a different buyer. Keep the rules for the Mac app and add a separate section for RaaS. Two more never-list items stay in force on hosted: no watermark removal, and no voice cloning (see section 7).

## 3. The customer flow

| Step | Customer sees | Server does | Who pays |
|---|---|---|---|
| 1. Sign in | Email link or Google | Creates account and quota | Business |
| 2. Upload | Progress bar that survives a dropped connection | Stores the source in object storage | Business, capped |
| 3. Prepare | "Reading your video" | Makes a 720p work copy, then finds scenes, transcript and on-screen text | Business, capped |
| 4. Plan | All of Moments and Edit | Saves the Edit, serves previews from the work copy | Business, capped |
| 5. Quote | Price and wait time for the exact cut | Calculates from the Edit, runs nothing | Nobody |
| 6. Pay | Credits taken | Freezes that Edit version and queues it | Customer |
| 7. Render | Progress, and an email when done | Worker renders from the full source | Customer |
| 8. Download | Download button, kept 7 days | Signed link | Customer |

If a render fails, credits return automatically, with no ticket needed.

## 4. Planning is not free to host

"Only the final stage renders" is the right experience, but steps 2 to 4 cost real money in today's code:

| Planning action | What runs today | Hosted answer |
|---|---|---|
| Import | Full analysis of the source | Cap source length; free allowance |
| Transcript | Apple Speech or a cloud route | Cloud or Linux speech engine, metered |
| Check and Scan | Apple Vision OCR | Linux OCR engine, metered per video |
| Find moments | AI text call | Business key, with a daily cap |
| Exact preview frame | Render per pause, from the source | Render from the work copy |
| Fast preview | One or two copies per moment, built on demand | From the work copy, with a limit |
| Test 1 second | Real AI fill | A few free per project, then credits |

A visitor who uploads a one-hour podcast and leaves still costs money. So free use needs a sign-in and hard caps from day one.

## 5. Architecture

```text
Browser (Studio UI)
   │ HTTPS
   ▼
Hosted API (Studio, `hosted` profile) ── Postgres: users, job owners, orders, credits, queue
   │
   ├─ Object storage: sources, work copies, Edit bundles, finished files
   │
   ├─ Prepare workers (CPU): work copy, scenes, speech, OCR
   ├─ Render workers (CPU): ffmpeg at full quality
   └─ Fill workers (GPU, start on demand): AI fill only
```

**Why this fits the code:** an Edit is already one versioned, hashed JSON document, and a render compiles from it. So a worker can be close to a pure function: take the source and the frozen Edit, and return a file. Keep the job folder layout, copy a job's bundle to a worker's scratch disk, run today's render, and upload the result. That avoids rewriting `render.py`.

**Stay simple at the start:** use Postgres as the queue. Add Redis or Kubernetes only when measurements call for it.

## 6. Code work

| Today | Problem on a public site | Change |
|---|---|---|
| `VIBECUT_TOKEN`, one shared secret | Not user accounts | Real sign-in and sessions |
| `GET /api/jobs` lists every job | **Anyone sees everyone's videos** | Owner check on all about 180 routes, denied by default, with a test that walks every route |
| `POST /api/jobs/path` imports a server path | **Reads files from the server** | Not in the hosted profile |
| Setup holds provider keys and settings | Shared secrets are exposed | Not in the hosted profile; admin only |
| Upload limit 20 GB, through the API | Disk and cost abuse | Resumable direct upload, starting at 2 GB and 60 minutes |
| In-process pools, one render at a time | One user blocks everyone | Worker queue with per-user limits |
| `vision.py` and Apple Speech are macOS only | No OCR or local speech on Linux | Linux OCR and speech, tested against Apple's results first |
| `textfill/sttn.py` chooses only `cpu` or `mps` | No Nvidia GPU support | Add `cuda`, and measure it |
| Import says "The video stays on this machine" | **False on hosted** | Honest copy on Import, Setup and the privacy page |
| Finish says "Add to queue" | No price | Quote, pay, render, download |
| `cleanup_storage` retention | Per machine, not per customer | Per-user retention with a real delete |
| ffmpeg runs on trusted files | Hostile uploads can attack it | Each job in a sandbox with no network, memory and time limits, and only local file protocols |

**New in the hosted profile:** add `HOSTED` to `core/profiles.py` and list only what ships. Leave out `voice_clone`, `url_ingest`, Classic and path import.

## 7. Legal and abuse

Get these reviewed by a lawyer before public launch. This is an engineering list, not legal advice.

**Your risk rises once you host.** On a Mac, the customer's file stays with the customer. Hosted, you store it, process it and hand it back.

| Item | Decision |
|---|---|
| Removing text and logos | `rights.py` already refuses watermarks. Keep that. On hosted, also refuse `handle_or_logo` and require the rights tick on every import. AI text removal is the feature most likely to be used on stolen video, and US DMCA §1202 covers removing identifying information |
| URL import | **Off.** A public paid site that downloads from YouTube or TikTok invites legal trouble and IP blocks |
| Voice cloning | **Off.** It needs proof of consent and is on the never-list |
| Takedowns | Registered DMCA agent, a takedown form, a repeat-offender rule and a way to remove a file fast |
| Illegal content | A written reporting process, and scanning if counsel advises it. Do this before strangers can upload |
| Privacy | Privacy policy, data processing terms, subprocessor list, real deletion, and disclosure of which AI and speech providers see what |
| Payment and tax | A merchant of record handles worldwide sales tax, for a higher fee |
| Models and engines | Same hard stops as the distribution plan: no MusicGen, no Demucs weights, no AGPL parts |
| H.264 | Ask counsel whether charging for encoded files needs an AVC patent license |
| Apple | See Phase 1. macOS license terms limit some commercial hosted use |

## 8. Cost and price

Nothing here is measured on server hardware yet, so Phase 0 replaces these numbers.

| Item | What we know | Effect |
|---|---|---|
| AI fill on Mac | Seed rate of 4.6 seconds per strip per frame, from an M1 8 GB under swap | 60 seconds at 30 fps with one strip is about 2.3 hours. Too slow to sell |
| AI fill on GPU | RTX 4090 about $0.70 to $1.10 per hour on RunPod, late 2026. Speed unknown | If 20× faster than that Mac (a guess), about 7 minutes and $0.10 per minute of clip. At Mac speed, about $2.50 |
| Plain render | CPU ffmpeg. Not measured | Likely cents per minute of output |
| Speech | About $0.006 per minute on common APIs, from memory; check current prices | About $0.36 for a one-hour upload, even if they never pay |
| Card fees | About 2.9% + 30¢ per charge, more with a merchant of record | A $1 charge loses too much. Sell credit packs |
| Market | Shotstack sells 50 minutes for $10 (20¢ per minute), down to 5¢ on plans. It is an API, with no editor or AI fill | A price floor, not the ceiling |

**Starting price to test, not a decision:**

- Minimum purchase $10.
- Plain render: about 50¢ per output minute.
- With AI fill: about $2 per output minute of filled video.
- Free tier: one source up to 30 minutes, all planning, and a 720p preview. One free final render under 60 seconds after email sign-in.
- No watermark on paid files.

**Rule:** gross margin must stay above 60% on the measured cost of real jobs, including the free use behind each paying customer.

## 9. Phases

Durations are rough, assume one founder plus OpenCode, and exclude legal waiting time.

| Phase | Build | Exit gate |
|---|---|---|
| **0. Prove and measure** (1 week) | Finish the Clean retest. Measure prepare, render and fill on a rented Linux GPU, using videos the founder supplies. Compare Linux OCR and speech with Apple's | Retest passes. Real cost per job known. Linux OCR is good enough, or a fallback is chosen |
| **1. Private beta** (3 to 4 weeks) | `HOSTED` profile, sign-in, job owners, the route test, removal of the unsafe routes, retention, sandbox. About 20 invited people, free | No crossover between accounts in the test. At least 5 people finish and download a clip without help |
| **2. Paid beta** (3 to 4 weeks) | Credits, quote, pay, refund on failure, separate workers, GPU fill, email when done. Lawyer's review, terms and takedown process | Real strangers pay twice or more. Margin holds on real jobs |
| **3. Public** (ongoing) | Open sign-up, abuse limits, monitoring, on-call, autoscaling once queues demand it | Queue wait within the promise. Support is manageable |

**Phase 1 hardware:** one Mac mini is the fastest start, because it keeps Apple's OCR and speech with no porting. It suits only a free invite-only beta, and AI fill will be slow, so limit fill to short clips. Before Phase 2, move to Linux. A single Mac cannot serve the queue, and macOS license terms limit some commercial hosted uses, such as service-bureau use in virtual machines. Ask counsel about any paid use on Macs.

## 10. Not in the first release

Subscriptions, teams and seats, a public API, publishing to networks, URL import, voice cloning, a Windows app, customer-hosted images and 4K.

## 11. Decisions for the founder

1. **Reverse the never-list for a separate RaaS product?** Recommended: yes, and the Mac rules stay.
2. **Who is the first buyer?** Recommended: occasional creators cutting short clips from existing long videos. It sets the free tier and price.
3. **AI fill at launch?** Recommended: yes, in Paid beta, with logos and handles refused. It is the main difference from cheaper tools, and also the biggest cost and legal risk.
4. **Which comes first: RaaS or the Mac app?** Recommended: finish Phase 0 first, since the retest is needed for both, then decide with real costs.
5. **Where does the code live?** Recommended: a profile on the `studio` branch, not a fourth lane, so fixes reach both products.
6. **Who sells it?** A merchant of record or your own company with a card processor. This depends on your country, and needs your accountant and lawyer.

## Sources

- Shotstack prices: https://shotstack.io/pricing/
- RunPod RTX 4090: https://www.runpod.io/gpu-models/rtx-4090 and https://www.hivenet.com/post/runpod-pricing-complete-guide-to-gpu-cloud-costs
- macOS license terms: https://www.apple.com/legal/sla/ (read through secondary summaries; counsel should read the current text)
- Code facts: `app.py`, `rights.py`, `textfill/__init__.py`, `textfill/sttn.py`, `core/profiles.py`, `vision.py`, `stt.py`
