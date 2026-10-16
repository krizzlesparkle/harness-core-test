---
name: reconcile-harness
description: Compare a harness repo with its upstream core, show what differs per file, and move the changes you choose in either direction. Use when the user says reconcile, sync my harness, promote this to core, or pull core updates.
---

# Reconcile a harness with its core

A harness repo holds a `harness.manifest.json` that tags each path `core`, a side name, or never-tracked, and names its upstream cores with the direction changes may flow.

Run the tool the manifest points at:

1. `status`: list files that differ between the harness copy and its upstream, per file.
2. `pull`: bring chosen upstream changes into the harness. Never overwrites a file tagged for this side only.
3. `promote`: write chosen harness changes out as a patch for the upstream. Every file passes the scan gate first; a blocked or unread file stops the promotion.

Never move a file the manifest does not tag `core`. Ask the user before any promotion.
