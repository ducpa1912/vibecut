# Moving-fill licences

Loop 8, 2026-11-12. The question: can another video-inpaint engine be shipped to remove burned-in
text on moving footage, where LaMa guesses? Every row was read from the project's own licence file
or README on 2026-11-12, at the URL in the row. **"Unclear" counts as no**: nothing enters the
build, the repo or this Mac's bundle without a yes.

The search covered the engines named in the brief (STTN, ProPainter, E2FGVI) plus the closest open
implementations of the same idea (MAT, FGT, FGVC, DiffuEraser, VideoPainter). An engine whose
*code* is permissive but whose *weights* carry no grant is not allowed: a paid app ships the
weights, not the paper.

| Engine | Code licence | Weights licence | Quoted clause | Commercial? |
|---|---|---|---|---|
| **LaMa** (shipped) | Apache-2.0 | Apache-2.0 (`lama_fp32.onnx`, Carve/LaMa-ONNX port, shipped since loop 3) | "Apache License Version 2.0, January 2004" — https://github.com/advimman/lama/blob/main/LICENSE | **yes** |
| STTN (2020) | MIT | **unclear**: `sttn.pth` is posted on Google Drive; the licence covers the software and no separate grant covers the checkpoint | "The MIT License (MIT) Copyright (c) 2016 Michael Rose" — https://github.com/researchmm/STTN/blob/master/LICENSE ; "we provide a model pretrained on Youtube-VOS" — https://github.com/researchmm/STTN#completing-videos-using-pretrained-model | no |
| FGT (2022) | MIT | **unclear**: same shape as STTN — MIT for "this work", checkpoints on Google Drive with no terms of their own, trained on YouTube-VOS | "This work is licensed under MIT license. See the [LICENSE](LICENSE) for details." — https://github.com/hitachinsk/FGT#license ; "Download the [[pre-trained models](https://drive.google.com/…)]" — https://github.com/hitachinsk/FGT#test | no |
| ProPainter (2023) | S-Lab License 1.0 | S-Lab 1.0 (repository release) | "Redistribution and use for non-commercial purpose in source and binary forms, with or without modification, are permitted" — https://github.com/sczhou/ProPainter/blob/main/LICENSE | **no** |
| E2FGVI (2022) | CC BY-NC 4.0 | CC BY-NC 4.0 | "Attribution-NonCommercial 4.0 International" — https://github.com/MCG-NKU/E2FGVI/blob/master/LICENSE | **no** |
| MAT (2022) | CC BY-NC 4.0 | CC BY-NC 4.0 | "Attribution-NonCommercial 4.0 International" — https://github.com/fenglinglwb/MAT/blob/main/LICENSE | **no** |
| DiffuEraser (2025) | Apache-2.0 | **no**: its own Apache grant does not reach the prior model it runs, ProPainter (S-Lab, non-commercial), nor the SD 1.5 base (OpenRAIL-M) | "This repository uses [Propainter](https://github.com/sczhou/ProPainter) as the prior model. Users must comply with [Propainter's license](…) when u[sing]" — https://github.com/lixiaowen-xw/DiffuEraser#license | **no** |
| VideoPainter (2025) | Custom (CogVideoX-based) | **unclear**: fine-tuned from CogVideo 5B under the CogVideoX License, plus "components originally developed or modi[fied]" | "This project, \"VideoPainter\", is fine-tuned with the assistance of \"CogVideo 5B\", which is subject to the The CogVideoX License." — https://github.com/TencentARC/VideoPainter/blob/main/LICENSE | no |
| FGVC (2020, FGT's predecessor) | MIT | **unclear**: no checkpoint terms stated | "MIT License Copyright (c) 2020 Virginia Tech Vision and Learning Lab" — https://github.com/vt-vl-lab/FGVC/blob/master/LICENSE | no |

## Reading

**No candidate is allowed.** Three are explicitly non-commercial (ProPainter, E2FGVI, MAT), one
inherits a non-commercial prior (DiffuEraser), one is tied to a bespoke generative licence
(VideoPainter), and four publish permissive *code* with checkpoints that carry no separate grant
(STTN, FGT, FGVC). Marking any of those "yes" on the strength of a code licence would be a guess
with the founder's $29 app behind it, so the table says no.

A permissive engine may still be used by the user through the custom fill slot: the user obtains
the weights, DuckSuite loads them locally, ships none and names none. That is the only path this
loop builds.

## What was not checked

- MiniMax-Remover and other 2026 releases: not searched. A row needs a licence file and a weight
  grant read at the source, not a name in a paper.
- YouTube-VOS and DAVIS dataset terms beyond noting the checkpoints were trained on them.
- Legal advice. This is a licence reading, not a legal opinion.
