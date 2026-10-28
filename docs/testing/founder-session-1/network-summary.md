# Network summary (generated from network.har, media bodies left out)

```text
entries 472 span s 1502

== non-2xx
   64.5 404 GET /api/jobs/7610134fee5e/check | {"detail":"Check has not run yet."}
   66.8 404 GET /api/jobs/7610134fee5e/check | {"detail":"Check has not run yet."}
  579.4 404 GET /api/jobs/7610134fee5e/edits/current?set_id=cs_81c8debebdb9&story_id=st_0000000_0020880&aspect=9%3A16 | {"detail":"This story has no Edit yet."}
  707.8 422 GET /api/jobs/7610134fee5e/edits/ed_be468ded6e96e529810334e6f1c3160d/frame?t=20.800&quality=draft | {"detail":"t must be between 0 and the story duration (20.800s)."}
  727.1 404 GET /api/jobs/7610134fee5e/edits/current?set_id=cs_81c8debebdb9&story_id=st_0027000_0052800&aspect=9%3A16 | {"detail":"This story has no Edit yet."}
  893.2 404 GET /api/jobs/25bb4aaa14e2/check | {"detail":"Check has not run yet."}
  893.3 404 GET /api/jobs/25bb4aaa14e2/check | {"detail":"Check has not run yet."}
 1114.0 404 GET /api/jobs/25bb4aaa14e2/edits/current?set_id=cs_f256b226259b&story_id=st_0030125_0048204&aspect=4%3A5 | {"detail":"This story has no Edit yet."}
 1114.0 404 GET /api/jobs/25bb4aaa14e2/edits/current?set_id=cs_f256b226259b&story_id=st_0030125_0048204&aspect=9%3A16 | {"detail":"This story has no Edit yet."}
 1138.5 422 GET /api/jobs/25bb4aaa14e2/edits/ed_c352ae5ba0f7047948338bea7cc665a1/frame?t=18.067&quality=draft | {"detail":"t must be between 0 and the story duration (18.067s)."}
 1144.2 404 GET /api/jobs/25bb4aaa14e2/edits/current?set_id=cs_f256b226259b&story_id=st_0053625_0069188&aspect=9%3A16 | {"detail":"This story has no Edit yet."}
 1172.9 404 GET /api/jobs/25bb4aaa14e2/edits/current?set_id=cs_f256b226259b&story_id=st_0030125_0048204&aspect=9%3A16 | {"detail":"This story has no Edit yet."}
 1172.9 404 GET /api/jobs/25bb4aaa14e2/preflight?story_id=st_0030125_0048204 | {"detail":{"code":"story_not_found","message":"Story 'st_0030125_0048204' was not found in this job.","suggestion":"Pass a render key, artifact id, or saved story id."}}
 1235.1 404 GET /api/jobs/97a5fd3744c0/check | {"detail":"Check has not run yet."}
 1235.2 404 GET /api/jobs/97a5fd3744c0/check | {"detail":"Check has not run yet."}
 1434.6 404 GET /api/jobs/97a5fd3744c0/edits/current?set_id=cs_38bfa4136a93&story_id=st_0010625_0034375&aspect=4%3A5 | {"detail":"This story has no Edit yet."}
 1434.6 404 GET /api/jobs/97a5fd3744c0/edits/current?set_id=cs_38bfa4136a93&story_id=st_0010625_0034375&aspect=9%3A16 | {"detail":"This story has no Edit yet."}
 1452.8 404 GET /api/jobs/97a5fd3744c0/edits/current?set_id=cs_38bfa4136a93&story_id=st_0010625_0034375&aspect=9%3A16 | {"detail":"This story has no Edit yet."}
 1452.9 404 GET /api/jobs/97a5fd3744c0/preflight?story_id=st_0010625_0034375 | {"detail":{"code":"story_not_found","message":"Story 'st_0010625_0034375' was not found in this job.","suggestion":"Pass a render key, artifact id, or saved story id."}}

== slowest (>1.5s)
 1434.9   17.9s 206 GET /api/jobs/97a5fd3744c0/edits/ed_aa9fd42a3b49bcddd3565900a420457d/proxy
  587.9   16.1s 206 GET /api/jobs/7610134fee5e/edits/ed_be468ded6e96e529810334e6f1c3160d/proxy
  579.8    2.1s -1 GET /api/jobs/7610134fee5e/edits/ed_be468ded6e96e529810334e6f1c3160d/proxy

== top routes
129 /api/jobs/#/status
60 /api/story-queues
39 /api/jobs/#/artifacts
31 /api/jobs/#/clip-sets/cs_#/stories/st_#_#/trim
22 /api/jobs/#/check
22 /api/jobs/#/clip-sets
22 /api/jobs/#/edits/ed_#/frame
19 /api/jobs
18 /api/jobs/#
12 /api/jobs/#/edits/current
8 /api/jobs/#/edits
7 /api/jobs/#/edits/ed_#/proxy
5 /api/jobs/#/packets
5 /api/shares
4 /api/jobs/#/edits/ed_#
3 /api/rights/policy
3 /api/jobs/#/thumb/#
2 /api/jobs/upload
2 /api/jobs/#/clip-sets/cs_#/stories/st_#_#/render
2 /api/jobs/#/captions/cap_#
2 file:///Users/happynghia/Downloads/Comment%#JOYLO%#and%#Ill%#send%#you%#the%#link!%#%#%E#%#%A#%#See%#more.mp#
2 /api/jobs/#/edits/ed_#/preflight
2 /api/jobs/#/artifacts/art_#/media/poster.jpg
2 /api/jobs/#/artifacts/art_#/media/reel.mp#
2 /api/jobs/#/preflight

== POST/PATCH/PUT
   25.4 200 POST /api/jobs/upload
   70.7 202 POST /api/jobs/7610134fee5e/check
  386.3 202 POST /api/jobs/7610134fee5e/check
  545.7 200 POST /api/jobs/7610134fee5e/clip-sets
  558.3 200 POST /api/jobs/7610134fee5e/clip-sets/cs_81c8debebdb9/stories/st_0000000_0020880/render
  559.7 200 POST /api/jobs/7610134fee5e/clip-sets/cs_81c8debebdb9/stories/st_0027000_0052800/render
  579.5 200 POST /api/jobs/7610134fee5e/edits
  727.1 200 POST /api/jobs/7610134fee5e/edits
  776.8 200 PATCH /api/jobs/7610134fee5e/edits/ed_4ed074769badf68c6c4af968c7844431
  783.9 200 PATCH /api/jobs/7610134fee5e/edits/ed_18a61ae2b7f5cc878e2084348b0f8416
  799.8 200 PATCH /api/jobs/7610134fee5e/edits/ed_581aea6306cf566b332e7f2171c00a2b
  803.5 200 PATCH /api/jobs/7610134fee5e/edits/ed_7c05248be24777bef2ccc1463fa2edd0
  845.2 200 POST /api/story-queues
  846.1 200 POST /api/story-queues
  847.2 200 POST /api/story-queues
  847.9 200 POST /api/story-queues
  894.9 202 POST /api/jobs/25bb4aaa14e2/check
 1096.7 200 POST /api/jobs/25bb4aaa14e2/clip-sets
 1102.9 200 POST /api/jobs/25bb4aaa14e2/clip-sets
 1108.4 200 POST /api/story-queues
 1114.1 200 POST /api/jobs/25bb4aaa14e2/edits
 1144.2 200 POST /api/jobs/25bb4aaa14e2/edits
 1175.1 200 POST /api/story-queues
 1179.0 200 POST /api/story-queues
 1179.8 200 POST /api/story-queues
 1180.4 200 POST /api/story-queues
 1210.0 200 POST /api/jobs/upload
 1250.9 202 POST /api/jobs/97a5fd3744c0/check
 1423.9 200 POST /api/jobs/97a5fd3744c0/clip-sets
 1434.7 200 POST /api/jobs/97a5fd3744c0/edits
 1457.1 200 POST /api/story-queues
 1460.4 200 POST /api/story-queues

== Check / queue progress timeline
   25.7 GET jobs/7610134fee5e/status {"status": "scanning", "progress": 0.02, "message": "Slicing the timeline", "error": null}
   27.7 GET jobs/7610134fee5e/status {"status": "scanning", "progress": 0.2063, "message": "Scanning cuts · 0:29 / 0:52", "error": null}
   29.8 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.4677, "message": "Pulling stills · 4 / 26", "error": null}
   31.8 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.5577, "message": "Pulling stills · 17 / 26", "error": null}
   33.8 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.63, "message": "Reading frames · text + subject", "error": null}
   39.9 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.6612, "message": "Tracking crop · 2 / 34", "error": null}
   41.9 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.6641, "message": "Tracking crop · 7 / 34", "error": null}
   43.9 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.6676, "message": "Tracking crop · 13 / 34", "error": null}
   46.0 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.6706, "message": "Tracking crop · 18 / 34", "error": null}
   48.0 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.6747, "message": "Tracking crop · 25 / 34", "error": null}
   50.1 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.6765, "message": "Tracking crop · 28 / 34", "error": null}
   52.2 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.68, "message": "Tracking crop · 34 / 34", "error": null}
   62.4 GET jobs/7610134fee5e/status {"status": "reading", "progress": 0.7, "message": "Transcribing speech · Apple speech", "error": null}
   64.5 GET jobs/7610134fee5e/status {"status": "ready", "progress": 1.0, "message": "26 moments · hook found", "error": null}
   64.5 GET jobs/7610134fee5e/check {}
   70.7 POST jobs/7610134fee5e/check {"status": "running", "progress": 0.05, "message": "Sampling text at 1 frames a second", "error": null}
   73.0 GET jobs/7610134fee5e/check {"status": "running", "progress": 0.05, "message": "Pulling frames to read text", "error": null}
  217.7 GET jobs/7610134fee5e/check {"status": "ready", "error": null}
  386.3 POST jobs/7610134fee5e/check {"status": "running", "progress": 0.01, "message": "Reading the source", "error": null}
  845.2 QUEUE sq_27dc9 running {"progress": 0.0, "message": "Rendering"}
  846.2 QUEUE sq_2928f running {"progress": 0.0, "message": "Rendering"}
  846.2 QUEUE sq_27dc9 running {"progress": 0.87, "message": "Rendering"}
  847.2 QUEUE sq_119cd running {"progress": 0.0, "message": "Rendering"}
  847.9 QUEUE sq_3c5b1 running {"progress": 0.0, "message": "Rendering"}
  850.3 QUEUE sq_2928f running {"progress": 0.87, "message": "Rendering"}
  855.1 QUEUE sq_119cd running {"progress": 0.0909, "eta": 7.0, "message": "Rendering"}
  855.1 QUEUE sq_2928f done {"progress": 1.0, "message": "Done"}
  857.6 QUEUE sq_119cd running {"progress": 0.6582, "eta": 1.7, "message": "Rendering"}
  860.0 QUEUE sq_119cd running {"progress": 0.87, "eta": 0.6, "message": "Rendering"}
  862.4 QUEUE sq_119cd running {"progress": 0.95, "eta": 0.4, "message": "Rendering"}
  864.8 QUEUE sq_3c5b1 running {"progress": 0.215, "eta": 7.9, "message": "Rendering"}
  864.8 QUEUE sq_119cd done {"progress": 1.0, "message": "Done"}
  867.3 QUEUE sq_3c5b1 running {"progress": 0.4588, "eta": 5.3, "message": "Rendering"}
  869.7 QUEUE sq_3c5b1 running {"progress": 0.5563, "eta": 4.7, "message": "Rendering"}
  872.2 QUEUE sq_3c5b1 running {"progress": 0.7513, "eta": 3.0, "message": "Rendering"}
  874.6 QUEUE sq_3c5b1 running {"progress": 0.87, "eta": 1.6, "message": "Rendering"}
  879.4 QUEUE sq_3c5b1 done {"progress": 1.0, "message": "Done"}
  893.2 GET jobs/25bb4aaa14e2/status {"status": "ready", "progress": 1.0, "message": "25 moments · hook found", "error": null}
  893.2 GET jobs/25bb4aaa14e2/check {}
  894.9 POST jobs/25bb4aaa14e2/check {"status": "running", "progress": 0.01, "message": "Reading the source", "error": null}
  896.7 GET jobs/25bb4aaa14e2/check {"status": "running", "progress": 0.05, "message": "Pulling frames to read text", "error": null}
 1058.6 GET jobs/25bb4aaa14e2/check {"status": "ready", "error": null}
 1172.9 QUEUE sq_18096 done {"progress": 1.0, "message": "Done"}
 1175.1 QUEUE sq_5b841 running {"progress": 0.0, "message": "Rendering"}
 1177.5 QUEUE sq_5b841 running {"progress": 0.1367, "eta": 14.9, "message": "Rendering"}
 1179.0 QUEUE sq_58f4a running {"progress": 0.0, "message": "Rendering"}
 1179.0 QUEUE sq_5b841 running {"progress": 0.29, "eta": 8.2, "message": "Rendering"}
 1179.8 QUEUE sq_0b088 running {"progress": 0.0, "message": "Rendering"}
 1180.5 QUEUE sq_abc7b running {"progress": 0.0, "message": "Rendering"}
 1180.5 QUEUE sq_0b088 done {"progress": 1.0, "message": "Done"}
 1182.9 QUEUE sq_abc7b done {"progress": 1.0, "message": "Done"}
 1185.3 QUEUE sq_58f4a running {"progress": 0.7025, "eta": 1.0, "message": "Rendering"}
 1187.8 QUEUE sq_58f4a done {"progress": 1.0, "message": "Done"}
 1210.9 GET jobs/97a5fd3744c0/status {"status": "scanning", "progress": 0.02, "message": "Slicing the timeline", "error": null}
 1212.9 GET jobs/97a5fd3744c0/status {"status": "scanning", "progress": 0.1713, "message": "Scanning cuts · 0:39 / 1:28", "error": null}
 1214.9 GET jobs/97a5fd3744c0/status {"status": "reading", "progress": 0.4976, "message": "Pulling stills · 8 / 25", "error": null}
 1216.9 GET jobs/97a5fd3744c0/status {"status": "reading", "progress": 0.63, "message": "Reading frames · text + subject", "error": null}
 1221.0 GET jobs/97a5fd3744c0/status {"status": "reading", "progress": 0.6683, "message": "Tracking crop · 20 / 48", "error": null}
 1223.0 GET jobs/97a5fd3744c0/status {"status": "reading", "progress": 0.6792, "message": "Tracking crop · 46 / 48", "error": null}
 1225.0 GET jobs/97a5fd3744c0/status {"status": "reading", "progress": 0.68, "message": "Tracking crop · 48 / 48", "error": null}
 1229.0 GET jobs/97a5fd3744c0/status {"status": "reading", "progress": 0.7, "message": "Transcribing speech · Apple speech", "error": null}
 1231.0 GET jobs/97a5fd3744c0/status {"status": "reading", "progress": 0.7, "message": "Transcribing speech · local Whisper", "error": null}
 1235.0 GET jobs/97a5fd3744c0/status {"status": "ready", "progress": 1.0, "message": "25 moments · hook found", "error": null}
 1235.1 GET jobs/97a5fd3744c0/check {}
 1250.9 POST jobs/97a5fd3744c0/check {"status": "queued", "progress": 0.0, "message": "Queued for Check", "error": null}
 1252.8 GET jobs/97a5fd3744c0/check {"status": "running", "progress": 0.05, "message": "Pulling frames to read text", "error": null}
 1385.6 GET jobs/97a5fd3744c0/check {"status": "ready", "error": null}
 1457.2 QUEUE sq_e02b6 running {"progress": 0.0, "message": "Rendering"}
 1459.6 QUEUE sq_e02b6 running {"progress": 0.05, "eta": 21.8, "message": "Rendering"}
 1460.4 QUEUE sq_9cc74 running {"progress": 0.0, "message": "Rendering"}
 1460.4 QUEUE sq_e02b6 running {"progress": 0.0933, "eta": 30.6, "message": "Rendering"}
 1462.8 QUEUE sq_e02b6 running {"progress": 0.29, "eta": 11.5, "message": "Rendering"}
 1467.7 QUEUE sq_9cc74 running {"progress": 0.0033, "message": "Rendering"}
 1467.7 QUEUE sq_e02b6 running {"progress": 0.3333, "eta": 0.0, "message": "Rendering"}
 1470.1 QUEUE sq_9cc74 running {"progress": 0.1367, "eta": 17.1, "message": "Rendering"}
 1470.1 QUEUE sq_e02b6 running {"progress": 0.3333, "message": "Rendering"}
 1472.5 QUEUE sq_9cc74 running {"progress": 0.3333, "message": "Rendering"}
 1472.5 QUEUE sq_e02b6 running {"progress": 0.3367, "message": "Rendering"}
 1475.1 QUEUE sq_e02b6 running {"progress": 0.392, "eta": 26.6, "message": "Rendering"}
 1477.5 QUEUE sq_e02b6 running {"progress": 0.6233, "eta": 5.2, "message": "Rendering"}
 1479.9 QUEUE sq_e02b6 running {"progress": 0.6333, "eta": 8.8, "message": "Rendering"}
 1482.4 QUEUE sq_9cc74 running {"progress": 0.3367, "message": "Rendering"}
 1482.4 QUEUE sq_e02b6 running {"progress": 0.6667, "message": "Rendering"}
 1484.8 QUEUE sq_9cc74 running {"progress": 0.6233, "eta": 3.5, "message": "Rendering"}
 1487.2 QUEUE sq_9cc74 running {"progress": 0.65, "eta": 6.3, "message": "Rendering"}
 1489.7 QUEUE sq_9cc74 running {"progress": 0.6667, "message": "Rendering"}
 1489.7 QUEUE sq_e02b6 running {"progress": 0.7773, "eta": 2.4, "message": "Rendering"}
 1492.1 QUEUE sq_e02b6 running {"progress": 0.9567, "eta": 0.4, "message": "Rendering"}
 1494.5 QUEUE sq_e02b6 running {"progress": 0.9833, "eta": 0.3, "message": "Rendering"}
 1497.0 QUEUE sq_9cc74 running {"progress": 0.8813, "eta": 1.2, "message": "Rendering"}
 1497.0 QUEUE sq_e02b6 done {"progress": 1.0, "message": "Done"}
 1499.4 QUEUE sq_9cc74 running {"progress": 0.9833, "eta": 0.2, "message": "Rendering"}
 1501.8 QUEUE sq_9cc74 done {"progress": 1.0, "message": "Done"}
```
