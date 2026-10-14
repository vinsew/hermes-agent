# Six plugin safety overlays for Hermes v0.22.0

Upstream pins in pins.json remain the recorded source; *.patch files describe locally reviewed deviations. Core runtime stays 07ceb8d629f1643f35e47da6f35b0dc505347e4e. These patches are not upstream commits and must be re-reviewed before plugin updates. Never overwrite the overlays using a catalog update.

Apply each patch to the plugin subdirectory at its exact upstream SHA with git apply (including context-audit root). Run behavioral tests using the Hermes canonical test runner with plugin-audit-inputs pointing to the patched plugin directories. joint_checks.py expects sibling staged/, pins.json and core/ in an isolated work directory. It creates temporary profiles and deletes only its own fixtures. Do not run synthetic observer events against production.

Safety boundaries: chat history metadata only; restore/forget and ledger clear default disabled and require separate operator authorization; private state modes 700/600; cross-process bounded ledger locking; 2MB/5000-row ledger limits; profile-scoped context state, UTF8 sizes, 90-day/100k-row context retention; conservative memory history admission budget 256MiB (not an atomic filesystem quota). Context SQLite does not shrink automatically after its peak. Ledger lock waits at most 0.5s and drops only observation events on timeout, preserving the agent turn.

Validation: original admission 13 failures; hardened 16 pass; context upstream selftest 49 and real dispatch integration 9 pass; six-plugin joint dispatch tested with two concurrent profiles, exact payload contract, no raw-body persistence, dummy masking and isolated restore gates. Windows is outside current Linux cloud and macOS Desktop deployment acceptance.
